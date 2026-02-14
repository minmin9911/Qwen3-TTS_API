from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf


def load_mono(path: Path) -> tuple[np.ndarray, int]:
    data, sr = sf.read(str(path), always_2d=False)
    if isinstance(data, np.ndarray) and data.ndim > 1:
        data = np.mean(data, axis=1)
    return np.asarray(data, dtype=np.float32), int(sr)


def rms_active(audio: np.ndarray, silence_db: float = -45.0) -> float:
    if audio.size == 0:
        return 0.0
    threshold = 10 ** (silence_db / 20.0)
    active = audio[np.abs(audio) >= threshold]
    if active.size == 0:
        active = audio
    return float(np.sqrt(np.mean(np.square(active))))


def normalize_to_target(audio: np.ndarray, target_rms: float) -> tuple[np.ndarray, float]:
    src_rms = rms_active(audio)
    if src_rms <= 1e-9 or target_rms <= 1e-9:
        return audio, 1.0
    gain = target_rms / src_rms
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        gain = min(gain, 0.98 / peak)
    out = np.clip(audio * gain, -1.0, 1.0).astype(np.float32)
    return out, float(gain)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--targets", nargs="+", required=True)
    parser.add_argument("--backup-suffix", default=".bak")
    args = parser.parse_args()

    ref_path = Path(args.reference)
    ref_audio, _ = load_mono(ref_path)
    target_rms = rms_active(ref_audio)
    print(f"reference: {ref_path}")
    print(f"target_rms: {target_rms:.10f}")

    for target in args.targets:
        path = Path(target)
        audio, sr = load_mono(path)
        before = rms_active(audio)
        normalized, gain = normalize_to_target(audio, target_rms)
        after = rms_active(normalized)

        backup = path.with_suffix(path.suffix + args.backup_suffix)
        shutil.copy2(path, backup)
        sf.write(str(path), normalized, sr, subtype="PCM_16")
        print(
            f"{path.name}: before={before:.10f} after={after:.10f} "
            f"gain={gain:.6f} backup={backup.name}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
