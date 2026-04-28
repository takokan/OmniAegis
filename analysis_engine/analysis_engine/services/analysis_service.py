from __future__ import annotations

from dataclasses import dataclass

from ..domain.schemas import AnalysisResult, FrameHash, LogoDetection
from .fingerprint import FingerprintService
from .frame_sampler import FFmpegFrameSampler
from .logo_detector import LogoDetector


@dataclass(frozen=True)
class AnalysisInputs:
    asset_id: str
    url: str
    headers: dict[str, str]


class AnalysisService:
    def __init__(
        self,
        *,
        sampler: FFmpegFrameSampler,
        fingerprint: FingerprintService,
        logo_detector: LogoDetector,
        frame_sample_seconds: float,
        frame_fps: int,
        confidence_threshold: float,
    ) -> None:
        self.sampler = sampler
        self.fingerprint = fingerprint
        self.logo_detector = logo_detector
        self.frame_sample_seconds = frame_sample_seconds
        self.frame_fps = frame_fps
        self.confidence_threshold = confidence_threshold

    async def analyze(self, inputs: AnalysisInputs) -> AnalysisResult:
        sampled = await self.sampler.sample_frames(
            inputs.url,
            seconds=self.frame_sample_seconds,
            fps=self.frame_fps,
            headers=inputs.headers,
            timeout_seconds=10.0,
        )

        frame_hashes: list[FrameHash] = []
        detections: list[LogoDetection] = []
        best_fp_similarity = 0.0
        best_fp_truth_id = None

        for idx, frame in enumerate(sampled.frames_bgr):
            ph = self.fingerprint.phash_hex(frame)
            frame_hashes.append(FrameHash(index=idx, phash_hex=ph))

            match = self.fingerprint.compare_to_truth(ph)
            if match.best_similarity > best_fp_similarity:
                best_fp_similarity = match.best_similarity
                best_fp_truth_id = match.best_match_id

            for det in self.logo_detector.detect(frame):
                detections.append(
                    LogoDetection(
                        label=det.label,
                        confidence=det.confidence,
                        bbox_xyxy=det.bbox_xyxy,
                    )
                )

        # Aggregate: fingerprints dominate; logos raise confidence slightly.
        logo_bonus = 0.0
        if detections:
            logo_bonus = min(0.10, max(d.confidence for d in detections) * 0.10)

        confidence = float(min(1.0, max(0.0, best_fp_similarity + logo_bonus)))
        verdict = "match" if confidence >= self.confidence_threshold else ("no_match" if confidence <= 0.35 else "inconclusive")

        return AnalysisResult(
            asset_id=inputs.asset_id,
            url=inputs.url,
            confidence=confidence,
            verdict=verdict,  # type: ignore[arg-type]
            signals={
                "best_truth_id": best_fp_truth_id,
                "best_fp_similarity": best_fp_similarity,
                "logo_detections": len(detections),
                "frames_sampled": len(frame_hashes),
            },
            frame_hashes=frame_hashes,
            logo_detections=detections,
        )

