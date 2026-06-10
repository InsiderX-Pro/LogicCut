from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .media import burn_subtitles
from .tts_engines import resolve_tts_engine


DEFAULT_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "third_party" / "video-translate-refine"
DEFAULT_PYTHON = Path(sys.executable)
SECRET_KEY_RE = re.compile(
    r"(?P<name>[A-Z0-9_]*(?:API_KEY|ACCESS_KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<value>[^\s\"']+)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class VideoTranslateRefineConfig:
    video: Path
    output_dir: Path
    source_root: Path = DEFAULT_SOURCE_ROOT
    python: Path = DEFAULT_PYTHON
    profile: str = "v3"
    clip_seconds: int | None = None
    src_lang: str | None = None
    tgt_lang: str | None = None
    translate_backend: str | None = None
    subtitle_path: Path | None = None
    speaker_backend: str | None = "pyannote_local"
    asr_text_refine_backend: str | None = "qwen_omni"
    vocal_separation_backend: str | None = None
    tts_engine: str | None = "rgad-tts"
    tts_backend: str | None = None
    tts_ports: str | None = None
    fish_tts_adapter_url: str | None = None
    dub_workers: int | None = None
    min_speakers: int | None = None
    num_speakers: int | None = None
    max_speakers: int | None = None
    ref_bgm_filter_enabled: bool = False
    ref_bgm_tts_ref_strategy: str | None = None
    write_subtitles: bool = True
    burn_subtitles: bool = False
    timeout_s: int = 7200


@dataclass(frozen=True)
class VideoTranslateRefineResult:
    output_video: Path
    source_output_video: Path
    output_dir: Path
    run_dir: Path
    manifest_path: Path
    log_path: Path
    subtitle_path: Path | None = None
    subtitled_video: Path | None = None


Runner = Callable[..., subprocess.CompletedProcess[str]]


def config_from_env(
    *,
    video: Path,
    output_dir: Path,
    clip_seconds: int | None = None,
    src_lang: str | None = None,
    tgt_lang: str | None = None,
    profile: str | None = None,
    translate_backend: str | None = None,
    subtitle_path: Path | None = None,
    tts_engine: str | None = None,
) -> VideoTranslateRefineConfig:
    source_root = Path(
        os.environ.get("LOGICCUT_VIDEO_TRANSLATE_REFINE_ROOT")
        or os.environ.get("VIDEO_TRANSLATE_REFINE_ROOT")
        or DEFAULT_SOURCE_ROOT
    ).expanduser()
    python = Path(
        os.environ.get("LOGICCUT_VIDEO_TRANSLATE_REFINE_PYTHON")
        or (DEFAULT_PYTHON if DEFAULT_PYTHON.exists() else sys.executable)
    ).expanduser()
    return VideoTranslateRefineConfig(
        video=video,
        output_dir=output_dir,
        source_root=source_root,
        python=python,
        profile=profile or os.environ.get("LOGICCUT_VIDEO_TRANSLATE_PROFILE", "v3"),
        clip_seconds=clip_seconds,
        src_lang=src_lang if src_lang is not None else os.environ.get("LOGICCUT_SOURCE_LANGUAGE", "en"),
        tgt_lang=tgt_lang if tgt_lang is not None else os.environ.get("LOGICCUT_TARGET_LANGUAGE", "中文"),
        translate_backend=(
            translate_backend
            if translate_backend is not None
            else os.environ.get("LOGICCUT_TRANSLATE_BACKEND", "qwen35_plus")
        ),
        subtitle_path=subtitle_path or _path_or_none(os.environ.get("LOGICCUT_SUBTITLE_PATH")),
        speaker_backend=os.environ.get("LOGICCUT_SPEAKER_BACKEND", "pyannote_local"),
        asr_text_refine_backend=os.environ.get("LOGICCUT_ASR_TEXT_REFINE_BACKEND", "qwen_omni"),
        vocal_separation_backend=os.environ.get("LOGICCUT_VOCAL_SEPARATION_BACKEND") or None,
        tts_engine=tts_engine or os.environ.get("LOGICCUT_TTS_ENGINE", "rgad-tts"),
        tts_backend=os.environ.get("LOGICCUT_TTS_BACKEND") or None,
        tts_ports=os.environ.get("LOGICCUT_TTS_PORTS") or None,
        fish_tts_adapter_url=os.environ.get("LOGICCUT_FISH_TTS_ADAPTER_URL") or None,
        dub_workers=_int_or_none(os.environ.get("LOGICCUT_DUB_WORKERS")),
        min_speakers=_int_or_none(os.environ.get("LOGICCUT_MIN_SPEAKERS")),
        num_speakers=_int_or_none(os.environ.get("LOGICCUT_NUM_SPEAKERS")),
        max_speakers=_int_or_none(os.environ.get("LOGICCUT_MAX_SPEAKERS")),
        ref_bgm_filter_enabled=_bool_env("LOGICCUT_REF_BGM_FILTER_ENABLED", default=False),
        ref_bgm_tts_ref_strategy=os.environ.get("LOGICCUT_REF_BGM_TTS_REF_STRATEGY") or None,
        write_subtitles=_bool_env("LOGICCUT_WRITE_SUBTITLES", default=True),
        burn_subtitles=_bool_env("LOGICCUT_BURN_SUBTITLES", default=False),
        timeout_s=int(os.environ.get("LOGICCUT_VIDEO_TRANSLATION_TIMEOUT_S", "7200")),
    )


def build_command(config: VideoTranslateRefineConfig) -> tuple[list[str], dict[str, str]]:
    script = config.source_root / "scripts" / "run_pipeline_profile.py"
    command = [str(config.python), str(script), str(config.video.resolve()), "--profile", config.profile]
    _extend_option(command, "--clip", config.clip_seconds)
    _extend_option(command, "--src-lang", config.src_lang)
    _extend_option(command, "--tgt-lang", config.tgt_lang)
    _extend_option(command, "--translate-backend", config.translate_backend)
    _extend_option(command, "--speaker-backend", config.speaker_backend)
    _extend_option(command, "--asr-text-refine-backend", config.asr_text_refine_backend)
    _extend_option(command, "--vocal-separation-backend", config.vocal_separation_backend)
    tts_preset = resolve_tts_engine(config.tts_engine, tts_ports=config.tts_ports)
    tts_backend = config.tts_backend or tts_preset.tts_backend
    tts_ports = config.tts_ports or tts_preset.tts_ports
    fish_tts_adapter_url = config.fish_tts_adapter_url or tts_preset.fish_tts_adapter_url
    _extend_option(command, "--tts-ports", tts_ports)
    _extend_option(command, "--dub-workers", config.dub_workers)
    _extend_option(command, "--min-speakers", config.min_speakers)
    _extend_option(command, "--num-speakers", config.num_speakers)
    _extend_option(command, "--max-speakers", config.max_speakers)
    _extend_extra_cli_arg(command, "--tts-backend", tts_backend)
    _extend_extra_cli_arg(command, "--fish-tts-adapter-url", fish_tts_adapter_url)
    _extend_extra_cli_arg(command, "--subtitle-path", config.subtitle_path)
    if config.ref_bgm_filter_enabled:
        _extend_extra_cli_arg(command, "--enable-ref-bgm-filter", True)
    _extend_extra_cli_arg(command, "--ref-bgm-tts-ref-strategy", config.ref_bgm_tts_ref_strategy)

    env = dict(os.environ)
    source_path = str((config.source_root / "src").resolve())
    current_pythonpath = str(env.get("PYTHONPATH") or "")
    env["PYTHONPATH"] = source_path if not current_pythonpath else f"{source_path}{os.pathsep}{current_pythonpath}"
    env.setdefault("PYTHONNOUSERSITE", "1")
    env.setdefault("LOGICCUT_CREATIVE_DRIVER", "codex")
    return command, env


def parse_output_video(stdout: str) -> Path:
    candidates: list[Path] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip().strip("'\"")
        if not line.lower().endswith(".mp4"):
            continue
        path = Path(line).expanduser()
        if path.exists():
            candidates.append(path.resolve())
    if not candidates:
        raise ValueError("video-translate-refine did not print an existing .mp4 output path")
    return candidates[-1]


def redact_secrets(text: str) -> str:
    return SECRET_KEY_RE.sub(lambda match: f"{match.group('name')}{match.group('sep')}<redacted>", text)


def run_video_translate_refine(
    config: VideoTranslateRefineConfig,
    *,
    runner: Runner = subprocess.run,
) -> VideoTranslateRefineResult:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    command, env = build_command(config)
    completed = runner(
        command,
        cwd=str(config.source_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=config.timeout_s,
    )

    combined_log = "\n".join(
        [
            "command=" + " ".join(command),
            "--- stdout ---",
            completed.stdout or "",
            "--- stderr ---",
            completed.stderr or "",
        ]
    )
    log_path = config.output_dir / "video_translate_refine.log"
    log_path.write_text(redact_secrets(combined_log), encoding="utf-8")

    if completed.returncode != 0:
        raise RuntimeError(f"video-translate-refine failed with exit code {completed.returncode}; see {log_path}")

    source_output = parse_output_video(completed.stdout or "")
    output_video = config.output_dir / "output_video.mp4"
    shutil.copy2(source_output, output_video)
    run_dir = source_output.parent
    _copy_optional(run_dir / "timings.json", config.output_dir / "timings.json")
    _copy_optional(run_dir / "final_result_manifest.json", config.output_dir / "final_result_manifest.json")
    subtitle_output = _maybe_write_subtitles(config.output_dir, enabled=config.write_subtitles)
    subtitled_video = _maybe_burn_subtitles(
        output_video,
        subtitle_output,
        config.output_dir,
        enabled=config.burn_subtitles,
    )

    tts_preset = resolve_tts_engine(config.tts_engine, tts_ports=config.tts_ports)
    manifest = {
        "adapter": "video-translate-refine",
        "profile": config.profile,
        "source_video": str(config.video),
        "output_video": str(output_video),
        "subtitle_path": (str(subtitle_output) if subtitle_output else None),
        "subtitled_video": (str(subtitled_video) if subtitled_video else None),
        "source_output_video": str(source_output),
        "run_dir": str(run_dir),
        "clip_seconds": config.clip_seconds,
        "src_lang": config.src_lang,
        "tgt_lang": config.tgt_lang,
        "translate_backend": config.translate_backend,
        "input_subtitle_path": (str(config.subtitle_path) if config.subtitle_path else None),
        "speaker_backend": config.speaker_backend,
        "asr_text_refine_backend": config.asr_text_refine_backend,
        "vocal_separation_backend": config.vocal_separation_backend,
        "tts_engine": tts_preset.engine,
        "tts_backend": config.tts_backend or tts_preset.tts_backend,
        "tts_ports": config.tts_ports or tts_preset.tts_ports,
        "fish_tts_adapter_url": config.fish_tts_adapter_url or tts_preset.fish_tts_adapter_url,
        "dub_workers": config.dub_workers,
        "min_speakers": config.min_speakers,
        "num_speakers": config.num_speakers,
        "max_speakers": config.max_speakers,
        "ref_bgm_filter_enabled": config.ref_bgm_filter_enabled,
        "ref_bgm_tts_ref_strategy": config.ref_bgm_tts_ref_strategy,
        "creative_driver": env.get("LOGICCUT_CREATIVE_DRIVER", "codex"),
    }
    manifest_path = config.output_dir / "video_translate_refine_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return VideoTranslateRefineResult(
        output_video=output_video,
        source_output_video=source_output,
        output_dir=config.output_dir,
        run_dir=run_dir,
        manifest_path=manifest_path,
        log_path=log_path,
        subtitle_path=subtitle_output,
        subtitled_video=subtitled_video,
    )


def _extend_option(command: list[str], option: str, value: object | None) -> None:
    if value is None:
        return
    command.extend([option, str(value)])


def _extend_extra_cli_arg(command: list[str], option: str, value: object | None = None) -> None:
    if value is None:
        return
    extra = option if value is True else f"{option} {shlex.quote(str(value))}"
    command.extend(["--extra-cli-arg", extra])


def _copy_optional(source: Path, destination: Path) -> None:
    if source.exists() and source.is_file():
        shutil.copy2(source, destination)


def _maybe_write_subtitles(output_dir: Path, *, enabled: bool) -> Path | None:
    timings = output_dir / "timings.json"
    if not enabled or not timings.exists():
        return None
    subtitle_output = output_dir / "translated_subtitles.srt"
    return write_translated_srt_from_timings(timings, subtitle_output)


def _maybe_burn_subtitles(
    output_video: Path,
    subtitle_output: Path | None,
    output_dir: Path,
    *,
    enabled: bool,
) -> Path | None:
    if not enabled or subtitle_output is None:
        return None
    subtitled_video = output_dir / "output_video_subtitled.mp4"
    return burn_subtitles(output_video, subtitle_output, subtitled_video, log_file=output_dir / "burn_subtitles.log")


def write_translated_srt_from_timings(timings_path: Path, output_path: Path) -> Path:
    payload = json.loads(timings_path.read_text(encoding="utf-8"))
    rows: list[tuple[float, float, str]] = []
    for utterance in payload.get("utterances", []) or []:
        if not isinstance(utterance, dict):
            continue
        text = _translated_text_for_utterance(utterance)
        if not text:
            continue
        start = float(utterance.get("start_ms", 0) or 0) / 1000.0
        end = float(utterance.get("end_ms", utterance.get("start_ms", 0)) or 0) / 1000.0
        if end <= start:
            continue
        rows.append((start, end, text))
    rows.sort(key=lambda item: item[0])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = []
    for index, (start, end, text) in enumerate(rows, start=1):
        blocks.append(str(index))
        blocks.append(f"{_srt_time(start)} --> {_srt_time(end)}")
        blocks.append(text)
        blocks.append("")
    output_path.write_text("\n".join(blocks), encoding="utf-8")
    return output_path


def _translated_text_for_utterance(utterance: dict) -> str:
    attempts = utterance.get("attempts")
    if isinstance(attempts, list):
        for attempt in reversed(attempts):
            if isinstance(attempt, dict):
                text = str(attempt.get("translated_text") or attempt.get("tts_text") or "").strip()
                if text:
                    return text
    return str(utterance.get("translated_text") or utterance.get("tts_text") or "").strip()


def _srt_time(seconds: float) -> str:
    millis = int(round(max(seconds, 0.0) * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def _int_or_none(value: str | None) -> int | None:
    if value is None or not str(value).strip():
        return None
    return int(value)


def _path_or_none(value: str | None) -> Path | None:
    if value is None or not str(value).strip():
        return None
    return Path(value).expanduser()


def _bool_env(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}
