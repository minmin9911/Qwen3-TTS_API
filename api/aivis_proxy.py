from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config.yaml"

_cached_config: dict[str, Any] | None = None
_cached_mtime: float | None = None


def _load_config() -> dict[str, Any]:
    global _cached_config, _cached_mtime

    if not CONFIG_PATH.exists():
        _cached_config = {}
        _cached_mtime = None
        return {}

    mtime = CONFIG_PATH.stat().st_mtime
    if _cached_config is None or _cached_mtime is None or mtime != _cached_mtime:
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        _cached_config = data if isinstance(data, dict) else {}
        _cached_mtime = mtime
    return _cached_config


@dataclass
class AivisSettings:
    base_url: str
    exe_path: str | None
    startup_timeout_sec: int
    poll_interval_sec: float


def get_aivis_settings() -> AivisSettings:
    cfg = _load_config().get("aivis", {})
    if not isinstance(cfg, dict):
        cfg = {}
    base_url = cfg.get("baseUrl") or "http://127.0.0.1:10101"
    exe_path = cfg.get("exePath")
    timeout = int(cfg.get("startupTimeoutSec") or 120)
    interval = float(cfg.get("pollIntervalSec") or 1.0)
    return AivisSettings(
        base_url=base_url,
        exe_path=exe_path,
        startup_timeout_sec=timeout,
        poll_interval_sec=interval,
    )


class AivisProxy:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def _is_ready(self, base_url: str) -> bool:
        url = f"{base_url}/speakers"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def ensure_ready(self) -> AivisSettings | None:
        return get_aivis_settings()

    async def recover_and_wait(self) -> AivisSettings | None:
        settings = get_aivis_settings()
        if not settings.exe_path:
            return None

        async with self._lock:
            if await self._is_ready(settings.base_url):
                return settings

            if Path(settings.exe_path).exists():
                subprocess.Popen(
                    [settings.exe_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                return None

            deadline = asyncio.get_event_loop().time() + settings.startup_timeout_sec
            while asyncio.get_event_loop().time() < deadline:
                if await self._is_ready(settings.base_url):
                    return settings
                await asyncio.sleep(settings.poll_interval_sec)
            return None

    async def proxy(self, settings: AivisSettings, request: httpx.Request) -> httpx.Response:
        async with httpx.AsyncClient(timeout=None) as client:
            return await client.send(request, stream=True)
