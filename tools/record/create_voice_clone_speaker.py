from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

try:
    import sounddevice as sd
except ImportError as exc:  # pragma: no cover
    raise SystemExit("sounddevice is not installed. Run `pip install sounddevice`.") from exc

BASE_DIR = Path(__file__).resolve().parents[2]
SPEAKERS_DIR = BASE_DIR / "api" / "speakers"
REF_DIR = SPEAKERS_DIR / "refAudio"

TARGET_RMS_DEFAULT = 0.1419159919

REFERENCE_TEXT = (
    "これは音声クローン用の参照音声です。"
    "自然な抑揚で、聞き取りやすい速度で読み上げます。"
    "今日は落ち着いて、丁寧に話します。"
)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", text.strip())
    slug = slug.strip("-").lower()
    return slug or "speaker"


def _next_speaker_id() -> int:
    max_id = 0
    for path in sorted(SPEAKERS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("speakerId"), int):
            max_id = max(max_id, int(data["speakerId"]))
    return max_id + 1


def _rms_active(audio: np.ndarray, silence_db: float = -45.0) -> float:
    if audio.size == 0:
        return 0.0
    threshold = 10 ** (silence_db / 20.0)
    active = audio[np.abs(audio) >= threshold]
    if active.size == 0:
        active = audio
    return float(np.sqrt(np.mean(np.square(active))))


def _load_mono(path: Path) -> tuple[np.ndarray, int]:
    data, sr = sf.read(str(path), always_2d=False)
    if isinstance(data, np.ndarray) and data.ndim > 1:
        data = np.mean(data, axis=1)
    return np.asarray(data, dtype=np.float32), int(sr)


def _resolve_target_rms(target_rms: float, volume_reference: str) -> tuple[float, str]:
    if volume_reference:
        path = Path(volume_reference)
        if path.exists():
            ref_audio, _ = _load_mono(path)
            ref_rms = _rms_active(ref_audio)
            if ref_rms > 1e-9:
                return ref_rms, str(path)
    return target_rms, "constant"


def _normalize_to_target_rms(audio: np.ndarray, target_rms: float) -> tuple[np.ndarray, float]:
    src_rms = _rms_active(audio)
    if src_rms <= 1e-9 or target_rms <= 1e-9:
        return audio, 1.0
    gain = target_rms / src_rms
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        gain = min(gain, 0.98 / peak)
    out = np.clip(audio * gain, -1.0, 1.0).astype(np.float32)
    return out, float(gain)


def _record_audio(sample_rate: int) -> np.ndarray:
    chunks: list[np.ndarray] = []

    def callback(indata: np.ndarray, frames: int, time_info: dict, status: object) -> None:
        del frames, time_info
        if status:
            print(f"[WARN] {status}")
        chunks.append(indata.copy())

    print("読み上げ文:")
    print(REFERENCE_TEXT)
    print("")
    print("準備ができたら Enter を押してください。")
    input("> ")
    print("録音開始。終了するときは Enter を押してください。")
    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        callback=callback,
    ):
        input("> ")

    if not chunks:
        raise SystemExit("録音データが取得できませんでした。")
    return np.asarray(np.concatenate(chunks, axis=0).reshape(-1), dtype=np.float32)


def _write_yaml(path: Path, speaker_id: int, name: str, slug: str, model_id: str) -> None:
    rel_audio = f"api/speakers/refAudio/{slug}.wav"
    data = {
        "speakerId": speaker_id,
        "name": name,
        "styleName": "ノーマル",
        "mode": "voice_clone",
        "modelId": model_id,
        "language": "Japanese",
        "refAudio": rel_audio,
        "refText": REFERENCE_TEXT,
        "xVectorOnlyMode": False,
        "volumeScale": 1.0,
        "dtype": "bfloat16",
        "device": "cuda:0",
    }
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="録音した参照音声を保存し、VoiceClone用 speaker YAML を生成します。"
    )
    parser.add_argument("--name", default="dummy_speaker", help="話者名")
    parser.add_argument("--slug", default=None, help="ファイル名識別子")
    parser.add_argument("--sample-rate", type=int, default=44100, help="録音サンプルレート")
    parser.add_argument(
        "--model-id",
        default="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        help="Qwen3-TTS modelId",
    )
    parser.add_argument(
        "--target-rms",
        type=float,
        default=TARGET_RMS_DEFAULT,
        help="録音音量を合わせる固定RMS値（既定は サンプルファイルの実測値）",
    )
    parser.add_argument(
        "--volume-reference",
        default="",
        help="任意: 基準WAV。指定時はその実測RMSで上書き",
    )
    args = parser.parse_args()

    slug = _slugify(args.slug or args.name)
    speaker_id = _next_speaker_id()

    REF_DIR.mkdir(parents=True, exist_ok=True)
    wav_path = REF_DIR / f"{slug}.wav"
    yaml_path = SPEAKERS_DIR / f"{slug}.yaml"

    print(f"speakerId: {speaker_id}")
    print(f"WAV: {wav_path}")
    print(f"YAML: {yaml_path}")

    audio = _record_audio(args.sample_rate)
    target_rms, source = _resolve_target_rms(args.target_rms, args.volume_reference)
    audio, gain = _normalize_to_target_rms(audio, target_rms)
    sf.write(str(wav_path), audio, args.sample_rate, subtype="PCM_16")
    _write_yaml(yaml_path, speaker_id, args.name, slug, args.model_id)

    print("完了しました。")
    print(f"target rms: {target_rms:.10f} (source: {source})")
    print(f"applied gain: {gain:.4f}")
    print(f"refAudio: api/speakers/refAudio/{slug}.wav")
    print(f"refText: {REFERENCE_TEXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
