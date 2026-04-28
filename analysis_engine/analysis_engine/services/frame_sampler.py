from __future__ import annotations

import asyncio
import shlex
import subprocess
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class SampledFrames:
    frames_bgr: list[np.ndarray]


class FFmpegFrameSampler:
    def __init__(self, *, ffmpeg_path: str = "ffmpeg") -> None:
        self.ffmpeg_path = ffmpeg_path

    async def sample_frames(
        self,
        url: str,
        *,
        seconds: float = 2.0,
        fps: int = 1,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 10.0,
    ) -> SampledFrames:
        # image2pipe, jpeg frames to stdout
        header_blob = ""
        if headers:
            header_blob = "".join(f"{k}: {v}\r\n" for k, v in headers.items())

        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-headers",
            header_blob,
            "-i",
            url,
            "-t",
            str(seconds),
            "-vf",
            f"fps={fps}",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "pipe:1",
        ]

        try:
            out = await asyncio.wait_for(asyncio.to_thread(self._run_bytes, cmd), timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"ffmpeg sampling timed out after {timeout_seconds}s") from exc

        frames = self._decode_mjpeg_stream(out)
        return SampledFrames(frames_bgr=frames)

    @staticmethod
    def _run_bytes(cmd: list[str]) -> bytes:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed rc={proc.returncode}: {shlex.join(cmd)} :: {proc.stderr[:400]!r}")
        return proc.stdout

    @staticmethod
    def _decode_mjpeg_stream(blob: bytes) -> list[np.ndarray]:
        # Split MJPEG by JPEG SOI/EOI markers.
        frames: list[np.ndarray] = []
        soi = b"\xff\xd8"
        eoi = b"\xff\xd9"
        i = 0
        n = len(blob)
        while i < n:
            s = blob.find(soi, i)
            if s == -1:
                break
            e = blob.find(eoi, s)
            if e == -1:
                break
            jpg = blob[s : e + 2]
            i = e + 2
            arr = np.frombuffer(jpg, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                frames.append(img)
        return frames

