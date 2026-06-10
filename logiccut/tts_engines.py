from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TtsEnginePreset:
    engine: str
    tts_backend: str
    tts_ports: str | None
    fish_tts_adapter_url: str | None = None
    note: str = ""


ALIASES = {
    "fish": "fishaudio",
    "fish-audio": "fishaudio",
    "fishaudio_s2": "fishaudio",
    "fish_speech": "fish-speech-s2",
    "fish-speech": "fish-speech-s2",
    "fish_speech_s2": "fish-speech-s2",
    "index": "indextts2",
    "index-tts2": "indextts2",
    "index_tts2": "indextts2",
    "omni": "omnivoice",
    "omni-voice": "omnivoice",
    "omni_voice": "omnivoice",
}


def normalize_tts_engine(engine: str | None) -> str:
    value = str(engine or "fishaudio").strip().lower().replace("_", "-")
    return ALIASES.get(value, value)


def resolve_tts_engine(engine: str | None, *, tts_ports: str | None = None) -> TtsEnginePreset:
    normalized = normalize_tts_engine(engine)
    if normalized == "fishaudio":
        return TtsEnginePreset(
            engine="fishaudio",
            tts_backend="legacy_router",
            tts_ports=tts_ports or os.environ.get("LOGICCUT_FISHAUDIO_TTS_PORTS", "8321"),
            note="Podcast-compatible FishAudio S2 /tts service.",
        )
    if normalized == "indextts2":
        return TtsEnginePreset(
            engine="indextts2",
            tts_backend="legacy_router",
            tts_ports=tts_ports or os.environ.get("LOGICCUT_INDEXTTS2_TTS_PORTS", "8304"),
            note="IndexTTS2 /tts router, compatible with emotion ref options.",
        )
    if normalized == "omnivoice":
        return TtsEnginePreset(
            engine="omnivoice",
            tts_backend="legacy_router",
            tts_ports=tts_ports or os.environ.get("LOGICCUT_OMNIVOICE_TTS_PORTS", "8391"),
            note="LogicCut OmniVoice OpenAI-compatible /tts adapter.",
        )
    if normalized == "fish-speech-s2":
        return TtsEnginePreset(
            engine="fish-speech-s2",
            tts_backend="fish_speech_s2",
            tts_ports=None,
            fish_tts_adapter_url=os.environ.get("LOGICCUT_FISH_TTS_ADAPTER_URL", "http://127.0.0.1:8392"),
            note="video-translate-refine Fish Speech S2 adapter mode.",
        )
    raise ValueError(
        "unsupported TTS engine: "
        f"{engine!r}; expected fishaudio, indextts2, omnivoice, or fish-speech-s2"
    )
