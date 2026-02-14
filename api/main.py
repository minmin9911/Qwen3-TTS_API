from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from .aivis_proxy import AivisProxy
from .config import SpeakersStore, load_speakers_cached
from .models import VoicevoxAudioQuery
from .synth import ModelManager, generate_audio, wav_bytes

app = FastAPI(title="Qwen3-TTS VOICEVOX-Compatible API")

_speaker_store: SpeakersStore | None = None
_model_manager: ModelManager | None = None
_aivis_proxy: AivisProxy | None = None
_idle_task: asyncio.Task[None] | None = None
_state_lock = asyncio.Lock()
_active_qwen_requests = 0
_last_qwen_access = time.monotonic()

_JST = timezone(timedelta(hours=9), name="JST")
_IDLE_UNLOAD_SEC = int(os.getenv("QWEN_IDLE_UNLOAD_SEC", "420"))
_IDLE_CHECK_SEC = int(os.getenv("QWEN_IDLE_CHECK_SEC", "10"))


class _JSTFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        if datefmt:
            return datetime.fromtimestamp(record.created, _JST).strftime(datefmt)
        return datetime.fromtimestamp(record.created, _JST).isoformat(timespec="seconds")


def _configure_logging_jst() -> None:
    datefmt = "%Y-%m-%d %H:%M:%S %Z"
    fmt = "%(asctime)s %(levelname)s: %(message)s"
    formatter = _JSTFormatter(fmt=fmt, datefmt=datefmt)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        for handler in logger.handlers:
            handler.setFormatter(formatter)


_configure_logging_jst()
_logger = logging.getLogger("uvicorn.error")


def get_speaker_store() -> SpeakersStore:
    global _speaker_store
    _speaker_store = load_speakers_cached()
    return _speaker_store


def get_model_manager() -> ModelManager:
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager


def get_aivis_proxy() -> AivisProxy:
    global _aivis_proxy
    if _aivis_proxy is None:
        _aivis_proxy = AivisProxy()
    return _aivis_proxy


async def _mark_qwen_access_start() -> None:
    global _active_qwen_requests, _last_qwen_access
    async with _state_lock:
        _active_qwen_requests += 1
        _last_qwen_access = time.monotonic()


async def _mark_qwen_access_end() -> None:
    global _active_qwen_requests, _last_qwen_access
    async with _state_lock:
        _active_qwen_requests = max(0, _active_qwen_requests - 1)
        _last_qwen_access = time.monotonic()


async def _idle_unload_loop() -> None:
    global _model_manager
    while True:
        await asyncio.sleep(max(1, _IDLE_CHECK_SEC))
        async with _state_lock:
            manager = _model_manager
            active = _active_qwen_requests
            idle_for = time.monotonic() - _last_qwen_access
        if manager is None or active > 0 or idle_for < _IDLE_UNLOAD_SEC:
            continue
        manager.unload_all()
        async with _state_lock:
            if _active_qwen_requests == 0 and _model_manager is manager:
                _model_manager = None
                _logger.info(
                    "Qwen model unloaded after %ss idle.",
                    _IDLE_UNLOAD_SEC,
                )


@app.on_event("startup")
async def _startup_event() -> None:
    global _idle_task
    if _IDLE_UNLOAD_SEC <= 0:
        _logger.info("Qwen idle unload disabled (QWEN_IDLE_UNLOAD_SEC=%s).", _IDLE_UNLOAD_SEC)
        return
    _idle_task = asyncio.create_task(_idle_unload_loop())
    _logger.info(
        "Qwen idle unload enabled: idle=%ss check=%ss",
        _IDLE_UNLOAD_SEC,
        _IDLE_CHECK_SEC,
    )


@app.on_event("shutdown")
async def _shutdown_event() -> None:
    global _idle_task, _model_manager
    if _idle_task is not None:
        _idle_task.cancel()
        try:
            await _idle_task
        except asyncio.CancelledError:
            pass
        _idle_task = None
    if _model_manager is not None:
        _model_manager.unload_all()
        _model_manager = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/speakers")
async def speakers(
    store: SpeakersStore = Depends(get_speaker_store),
    proxy: AivisProxy = Depends(get_aivis_proxy),
) -> list[dict]:
    qwen_list = store.to_voicevox_speakers()
    settings = await proxy.ensure_ready()
    if settings is None:
        return qwen_list

    url = f"{settings.base_url}/speakers"
    async def _fetch_speakers(target_url: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.get(target_url)

    try:
        resp = await _fetch_speakers(url)
    except httpx.HTTPError:
        recovered = await proxy.recover_and_wait()
        if recovered is None:
            return qwen_list
        retry_url = f"{recovered.base_url}/speakers"
        try:
            resp = await _fetch_speakers(retry_url)
        except httpx.HTTPError:
            return qwen_list

    if resp.status_code != 200:
        recovered = await proxy.recover_and_wait()
        if recovered is None:
            return qwen_list
        retry_url = f"{recovered.base_url}/speakers"
        try:
            resp = await _fetch_speakers(retry_url)
        except httpx.HTTPError:
            return qwen_list
        if resp.status_code != 200:
            return qwen_list

    try:
        data = resp.json()
    except ValueError:
        return qwen_list
    if isinstance(data, list):
        return data + qwen_list
    return qwen_list


@app.post("/audio_query")
async def audio_query(
    text: str = Query(..., min_length=1),
    speaker: int = Query(..., ge=0),
    store: SpeakersStore = Depends(get_speaker_store),
    proxy: AivisProxy = Depends(get_aivis_proxy),
) -> dict[str, Any]:
    if not store.has(speaker):
        t0 = time.perf_counter()
        settings = await proxy.ensure_ready()
        t1 = time.perf_counter()
        if settings is None:
            raise HTTPException(status_code=503, detail="AivisSpeech is not available.")
        url = f"{settings.base_url}/audio_query"
        t2 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(url, params={"text": text, "speaker": speaker})
        except httpx.HTTPError as exc:
            recovered = await proxy.recover_and_wait()
            if recovered is None:
                raise HTTPException(
                    status_code=503,
                    detail=f"AivisSpeech request failed: {exc}",
                ) from exc
            retry_url = f"{recovered.base_url}/audio_query"
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    resp = await client.post(
                        retry_url,
                        params={"text": text, "speaker": speaker},
                    )
            except httpx.HTTPError as retry_exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"AivisSpeech request failed after recovery: {retry_exc}",
                ) from retry_exc
        t3 = time.perf_counter()
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        headers = {
            "X-Bench-TotalMs": f"{(t3 - t0) * 1000:.3f}",
            "X-Bench-ReadyMs": f"{(t1 - t0) * 1000:.3f}",
            "X-Bench-ProxyMs": f"{(t3 - t2) * 1000:.3f}",
        }
        return JSONResponse(content=resp.json(), headers=headers)
    query = VoicevoxAudioQuery(text=text, speaker=speaker)
    return query.model_dump()


@app.post("/synthesis")
async def synthesis(
    request: Request,
    speaker: int = Query(..., ge=0),
    store: SpeakersStore = Depends(get_speaker_store),
    manager: ModelManager = Depends(get_model_manager),
    proxy: AivisProxy = Depends(get_aivis_proxy),
) -> Response:
    try:
        query: dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    if not store.has(speaker):
        t0 = time.perf_counter()
        settings = await proxy.ensure_ready()
        t1 = time.perf_counter()
        if settings is None:
            raise HTTPException(status_code=503, detail="AivisSpeech is not available.")
        url = f"{settings.base_url}/synthesis"
        t2 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                resp = await client.post(
                    url,
                    params={"speaker": speaker},
                    json=query,
                    headers={"Content-Type": "application/json"},
                )
        except httpx.HTTPError as exc:
            recovered = await proxy.recover_and_wait()
            if recovered is None:
                raise HTTPException(
                    status_code=503,
                    detail=f"AivisSpeech request failed: {exc}",
                ) from exc
            retry_url = f"{recovered.base_url}/synthesis"
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    resp = await client.post(
                        retry_url,
                        params={"speaker": speaker},
                        json=query,
                        headers={"Content-Type": "application/json"},
                    )
            except httpx.HTTPError as retry_exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"AivisSpeech request failed after recovery: {retry_exc}",
                ) from retry_exc
        t3 = time.perf_counter()
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        media_type = resp.headers.get("content-type", "audio/wav")
        headers = {
            "X-Bench-TotalMs": f"{(t3 - t0) * 1000:.3f}",
            "X-Bench-ReadyMs": f"{(t1 - t0) * 1000:.3f}",
            "X-Bench-ProxyMs": f"{(t3 - t2) * 1000:.3f}",
        }
        return Response(content=resp.content, media_type=media_type, headers=headers)

    text = query.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=422, detail="Query must include non-empty 'text'.")

    try:
        config = store.get(speaker)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await _mark_qwen_access_start()
    try:
        wav, sr = generate_audio(manager, config, text.strip(), query)
    finally:
        await _mark_qwen_access_end()
    return Response(content=wav_bytes(wav, sr), media_type="audio/wav")


def create_app() -> FastAPI:
    return app
