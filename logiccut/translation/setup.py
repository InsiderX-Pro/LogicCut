from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


MINIMAL_PACKAGES = [
    "opencc-python-reimplemented",
]
OPTIONAL_PACKAGES = [
    "faster-whisper",
]
FULL_EXTRA_PACKAGES = [
    "torch",
    "torchaudio",
]
PYANNOTE_PACKAGES = [
    "pyannote.audio==3.1.1",
    "pyannote.core==5.0.0",
    "pyannote.metrics==3.2.1",
    "pyannote.pipeline==3.0.1",
    "numpy==1.26.4",
]


def build_translation_setup_plan(*, profile: str = "minimal", install: bool = False) -> dict[str, Any]:
    if profile not in {"minimal", "asr", "full"}:
        raise ValueError("translation setup profile must be minimal, asr, or full")
    packages = list(MINIMAL_PACKAGES)
    optional: list[str] = []
    if profile == "minimal":
        optional.extend(OPTIONAL_PACKAGES)
    if profile in {"minimal", "asr"}:
        optional.extend(FULL_EXTRA_PACKAGES)
        optional.extend(PYANNOTE_PACKAGES)
    if profile in {"asr", "full"}:
        packages.extend(OPTIONAL_PACKAGES)
    if profile == "full":
        packages.extend(FULL_EXTRA_PACKAGES)
        packages.extend(PYANNOTE_PACKAGES)
    commands = [
        f"{sys.executable} -m pip install --upgrade pip wheel",
        f"{sys.executable} -m pip install " + " ".join(packages),
    ]
    if profile == "full":
        commands.append("python scripts/download_models.py --include-gated")
    return {
        "component": "translation",
        "profile": profile,
        "install": install,
        "system_dependencies": ["ffmpeg", "ffprobe", "python>=3.10"],
        "python_packages": packages,
        "optional_python_packages": optional,
        "environment": {
            "HF_TOKEN": "required for full pyannote speaker diarization",
            "LOGICCUT_TRANSLATION_DRIVER": "codex-file",
        },
        "model_sources": [
            {"name": "faster-whisper", "github": "https://github.com/SYSTRAN/faster-whisper"},
            {"name": "faster-whisper-base", "huggingface": "https://huggingface.co/Systran/faster-whisper-base"},
            {"name": "faster-whisper-large-v3", "huggingface": "https://huggingface.co/Systran/faster-whisper-large-v3"},
            {"name": "pyannote/speaker-diarization-3.1", "huggingface": "https://huggingface.co/pyannote/speaker-diarization-3.1"},
            {"name": "Fish Speech", "github": "https://github.com/fishaudio/fish-speech"},
            {"name": "IndexTTS2", "github": "https://github.com/index-tts/index-tts", "huggingface": "https://huggingface.co/IndexTeam/IndexTTS-2"},
            {"name": "OmniVoice", "github": "https://github.com/k2-fsa/OmniVoice", "huggingface": "https://huggingface.co/k2-fsa/OmniVoice"},
        ],
        "install_commands": commands,
        "checks": _checks(profile),
        "smoke_commands": [
            "logiccut sample --output output/translation-smoke/source.mp4 --duration 65",
            "logiccut translate-video --backend logiccut-local --input output/translation-smoke/source.mp4 --output-dir output/translation-smoke/local --allow-fallback-transcript",
            "edit output/translation-smoke/local/translated_segments.json from Codex prompt",
            "logiccut translate-video --backend logiccut-local --input output/translation-smoke/source.mp4 --output-dir output/translation-smoke/local --translation-json output/translation-smoke/local/translated_segments.json --allow-fallback-transcript",
        ],
    }


def run_translation_setup(*, profile: str = "minimal", install: bool = False, runner=subprocess.run) -> dict[str, Any]:
    plan = build_translation_setup_plan(profile=profile, install=install)
    if not install:
        return plan
    for command in plan["install_commands"]:
        runner(shlex.split(command), check=True, env={**os.environ, "PYTHONNOUSERSITE": "1"})
    return {**plan, "installed": True, "checks": _checks(profile)}


def _checks(profile: str) -> dict[str, dict[str, Any]]:
    checks = {
        "ffmpeg": _command_check("ffmpeg"),
        "ffprobe": _command_check("ffprobe"),
        "opencc": _module_check("opencc"),
    }
    if profile in {"asr", "full"}:
        checks["faster_whisper"] = _module_check("faster_whisper")
    if profile == "full":
        checks["torch"] = _module_check("torch")
        checks["pyannote.audio"] = _module_check("pyannote.audio")
        checks["HF_TOKEN"] = {"status": "ok" if os.environ.get("HF_TOKEN") else "missing"}
    return checks


def _command_check(command: str) -> dict[str, Any]:
    path = shutil.which(command)
    return {"status": "ok" if path else "missing", "path": path}


def _module_check(module: str) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-c", f"import {module}; print('ok')"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
    )
    if proc.returncode == 0:
        return {"status": "ok", "module": module}
    return {"status": "missing", "module": module, "message": (proc.stderr or proc.stdout).strip()[-300:]}
