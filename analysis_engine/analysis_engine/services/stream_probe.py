from __future__ import annotations

import asyncio
import json
import shlex
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class StreamProbeResult:
    playable_url: str
    extractor: str | None
    is_live: bool | None
    manifest_url: str | None


class StreamProbeService:
    """Resolve playable stream URLs quickly without full downloads."""

    def __init__(self, *, readiness_timeout_seconds: float = 10.0) -> None:
        self.readiness_timeout_seconds = readiness_timeout_seconds

    async def resolve_with_ytdlp(
        self,
        url: str,
        *,
        user_agent: str | None = None,
        proxy: str | None = None,
    ) -> StreamProbeResult:
        # Use yt-dlp JSON dump for rapid manifest resolution.
        cmd = ["yt-dlp", "--dump-json", "--no-download", "--no-warnings", "--skip-download", url]
        if user_agent:
            cmd.extend(["--user-agent", user_agent])
        if proxy:
            cmd.extend(["--proxy", proxy])

        try:
            raw = await asyncio.wait_for(asyncio.to_thread(self._run, cmd), timeout=self.readiness_timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"yt-dlp probe timed out after {self.readiness_timeout_seconds}s") from exc

        data = json.loads(raw)
        manifest_url = data.get("manifest_url") or data.get("url")
        playable = data.get("url") or manifest_url or url
        return StreamProbeResult(
            playable_url=str(playable),
            extractor=data.get("extractor"),
            is_live=data.get("is_live"),
            manifest_url=str(manifest_url) if manifest_url else None,
        )

    @staticmethod
    def _run(cmd: list[str]) -> str:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"Command failed rc={proc.returncode}: {shlex.join(cmd)} :: {proc.stderr.strip()[:400]}")
        return proc.stdout.strip()

