from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from importlib import import_module
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware


def _bootstrap_env() -> None:
    current = Path(__file__).resolve()
    decision_layer_root = current.parents[1]
    workspace_root = decision_layer_root.parent

    for env_path in (workspace_root / ".env", decision_layer_root / ".env"):
        if not env_path.exists():
            continue

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_bootstrap_env()

from app.config import QdrantClientSingleton, load_qdrant_settings
from app.auth_api import router as auth_router
from app.batch_api import router as batch_router
from app.fingerprinters import AudioFingerprinter, ImageFingerprinter, SemanticEmbedder, VideoFingerprinter
from app.hitl_api import router as hitl_router
from app.xai_api import router as xai_router
from app.registry import RegistryManager
from app.schemas import FingerprintResponse, MatchItem, MatchResponse, Modality

try:
    from decision_layer.services.audit_service import LocalPrivateKeySigner
    from decision_layer.services.batch_coordinator import BatchCoordinator, BatchCoordinatorConfig
    from decision_layer.services.graph_db import GraphDBService
    from decision_layer.services.hitl_monitor import HITLMonitorService
    from decision_layer.services.monitoring import MetricsRegistry, PrometheusMiddleware, metrics_response
    from decision_layer.services.xai_storage import ExplainabilityStorage
    from decision_layer.services.xai_umap import UMAPProjector
    from decision_layer.shared import (
        check_connections,
        close_db_clients,
        get_neo4j_driver,
        get_postgres_pool,
        get_redis_client,
    )
except ModuleNotFoundError:  # pragma: no cover
    from services.audit_service import LocalPrivateKeySigner
    from services.batch_coordinator import BatchCoordinator, BatchCoordinatorConfig
    from services.graph_db import GraphDBService
    from services.hitl_monitor import HITLMonitorService
    from services.monitoring import MetricsRegistry, PrometheusMiddleware, metrics_response
    from services.xai_storage import ExplainabilityStorage
    from services.xai_umap import UMAPProjector
    from shared import check_connections, close_db_clients, get_neo4j_driver, get_postgres_pool, get_redis_client


logger = logging.getLogger(__name__)

image_fp = ImageFingerprinter()
video_fp = VideoFingerprinter(frames_to_sample=16)
audio_fp = AudioFingerprinter()
semantic_fp = SemanticEmbedder(embedding_dim=512)
GLOBAL_METRICS = MetricsRegistry()
gateway_router = APIRouter(tags=["gateway"])


def _build_batch_signer() -> LocalPrivateKeySigner | None:
    private_key = os.getenv("POLYGON_PRIVATE_KEY")
    if not private_key:
        return None
    return LocalPrivateKeySigner(private_key)


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    skip_dependency_check = _is_truthy(os.getenv("SKIP_STARTUP_DEPENDENCY_CHECK"))
    if not skip_dependency_check:
        try:
            await check_connections()
        except Exception as exc:
            logger.critical("Cloud dependency health check failed during startup: %s", exc)
            raise RuntimeError("Startup aborted: cloud dependencies are unavailable") from exc
    else:
        logger.warning("Skipping startup dependency checks due to SKIP_STARTUP_DEPENDENCY_CHECK")

    try:
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
    except Exception as exc:
        logger.warning("Registry initialization skipped: %s", exc)
        app.state.registry = None
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

    hitl_monitor = None
    hitl_stop_event = None
    hitl_maintenance_task = None
    try:
        hitl_monitor = HITLMonitorService(graph_db=graph_db)
        hitl_stop_event = asyncio.Event()
        hitl_maintenance_task = asyncio.create_task(hitl_monitor.run_maintenance_loop(hitl_stop_event))
    except Exception as exc:
        logger.warning("HITL monitor initialization skipped: %s", exc)

    app.state.hitl_monitor = hitl_monitor
    app.state.hitl_stop_event = hitl_stop_event
    app.state.hitl_maintenance_task = hitl_maintenance_task

    batch_signer = _build_batch_signer()
    batch_coordinator = None
    try:
        if batch_signer is not None and os.getenv("MERKLE_ANCHOR_CONTRACT"):
            batch_coordinator = BatchCoordinator(
                signer=batch_signer,
                config=BatchCoordinatorConfig.from_env(),
            )
            await batch_coordinator.start()
    except Exception:
        batch_coordinator = None
    app.state.batch_coordinator = batch_coordinator

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

    xai_storage = None
    umap_projector = None
    try:
        xai_storage = ExplainabilityStorage.from_env()
        app.state.xai_storage = xai_storage
    except Exception:
        app.state.xai_storage = None

    try:
        umap_projector = UMAPProjector.from_env()
        app.state.umap_projector = umap_projector
    except Exception:
        app.state.umap_projector = None

    try:
        yield
    finally:
        if getattr(app.state, "batch_coordinator", None) is not None:
            await app.state.batch_coordinator.stop()

        stop_event = getattr(app.state, "hitl_stop_event", None)
        maintenance_task = getattr(app.state, "hitl_maintenance_task", None)
        if stop_event is not None:
            stop_event.set()
        if maintenance_task is not None:
            maintenance_task.cancel()
            try:
                await maintenance_task
            except asyncio.CancelledError:
                pass

        hitl_monitor = getattr(app.state, "hitl_monitor", None)
        if hitl_monitor is not None:
            hitl_monitor.close()

        xai_storage = getattr(app.state, "xai_storage", None)
        if xai_storage is not None:
            xai_storage.close()

        umap_projector = getattr(app.state, "umap_projector", None)
        if umap_projector is not None:
            umap_projector.close()

        if app.state.graph_db is not None:
            app.state.graph_db.close()

        await close_db_clients()
        QdrantClientSingleton.close_client()


app = FastAPI(
    title="OmniAegis Fingerprinting & Verification Gate",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS for frontend access
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173").split(",")
cors_origins = [origin.strip() for origin in cors_origins if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.add_middleware(PrometheusMiddleware, metrics=GLOBAL_METRICS)
app.include_router(auth_router)
app.include_router(batch_router)
app.include_router(hitl_router)
app.include_router(xai_router)


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


def _normalize_user_id(user_id: str | None, *, required: bool = True) -> str | None:
    normalized = (user_id or "").strip()
    if required and not normalized:
        raise HTTPException(status_code=400, detail="user_id is required")
    return normalized or None


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


def _build_image_explanation(content: bytes, top_k: int, owner_user_id: str | None = None) -> dict[str, Any]:
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
        semantic_matches = registry.match_semantic(
            semantic["embedding"],
            top_k=top_k,
            modality_filter="image",
            owner_user_id=owner_user_id,
        )
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
    user_id: str | None = Form(None),
) -> FingerprintResponse:
    try:
        registry = _registry()
        content = await file.read()
        fp = image_fp.fingerprint_from_bytes(content)
        owner_user_id = _normalize_user_id(user_id, required=register)

        assigned_id = asset_id or str(uuid.uuid4())
        if register:
            registry.register_image(
                asset_id=assigned_id,
                hash_bytes=fp["hash_bytes"],
                metadata={
                    "modality": "image",
                    "filename": file.filename,
                    "source": source,
                    "user_id": owner_user_id,
                },
            )

            # Stage-2 semantic registration for derivative-work matching.
            semantic = semantic_fp.embed_from_bytes(content)
            registry.register_semantic(
                asset_id=assigned_id,
                embedding=semantic["embedding"],
                metadata={
                    "modality": "image",
                    "semantic_embedding_dim": semantic["embedding_dim"],
                    "source": source,
                    "filename": file.filename,
                    "user_id": owner_user_id,
                },
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
    user_id: str | None = Form(None),
) -> dict[str, Any]:
    try:
        registry = _registry()
        content = await file.read()
        semantic = semantic_fp.embed_from_bytes(content)
        owner_user_id = _normalize_user_id(user_id, required=register)

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
                    "user_id": owner_user_id,
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
    user_id: str | None = Form(None),
) -> FingerprintResponse:
    tmp_path = await _save_upload_to_temp(file, suffix=os.path.splitext(file.filename or "")[1])
    try:
        registry = _registry()
        fp = video_fp.fingerprint(tmp_path)
        owner_user_id = _normalize_user_id(user_id, required=register)

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
                    "user_id": owner_user_id,
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
    user_id: str | None = Form(None),
) -> FingerprintResponse:
    tmp_path = await _save_upload_to_temp(file, suffix=os.path.splitext(file.filename or "")[1])
    try:
        registry = _registry()
        fp = audio_fp.fingerprint(tmp_path)
        owner_user_id = _normalize_user_id(user_id, required=register)

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
                    "user_id": owner_user_id,
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
    user_id: str = Form(...),
) -> MatchResponse:
    if top_k < 1 or top_k > 50:
        raise HTTPException(status_code=400, detail="top_k must be between 1 and 50")

    try:
        registry = _registry()
        owner_user_id = _normalize_user_id(user_id, required=True)
        if modality == Modality.image:
            content = await file.read()
            fp = image_fp.fingerprint_from_bytes(content)
            results = registry.match_image(fp["hash_bytes"], top_k=top_k, owner_user_id=owner_user_id)
            explanation = _build_image_explanation(content=content, top_k=top_k, owner_user_id=owner_user_id)
            return _match_results_to_schema(
                modality=modality,
                results=results,
                query_summary={
                    "hash_hex": fp["hash_hex"],
                    "hash_size_bits": fp["hash_size_bits"],
                    "user_id": owner_user_id,
                },
                explanation=explanation,
            )

        suffix = os.path.splitext(file.filename or "")[1]
        tmp_path = await _save_upload_to_temp(file, suffix=suffix)

        try:
            if modality == Modality.video:
                fp = video_fp.fingerprint(tmp_path)
                results = registry.match_video(
                    fp["aggregate_hash_bytes"],
                    top_k=top_k,
                    owner_user_id=owner_user_id,
                )
                return _match_results_to_schema(
                    modality=modality,
                    results=results,
                    query_summary={
                        "frames_sampled": fp["frames_sampled"],
                        "aggregate_hash_hex": fp["aggregate_hash_hex"],
                        "user_id": owner_user_id,
                    },
                )

            if modality == Modality.audio:
                fp = audio_fp.fingerprint(tmp_path)
                results = registry.match_audio(fp["embedding"], top_k=top_k, owner_user_id=owner_user_id)
                return _match_results_to_schema(
                    modality=modality,
                    results=results,
                    query_summary={
                        "fingerprint_id": fp["fingerprint_id"],
                        "embedding_dim": fp["embedding_dim"],
                        "user_id": owner_user_id,
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
    user_id: str = Form(...),
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
        owner_user_id = _normalize_user_id(user_id, required=True)
        content = await file.read()
        image_hash = image_fp.fingerprint_from_bytes(content)
        fast_matches = registry.match_image(
            image_hash["hash_bytes"],
            top_k=top_k,
            owner_user_id=owner_user_id,
        )

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
                owner_user_id=owner_user_id,
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
                "user_id": owner_user_id,
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


async def _measure_cloud_latency_ms(fn: Any) -> tuple[str, float | None, str | None]:
    start = time.perf_counter()
    try:
        await fn()
        latency_ms = (time.perf_counter() - start) * 1000.0
        return "ok", round(latency_ms, 2), None
    except Exception as exc:  # pragma: no cover - runtime/network dependent
        latency_ms = (time.perf_counter() - start) * 1000.0
        return "down", round(latency_ms, 2), str(exc)


async def _cloud_health_status() -> dict[str, Any]:
    redis_client = await get_redis_client()
    postgres_pool = await get_postgres_pool()
    neo4j_driver = await get_neo4j_driver()

    async def _redis_probe() -> None:
        pong = await redis_client.ping()
        if pong is not True:
            raise RuntimeError("unexpected PING response")

    async def _postgres_probe() -> None:
        async with postgres_pool.acquire() as conn:
            value = await conn.fetchval("SELECT 1")
            if value != 1:
                raise RuntimeError("unexpected SELECT 1 result")

    async def _neo4j_probe() -> None:
        async with neo4j_driver.session() as session:
            result = await session.run("RETURN 1 AS ok")
            record = await result.single()
            if record is None or record.get("ok") != 1:
                raise RuntimeError("unexpected Neo4j query result")

    redis_status, redis_latency, redis_error = await _measure_cloud_latency_ms(_redis_probe)
    postgres_status, postgres_latency, postgres_error = await _measure_cloud_latency_ms(_postgres_probe)
    neo4j_status, neo4j_latency, neo4j_error = await _measure_cloud_latency_ms(_neo4j_probe)

    services = {
        "redis": {
            "status": redis_status,
            "latency_ms": redis_latency,
            "error": redis_error,
        },
        "postgres": {
            "status": postgres_status,
            "latency_ms": postgres_latency,
            "error": postgres_error,
        },
        "neo4j": {
            "status": neo4j_status,
            "latency_ms": neo4j_latency,
            "error": neo4j_error,
        },
    }

    overall = "ok" if all(s["status"] == "ok" for s in services.values()) else "degraded"
    return {"status": overall, "services": services}


@gateway_router.get("/health")
async def health() -> dict[str, Any]:
    registry = _registry()
    monitor = getattr(app.state, "calibration_monitor", {"preds": [], "targets": []})
    preds = monitor.get("preds", [])
    targets = monitor.get("targets", [])
    cloud = await _cloud_health_status()

    ece = _compute_ece(preds, targets, n_bins=10) if len(preds) >= 10 else None
    metrics = getattr(app.state, "metrics", None)
    if metrics is not None and ece is not None:
        metrics.set_ece(float(ece))

    return {
        "status": cloud["status"],
        "cloud": cloud["services"],
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


app.include_router(gateway_router)
