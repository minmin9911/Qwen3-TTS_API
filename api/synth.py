from __future__ import annotations

import gc
import io

import librosa
import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

from .models import SpeakerConfig


def _dtype_from_str(name: str) -> torch.dtype:
    mapping = {
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float16": torch.float16,
        "fp16": torch.float16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }
    if name not in mapping:
        raise ValueError(f"Unsupported dtype: {name}")
    return mapping[name]


def _load_audio(path: str) -> tuple[np.ndarray, int]:
    data, sr = sf.read(path)
    if isinstance(data, np.ndarray) and data.ndim > 1:
        data = np.mean(data, axis=-1)
    return data.astype(np.float32), int(sr)


class ModelManager:
    def __init__(self) -> None:
        self._models: dict[tuple[str, str, str, bool], Qwen3TTSModel] = {}

    def get_model(self, model_id: str, dtype: str, device: str, flash_attn: bool) -> Qwen3TTSModel:
        key = (model_id, dtype, device, flash_attn)
        if key in self._models:
            return self._models[key]
        attn_impl = "flash_attention_2" if flash_attn else None
        model = Qwen3TTSModel.from_pretrained(
            model_id,
            device_map=device,
            dtype=_dtype_from_str(dtype),
            attn_implementation=attn_impl,
        )
        self._models[key] = model
        return model

    def unload_all(self) -> None:
        self._models.clear()
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            try:
                torch.cuda.ipc_collect()
            except RuntimeError:
                pass


def generate_audio(
    manager: ModelManager,
    config: SpeakerConfig,
    text: str,
    query: dict,
    flash_attn: bool = False,
) -> tuple[np.ndarray, int]:
    model = manager.get_model(config.model_id, config.dtype, config.device, flash_attn)
    language = config.language or "Auto"

    if config.mode == "custom_voice":
        speaker = config.speaker
        if not speaker:
            supported = model.get_supported_speakers()
            if not supported:
                raise ValueError("No supported speakers available for custom_voice.")
            speaker = supported[0]
        wavs, sr = model.generate_custom_voice(
            text=text,
            language=language,
            speaker=speaker,
            instruct=config.instruct,
        )
    elif config.mode == "voice_design":
        if not config.instruct:
            raise ValueError("voice_design requires 'instruct' in speaker config.")
        wavs, sr = model.generate_voice_design(
            text=text,
            language=language,
            instruct=config.instruct,
        )
    else:
        if not config.ref_audio:
            raise ValueError("voice_clone requires 'ref_audio' in speaker config.")
        ref_audio = _load_audio(config.ref_audio)
        wavs, sr = model.generate_voice_clone(
            text=text,
            language=language,
            ref_audio=ref_audio,
            ref_text=config.ref_text,
            x_vector_only_mode=bool(config.x_vector_only_mode),
        )

    wav = np.asarray(wavs[0], dtype=np.float32)
    scale = 1.0
    query_scale = query.get("volumeScale")
    if isinstance(query_scale, (int, float)):
        scale *= float(query_scale)
    if config.volume_scale and config.volume_scale > 0:
        scale *= float(config.volume_scale)
    if scale != 1.0:
        wav = wav * scale
        wav = np.clip(wav, -1.0, 1.0)
    target_sr = query.get("outputSamplingRate")
    if isinstance(target_sr, int) and target_sr > 0 and target_sr != sr:
        wav = librosa.resample(wav, orig_sr=sr, target_sr=target_sr)
        sr = target_sr
    return wav, sr


def wav_bytes(wav: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, wav, sr, format="WAV")
    return buf.getvalue()
