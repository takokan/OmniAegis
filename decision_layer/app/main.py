from __future__ import annotations

import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from importlib import import_module
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.config import QdrantClientSingleton, load_qdrant_settings
from app.fingerprinters import AudioFingerprinter, ImageFingerprinter, SemanticEmbedder, VideoFingerprinter
from app.registry import RegistryManager
from app.schemas import FingerprintResponse, MatchItem, MatchResponse, Modality

try:
    from decision_layer.services.graph_db import GraphDBService
    from decision_layer.services.monitoring import MetricsRegistry, PrometheusMiddleware, metrics_response
except ModuleNotFoundError:  # pragma: no cover
    from services.graph_db import GraphDBService
    from services.monitoring import MetricsRegistry, PrometheusMiddleware, metrics_response

image_fp = ImageFingerprinter()
video_fp = VideoFingerprinter(frames_to_sample=16)
audio_fp = AudioFingerprinter()
semantic_fp = SemanticEmbedder(embedding_dim=512)
GLOBAL_METRICS = MetricsRegistry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_qdrant_settings()
    qdrant_client = QdrantClientSingleton.get_client(settings)

    app.state.registry = RegistryManager(
        audio_dim=audio_fp.embedding_dim,
        semantic_dim=semantic_fp.embedding_dim,
        qdrant_client=qdrant_client,
        semantic_collection_name=settings.collection_name,
        hnsw_m=settings.hnsw_m,
        hnsw_ef_construct=settings.hnsw_ef_construct,
    )
    app.state.calibration_monitor = {
        "preds": [],
        "targets": [],
        "max_samples": 5000,
    }
    app.state.metrics = GLOBAL_METRICS
    app.state.metrics.set_model_version(1.0)

    graph_db: GraphDBService | None = None
    try:
        graph_db = GraphDBService.from_env()
        graph_db.run_migrations()
    except Exception:
        graph_db = None
    app.state.graph_db = graph_db

    # Stage-7 explainability components (lazy-imported to avoid hard startup coupling).
    explainers_module = import_module("app.reasoning.explainers")
    graph_builder_module = import_module("app.reasoning.graph_builder")
    rights_model_module = import_module("app.reasoning.model")

    visual_explainer_cls = getattr(explainers_module, "VisualExplainer")
    graph_explainer_cls = getattr(explainers_module, "GraphExplainer")
    graph_builder_cls = getattr(graph_builder_module, "GraphBuilder")
    rights_gnn_cls = getattr(rights_model_module, "RightsGNN")

    app.state.visual_explainer = visual_explainer_cls(semantic_fp)
    app.state.graph_builder = graph_builder_cls(graph_db=app.state.graph_db)
    app.state.rights_model = rights_gnn_cls()
    app.state.graph_explainer = graph_explainer_cls(app.state.rights_model)

    try:
        yield
    finally:
        if app.state.graph_db is not None:
            app.state.graph_db.close()
        QdrantClientSingleton.close_client()


app = FastAPI(
    title="OmniAegis Fingerprinting & Verification Gate",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(PrometheusMiddleware, metrics=GLOBAL_METRICS)


def _registry() -> RegistryManager:
    registry = getattr(app.state, "registry", None)
    if registry is None:
        raise HTTPException(status_code=503, detail="Registry is not initialized")
    return registry


def _xai_components() -> tuple[Any, Any, Any]:
    visual = getattr(app.state, "visual_explainer", None)
    graph_builder = getattr(app.state, "graph_builder", None)
    graph_explainer = getattr(app.state, "graph_explainer", None)
    return visual, graph_builder, graph_explainer


def _log_calibration_sample(probability: float, target: int) -> None:
    monitor = getattr(app.state, "calibration_monitor", None)
    if monitor is None:
        return

    p = float(min(max(probability, 0.0), 1.0))
    y = int(1 if target else 0)

    monitor["preds"].append(p)
    monitor["targets"].append(y)

    max_samples = int(monitor.get("max_samples", 5000))
    if len(monitor["preds"]) > max_samples:
        overflow = len(monitor["preds"]) - max_samples
        del monitor["preds"][:overflow]
        del monitor["targets"][:overflow]


def _compute_ece(preds: list[float], targets: list[int], n_bins: int = 10) -> float:
    calibration_module = import_module("app.reasoning.calibration")
    compute_ece_fn = getattr(calibration_module, "compute_ece")
    return float(compute_ece_fn(preds, targets, n_bins=n_bins))


async def _save_upload_to_temp(upload: UploadFile, suffix: str = "") -> str:
    try:
        content = await upload.read()
        if not content:
            raise ValueError("Uploaded file is empty")

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            return tmp.name
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read upload: {exc}") from exc


def _match_results_to_schema(
    modality: Modality,
    results: list[Any],
    query_summary: dict[str, Any],
    explanation: dict[str, Any] | None = None,
) -> MatchResponse:
    return MatchResponse(
        modality=modality,
        query_summary=query_summary,
        matches=[
            MatchItem(
                asset_id=r.asset_id,
                confidence=r.confidence,
                score=r.distance_or_similarity,
                metadata=r.metadata,
            )
            for r in results
        ],
        explanation=explanation or {"visual_highlights": [], "contextual_factors": []},
    )


def _build_image_explanation(content: bytes, top_k: int) -> dict[str, Any]:
    visual, graph_builder, graph_explainer = _xai_components()
    registry = _registry()

    if visual is None or graph_builder is None or graph_explainer is None:
        return {"visual_highlights": [], "contextual_factors": []}

    try:
        image = semantic_fp._load_rgb_image_from_bytes(content)  # noqa: SLF001 - private helper reuse for contract consistency
        image_tensor = semantic_fp.transform(image)
        heatmap = visual.get_visual_explanation(image_tensor)
        boxes = visual.heatmap_to_bounding_boxes(heatmap, top_k=3)
    except Exception:
        boxes = []

    contextual_factors: list[dict[str, Any]] = []
    try:
        semantic = semantic_fp.embed_from_bytes(content)
        phash = image_fp.fingerprint_from_bytes(content)
        semantic_matches = registry.match_semantic(semantic["embedding"], top_k=top_k, modality_filter="image")
        subgraph = graph_builder.build_subgraph(
            query_embedding=semantic["embedding"],
            qdrant_results=semantic_matches,
            query_metadata={"asset_id": f"query:{phash['hash_hex']}", "modality": "image"},
        )
        contextual_factors = graph_explainer.get_graph_explanation(subgraph)
    except Exception:
        contextual_factors = []

    return {
        "visual_highlights": boxes,
        "contextual_factors": contextual_factors,
    }


@app.post("/fingerprint/image", response_model=FingerprintResponse)
async def fingerprint_image(
    file: UploadFile = File(...),
    register: bool = Form(False),
    asset_id: str | None = Form(None),
    source: str | None = Form(None),
) -> FingerprintResponse:
    try:
        registry = _registry()
        content = await file.read()
        fp = image_fp.fingerprint_from_bytes(content)

        assigned_id = asset_id or str(uuid.uuid4())
        if register:
            registry.register_image(
                asset_id=assigned_id,
                hash_bytes=fp["hash_bytes"],
                metadata={"modality": "image", "filename": file.filename, "source": source},
            )

            # Stage-2 semantic registration for derivative-work matching.
            semantic = semantic_fp.embed_from_bytes(content)
            registry.register_semantic(
                asset_id=assigned_id,
                embedding=semantic["embedding"],
                metadata={"semantic_embedding_dim": semantic["embedding_dim"]},
            )

        return FingerprintResponse(
            modality=Modality.image,
            fingerprint={
                "hash_hex": fp["hash_hex"],
                "hash_bits": fp["hash_bits"],
                "hash_size_bits": fp["hash_size_bits"],
            },
            registered=register,
            asset_id=assigned_id if register else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Image fingerprinting failed: {exc}") from exc


@app.post("/fingerprint/semantic/image")
async def fingerprint_semantic_image(
    file: UploadFile = File(...),
    register: bool = Form(False),
    asset_id: str | None = Form(None),
    source: str | None = Form(None),
) -> dict[str, Any]:
    try:
        registry = _registry()
        content = await file.read()
        semantic = semantic_fp.embed_from_bytes(content)

        assigned_id = asset_id or str(uuid.uuid4())
        if register:
            registry.register_semantic(
                asset_id=assigned_id,
                embedding=semantic["embedding"],
                metadata={
                    "modality": "image",
                    "semantic_only": True,
                    "filename": file.filename,
                    "source": source,
                    "semantic_embedding_dim": semantic["embedding_dim"],
                },
            )

        return {
            "modality": "image",
            "semantic_embedding_dim": semantic["embedding_dim"],
            "registered": register,
            "asset_id": assigned_id if register else None,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Semantic fingerprinting failed: {exc}") from exc


@app.post("/fingerprint/video", response_model=FingerprintResponse)
async def fingerprint_video(
    file: UploadFile = File(...),
    register: bool = Form(False),
    asset_id: str | None = Form(None),
    source: str | None = Form(None),
) -> FingerprintResponse:
    tmp_path = await _save_upload_to_temp(file, suffix=os.path.splitext(file.filename or "")[1])
    try:
        registry = _registry()
        fp = video_fp.fingerprint(tmp_path)

        assigned_id = asset_id or str(uuid.uuid4())
        if register:
            registry.register_video(
                asset_id=assigned_id,
                hash_bytes=fp["aggregate_hash_bytes"],
                metadata={
                    "modality": "video",
                    "filename": file.filename,
                    "source": source,
                    "frames_sampled": fp["frames_sampled"],
                },
            )

        return FingerprintResponse(
            modality=Modality.video,
            fingerprint={
                "frames_sampled": fp["frames_sampled"],
                "frame_hashes": fp["frame_hashes"],
                "aggregate_hash_hex": fp["aggregate_hash_hex"],
                "aggregate_hash_bits": fp["aggregate_hash_bits"],
                "hash_size_bits": fp["hash_size_bits"],
            },
            registered=register,
            asset_id=assigned_id if register else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Video fingerprinting failed: {exc}") from exc
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/fingerprint/audio", response_model=FingerprintResponse)
async def fingerprint_audio(
    file: UploadFile = File(...),
    register: bool = Form(False),
    asset_id: str | None = Form(None),
    source: str | None = Form(None),
) -> FingerprintResponse:
    tmp_path = await _save_upload_to_temp(file, suffix=os.path.splitext(file.filename or "")[1])
    try:
        registry = _registry()
        fp = audio_fp.fingerprint(tmp_path)

        assigned_id = asset_id or str(uuid.uuid4())
        if register:
            registry.register_audio(
                asset_id=assigned_id,
                embedding=fp["embedding"],
                metadata={
                    "modality": "audio",
                    "filename": file.filename,
                    "source": source,
                    "fingerprint_id": fp["fingerprint_id"],
                },
            )

        return FingerprintResponse(
            modality=Modality.audio,
            fingerprint={
                "embedding_dim": fp["embedding_dim"],
                "fingerprint_id": fp["fingerprint_id"],
                "top_landmarks": fp["top_landmarks"],
            },
            registered=register,
            asset_id=assigned_id if register else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Audio fingerprinting failed: {exc}") from exc
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/match", response_model=MatchResponse)
async def match_asset(
    modality: Modality = Form(...),
    file: UploadFile = File(...),
    top_k: int = Form(5),
) -> MatchResponse:
    if top_k < 1 or top_k > 50:
        raise HTTPException(status_code=400, detail="top_k must be between 1 and 50")

    try:
        registry = _registry()
        if modality == Modality.image:
            content = await file.read()
            fp = image_fp.fingerprint_from_bytes(content)
            results = registry.match_image(fp["hash_bytes"], top_k=top_k)
            explanation = _build_image_explanation(content=content, top_k=top_k)
            return _match_results_to_schema(
                modality=modality,
                results=results,
                query_summary={"hash_hex": fp["hash_hex"], "hash_size_bits": fp["hash_size_bits"]},
                explanation=explanation,
            )

        suffix = os.path.splitext(file.filename or "")[1]
        tmp_path = await _save_upload_to_temp(file, suffix=suffix)

        try:
            if modality == Modality.video:
                fp = video_fp.fingerprint(tmp_path)
                results = registry.match_video(fp["aggregate_hash_bytes"], top_k=top_k)
                return _match_results_to_schema(
                    modality=modality,
                    results=results,
                    query_summary={
                        "frames_sampled": fp["frames_sampled"],
                        "aggregate_hash_hex": fp["aggregate_hash_hex"],
                    },
                )

            if modality == Modality.audio:
                fp = audio_fp.fingerprint(tmp_path)
                results = registry.match_audio(fp["embedding"], top_k=top_k)
                return _match_results_to_schema(
                    modality=modality,
                    results=results,
                    query_summary={
                        "fingerprint_id": fp["fingerprint_id"],
                        "embedding_dim": fp["embedding_dim"],
                    },
                )

            raise HTTPException(status_code=400, detail="Unsupported modality")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Matching failed: {exc}") from exc


@app.post("/verify/image/slow-gate")
async def verify_image_slow_gate(
    file: UploadFile = File(...),
    top_k: int = Form(5),
    hamming_inconclusive_threshold: int = Form(20),
    semantic_alert_threshold: float = Form(0.85),
    modality_filter: str | None = Form(None),
) -> dict[str, Any]:
    """Two-stage verification pattern:

    IF stage-1 best Hamming distance > threshold (or no match):
        Trigger stage-2 semantic embedding and cosine matching.
        IF cosine similarity > semantic threshold:
            Mark as potential derivative/piracy.
    """
    if top_k < 1 or top_k > 50:
        raise HTTPException(status_code=400, detail="top_k must be between 1 and 50")

    try:
        registry = _registry()
        content = await file.read()
        image_hash = image_fp.fingerprint_from_bytes(content)
        fast_matches = registry.match_image(image_hash["hash_bytes"], top_k=top_k)

        best_hamming = fast_matches[0].distance_or_similarity if fast_matches else None
        should_trigger_semantic = best_hamming is None or best_hamming > hamming_inconclusive_threshold

        slow_gate = {
            "triggered": should_trigger_semantic,
            "semantic_threshold": semantic_alert_threshold,
            "matches": [],
            "potential_derivative_piracy": False,
        }

        if should_trigger_semantic:
            semantic = semantic_fp.embed_from_bytes(content)
            semantic_matches = registry.match_semantic(
                semantic["embedding"],
                top_k=top_k,
                modality_filter=modality_filter,
            )

            slow_gate["matches"] = [
                {
                    "asset_id": m.asset_id,
                    "cosine_similarity": m.distance_or_similarity,
                    "confidence": m.confidence,
                    "metadata": m.metadata,
                }
                for m in semantic_matches
            ]

            if semantic_matches and semantic_matches[0].distance_or_similarity > semantic_alert_threshold:
                slow_gate["potential_derivative_piracy"] = True

        return {
            "stage_1": {
                "hash_hex": image_hash["hash_hex"],
                "hamming_inconclusive_threshold": hamming_inconclusive_threshold,
                "best_hamming_distance": best_hamming,
                "matches": [
                    {
                        "asset_id": m.asset_id,
                        "hamming_distance": m.distance_or_similarity,
                        "confidence": m.confidence,
                        "metadata": m.metadata,
                    }
                    for m in fast_matches
                ],
            },
            "stage_2": slow_gate,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Slow-gate verification failed: {exc}") from exc


@app.post("/monitor/calibration/log")
async def log_calibration_sample(
    probability: float = Form(...),
    target: int = Form(...),
) -> dict[str, Any]:
    if probability < 0.0 or probability > 1.0:
        raise HTTPException(status_code=400, detail="probability must be in [0, 1]")
    if target not in (0, 1):
        raise HTTPException(status_code=400, detail="target must be 0 or 1")

    _log_calibration_sample(probability=probability, target=target)

    monitor = getattr(app.state, "calibration_monitor", {"preds": [], "targets": []})
    metrics = getattr(app.state, "metrics", None)
    if metrics is not None and len(monitor.get("preds", [])) >= 10:
        ece_value = _compute_ece(monitor["preds"], monitor["targets"], n_bins=10)
        metrics.set_ece(ece_value)

    return {
        "logged": True,
        "samples": len(monitor.get("preds", [])),
    }


@app.get("/metrics")
async def metrics() -> Response:
    return metrics_response()


@app.get("/health")
async def health() -> dict[str, Any]:
    registry = _registry()
    monitor = getattr(app.state, "calibration_monitor", {"preds": [], "targets": []})
    preds = monitor.get("preds", [])
    targets = monitor.get("targets", [])

    ece = _compute_ece(preds, targets, n_bins=10) if len(preds) >= 10 else None
    metrics = getattr(app.state, "metrics", None)
    if metrics is not None and ece is not None:
        metrics.set_ece(float(ece))

    return {
        "status": "ok",
        "registered": {
            "images": len(registry.image_ids),
            "videos": len(registry.video_ids),
            "audios": len(registry.audio_ids),
            "semantic_images": len(registry.semantic_ids),
        },
        "calibration": {
            "samples": len(preds),
            "ece_10_bins": ece,
        },
    }
