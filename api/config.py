from __future__ import annotations

import uuid
from pathlib import Path

import yaml

from .models import SpeakerConfig

BASE_DIR = Path(__file__).resolve().parents[1]
SPEAKERS_DIR = BASE_DIR / "api" / "speakers"

_cached_store: SpeakersStore | None = None
_cached_mtime: float | None = None


class SpeakersStore:
    def __init__(self, speakers: list[SpeakerConfig]) -> None:
        self._speakers = speakers
        self._by_id: dict[int, SpeakerConfig] = {}
        for speaker in speakers:
            if speaker.speaker_id in self._by_id:
                raise ValueError(f"Duplicate speaker id: {speaker.speaker_id}")
            self._by_id[speaker.speaker_id] = speaker

    def get(self, speaker_id: int) -> SpeakerConfig:
        if speaker_id not in self._by_id:
            raise KeyError(f"Unknown speaker id: {speaker_id}")
        return self._by_id[speaker_id]

    def has(self, speaker_id: int) -> bool:
        return speaker_id in self._by_id

    def to_voicevox_speakers(self) -> list[dict]:
        grouped: dict[str, list[SpeakerConfig]] = {}
        for speaker in self._speakers:
            grouped.setdefault(speaker.name, []).append(speaker)

        result: list[dict] = []
        for name, styles in grouped.items():
            speaker_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"qwen3tts:{name}"))
            result.append(
                {
                    "name": name,
                    "speaker_uuid": speaker_uuid,
                    "styles": [
                        {"id": style.speaker_id, "name": style.style_name or "default"}
                        for style in sorted(styles, key=lambda s: s.speaker_id)
                    ],
                    "version": "0.0.1",
                }
            )
        return result


def load_speakers(path: Path | None = None) -> SpeakersStore:
    speakers: list[SpeakerConfig] = []
    if path is None:
        if not SPEAKERS_DIR.exists():
            raise FileNotFoundError(f"Speakers directory not found: {SPEAKERS_DIR}")
        paths = sorted(SPEAKERS_DIR.glob("*.yaml"))
        if not paths:
            raise FileNotFoundError(f"No speaker yaml files found in: {SPEAKERS_DIR}")
    else:
        paths = [path]

    for config_path in paths:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = [data]
        else:
            raise ValueError(f"Invalid speaker config: {config_path}")
        speakers.extend(SpeakerConfig.model_validate(item) for item in items)

    for speaker in speakers:
        if speaker.ref_audio:
            ref_path = Path(speaker.ref_audio)
            if not ref_path.is_absolute():
                speaker.ref_audio = str((BASE_DIR / ref_path).resolve())
    return SpeakersStore(speakers)


def _latest_mtime(paths: list[Path]) -> float:
    return max(p.stat().st_mtime for p in paths)


def load_speakers_cached() -> SpeakersStore:
    global _cached_store, _cached_mtime

    if not SPEAKERS_DIR.exists():
        raise FileNotFoundError(f"Speakers directory not found: {SPEAKERS_DIR}")
    paths = sorted(SPEAKERS_DIR.glob("*.yaml"))
    if not paths:
        raise FileNotFoundError(f"No speaker yaml files found in: {SPEAKERS_DIR}")

    latest = _latest_mtime(paths)
    if _cached_store is None or _cached_mtime is None or latest != _cached_mtime:
        _cached_store = load_speakers()
        _cached_mtime = latest
    return _cached_store
