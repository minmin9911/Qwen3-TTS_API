from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SpeakerConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    speaker_id: int = Field(alias="speakerId")
    name: str
    style_name: str = Field(alias="styleName")
    mode: Literal["custom_voice", "voice_design", "voice_clone"]
    model_id: str = Field(alias="modelId")
    language: str = "Japanese"
    speaker: str | None = None
    instruct: str | None = None
    ref_audio: str | None = Field(default=None, alias="refAudio")
    ref_text: str | None = Field(default=None, alias="refText")
    x_vector_only_mode: bool = Field(default=False, alias="xVectorOnlyMode")
    volume_scale: float = Field(default=1.0, alias="volumeScale")
    dtype: str = "bfloat16"
    device: str = "cuda:0"


class VoicevoxAudioQuery(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str
    speaker: int | None = None
    speedScale: float = 1.0
    pitchScale: float = 0.0
    intonationScale: float = 1.0
    volumeScale: float = 1.0
    prePhonemeLength: float = 0.1
    postPhonemeLength: float = 0.1
    outputSamplingRate: int = 44100
    outputStereo: bool = False
    kana: str = Field(default="")
