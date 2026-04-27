from __future__ import annotations

import hashlib

import librosa
import numpy as np


class AudioFingerprinter:
    """Landmark-style audio fingerprint with speed/pitch robustness.

    Core idea:
    1) Convert waveform to beat-synchronous `chroma_cens` features.
    2) Extract local chroma peaks per beat.
    3) Build landmarks from (anchor_peak, target_peak) pairs using:
       - relative chroma interval (mod 12) -> pitch-shift tolerant
       - beat-distance (not seconds) -> speed/time-scale tolerant
    4) Hash landmarks into a compact histogram embedding for vector search.

    This avoids heavy neural inference and remains fast on low-end CPUs.
    """

    def __init__(
        self,
        sample_rate: int = 22050,
        hop_length: int = 512,
        top_peaks_per_beat: int = 2,
        max_target_beats: int = 6,
        beat_delta_bins: int = 8,
    ) -> None:
        self.sample_rate = sample_rate
        self.hop_length = hop_length
        self.top_peaks_per_beat = top_peaks_per_beat
        self.max_target_beats = max_target_beats
        self.beat_delta_bins = beat_delta_bins
        self.embedding_dim = 12 * self.beat_delta_bins

    def _load_audio(self, audio_path: str) -> np.ndarray:
        try:
            y, _ = librosa.load(audio_path, sr=self.sample_rate, mono=True, dtype=np.float32)
        except Exception as exc:  # pragma: no cover - defensive path
            raise ValueError(f"Invalid or corrupt audio file: {exc}") from exc

        if y is None or y.size == 0:
            raise ValueError("Empty audio data")

        if np.max(np.abs(y)) < 1e-6:
            raise ValueError("Silent audio cannot be fingerprinted reliably")

        return y

    def _beat_sync_chroma(self, y: np.ndarray) -> np.ndarray:
        # HPSS improves robustness under reverb/noise by focusing pitch-rich harmonic part.
        y_harm, y_perc = librosa.effects.hpss(y)

        chroma = librosa.feature.chroma_cens(
            y=y_harm,
            sr=self.sample_rate,
            hop_length=self.hop_length,
        ).astype(np.float32)

        onset_env = librosa.onset.onset_strength(
            y=y_perc,
            sr=self.sample_rate,
            hop_length=self.hop_length,
        )
        _, beats = librosa.beat.beat_track(
            onset_envelope=onset_env,
            sr=self.sample_rate,
            hop_length=self.hop_length,
            units="frames",
        )

        # Fallback for weak beat tracks (ambient/audio with low rhythmic content).
        if beats is None or len(beats) < 4:
            frame_count = chroma.shape[1]
            step = max(frame_count // 32, 1)
            beats = np.arange(0, frame_count, step, dtype=int)

        beat_chroma = librosa.util.sync(chroma, beats, aggregate=np.median)

        # Vectorized L2 normalization for cosine-friendly embedding.
        norm = np.linalg.norm(beat_chroma, axis=0, keepdims=True) + 1e-8
        beat_chroma = beat_chroma / norm

        return beat_chroma.astype(np.float32)

    def _extract_landmarks(self, beat_chroma: np.ndarray) -> np.ndarray:
        if beat_chroma.shape[1] < 2:
            raise ValueError("Audio too short for stable fingerprint")

        # Top-k chroma peaks per beat using argpartition (faster than full sort).
        k = min(self.top_peaks_per_beat, beat_chroma.shape[0])
        peak_bins = np.argpartition(beat_chroma, -k, axis=0)[-k:, :]

        histogram = np.zeros(self.embedding_dim, dtype=np.float32)
        n_beats = beat_chroma.shape[1]

        for anchor_beat in range(n_beats - 1):
            anchor_bins = peak_bins[:, anchor_beat]
            end = min(anchor_beat + self.max_target_beats, n_beats)

            for target_beat in range(anchor_beat + 1, end):
                delta_beat = target_beat - anchor_beat
                delta_bin = min(delta_beat, self.beat_delta_bins - 1)
                target_bins = peak_bins[:, target_beat]

                # Pitch-shift invariance: use relative chroma interval modulo 12.
                intervals = (target_bins.reshape(1, -1) - anchor_bins.reshape(-1, 1)) % 12
                flat_intervals = intervals.reshape(-1)

                # Time-scale invariance: use beat distance (tempo-normalized), not seconds.
                idx = flat_intervals * self.beat_delta_bins + delta_bin
                np.add.at(histogram, idx, 1.0)

        total = histogram.sum()
        if total > 0:
            histogram /= total

        return histogram

    def fingerprint(self, audio_path: str) -> dict:
        y = self._load_audio(audio_path)
        beat_chroma = self._beat_sync_chroma(y)
        embedding = self._extract_landmarks(beat_chroma)

        # Stable compact id for diagnostics/traceability.
        digest = hashlib.sha256(embedding.tobytes()).hexdigest()[:16]

        top_idx = np.argsort(embedding)[-10:][::-1]
        top_landmarks = [
            {
                "interval": int(i // self.beat_delta_bins),
                "delta_beat_bin": int(i % self.beat_delta_bins),
                "score": float(embedding[i]),
            }
            for i in top_idx
            if embedding[i] > 0
        ]

        return {
            "embedding": embedding.astype(np.float32),
            "embedding_dim": int(self.embedding_dim),
            "fingerprint_id": digest,
            "top_landmarks": top_landmarks,
        }
