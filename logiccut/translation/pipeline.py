from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..media import burn_subtitles, ffprobe_duration, render_clip, write_srt
from ..semantic import transcribe_media
from ..text_normalize import normalize_display_text


@dataclass(frozen=True)
class LocalTranslationConfig:
    input_video: Path
    output_dir: Path
    target_language: str = "中文"
    source_language: str | None = None
    clip_seconds: int | None = None
    transcript_json: Path | None = None
    translation_json: Path | None = None
    allow_fallback_transcript: bool = False
    burn_subtitles: bool = True


@dataclass(frozen=True)
class LocalTranslationResult:
    status: str
    output_dir: Path
    manifest_path: Path
    prompt_path: Path
    transcript_path: Path
    todo_translation_path: Path
    translation_path: Path | None = None
    subtitle_path: Path | None = None
    output_video: Path | None = None
    working_video: Path | None = None


def run_local_translation(config: LocalTranslationConfig) -> LocalTranslationResult:
    input_video = config.input_video.expanduser()
    if not input_video.exists():
        raise FileNotFoundError(input_video)

    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    working_video = _prepare_working_video(input_video, output_dir, config.clip_seconds)
    transcript = _load_or_transcribe(config, working_video)
    transcript_path = output_dir / "source_transcript.json"
    _write_json(transcript_path, transcript)

    prompt_path = output_dir / "codex_translation_prompt.md"
    translation_path = config.translation_json or output_dir / "translated_segments.json"
    todo_translation_path = output_dir / "translated_segments.todo.json"
    prompt_path.write_text(
        build_codex_translation_prompt(
            transcript,
            target_language=config.target_language,
            output_filename=translation_path.name,
        ),
        encoding="utf-8",
    )
    if not translation_path.exists():
        _write_json(
            todo_translation_path,
            {
                "target_language": config.target_language,
                "segments": [
                    {
                        "start": item["start"],
                        "end": item["end"],
                        "source_text": item["text"],
                        "text": "",
                    }
                    for item in _normal_segments(transcript)
                ],
            },
        )
        manifest_path = _write_manifest(
            output_dir,
            status="needs_codex_translation",
            config=config,
            working_video=working_video,
            transcript_path=transcript_path,
            prompt_path=prompt_path,
            todo_translation_path=todo_translation_path,
            translation_path=translation_path,
            subtitle_path=None,
            output_video=None,
        )
        return LocalTranslationResult(
            status="needs_codex_translation",
            output_dir=output_dir,
            manifest_path=manifest_path,
            prompt_path=prompt_path,
            transcript_path=transcript_path,
            todo_translation_path=todo_translation_path,
            translation_path=translation_path,
            working_video=working_video,
        )

    translated_segments = _load_translated_segments(translation_path)
    subtitle_path = write_srt(output_dir / "translated_subtitles.srt", translated_segments)
    output_video = output_dir / "output_video_subtitled.mp4" if config.burn_subtitles else output_dir / "output_video.mp4"
    if config.burn_subtitles:
        output_video = burn_subtitles(working_video, subtitle_path, output_video, log_file=output_dir / "burn_subtitles.log")
    else:
        shutil.copy2(working_video, output_video)
    manifest_path = _write_manifest(
        output_dir,
        status="ok",
        config=config,
        working_video=working_video,
        transcript_path=transcript_path,
        prompt_path=prompt_path,
        todo_translation_path=todo_translation_path,
        translation_path=translation_path,
        subtitle_path=subtitle_path,
        output_video=output_video,
    )
    _write_report(output_dir / "translation_report.html", config=config, output_video=output_video, segments=translated_segments)
    return LocalTranslationResult(
        status="ok",
        output_dir=output_dir,
        manifest_path=manifest_path,
        prompt_path=prompt_path,
        transcript_path=transcript_path,
        todo_translation_path=todo_translation_path,
        translation_path=translation_path,
        subtitle_path=subtitle_path,
        output_video=output_video,
        working_video=working_video,
    )


def build_codex_translation_prompt(
    transcript: dict[str, Any],
    *,
    target_language: str,
    output_filename: str,
) -> str:
    segments = _normal_segments(transcript)
    transcript_text = "\n".join(
        f"[{item['start']:.2f}-{item['end']:.2f}] {item['text']}"
        for item in segments
    )
    return f"""# LogicCut Local Translation

你现在是 LogicCut 的 Codex 翻译层。请只基于下面的 transcript 翻译字幕。

重要边界：
- 不要调用 OpenAI/Gemini/Claude API，也不要要求用户配置 LLM key。
- 不要改动时间轴，保留每个 segment 的 start/end。
- 翻译目标语言：{target_language}
- 输出文件名必须是 `{output_filename}`。
- 输出 JSON，不要 Markdown。
- 中文输出必须使用简体中文。

JSON 格式：
{{
  "target_language": "{target_language}",
  "segments": [
    {{
      "start": 0.0,
      "end": 1.0,
      "text": "翻译后的字幕"
    }}
  ]
}}

Transcript:
{transcript_text}
""".strip()


def _prepare_working_video(input_video: Path, output_dir: Path, clip_seconds: int | None) -> Path:
    if not clip_seconds:
        return input_video
    duration = min(float(clip_seconds), ffprobe_duration(input_video))
    clip_path = output_dir / "source_clip.mp4"
    return render_clip(input_video, clip_path, 0.0, duration, log_file=output_dir / "clip.log", accurate=True)


def _load_or_transcribe(config: LocalTranslationConfig, working_video: Path) -> dict[str, Any]:
    if config.transcript_json:
        return _load_json(config.transcript_json)
    try:
        return _transcribe_with_faster_whisper(working_video, language=config.source_language)
    except ImportError:
        pass
    except Exception as exc:
        if not config.allow_fallback_transcript:
            raise RuntimeError(f"faster-whisper transcription failed: {exc}") from exc
    if config.allow_fallback_transcript:
        old = os.environ.get("LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK")
        os.environ["LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK"] = "1"
        try:
            return transcribe_media(working_video, language=config.source_language)
        finally:
            if old is None:
                os.environ.pop("LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK", None)
            else:
                os.environ["LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK"] = old
    try:
        return transcribe_media(working_video, language=config.source_language)
    except Exception as exc:
        raise RuntimeError(
            "No local ASR backend is available. Run `logiccut setup translation --profile asr --install`, "
            "provide --transcript-json, or use --allow-fallback-transcript only for demos."
        ) from exc


def _transcribe_with_faster_whisper(media_path: Path, *, language: str | None = None) -> dict[str, Any]:
    from faster_whisper import WhisperModel

    model_size = os.environ.get("LOGICCUT_FASTER_WHISPER_MODEL", "base")
    device = os.environ.get("LOGICCUT_FASTER_WHISPER_DEVICE", "auto")
    compute_type = os.environ.get("LOGICCUT_FASTER_WHISPER_COMPUTE_TYPE", "default")
    kwargs = {"device": device}
    if compute_type != "default":
        kwargs["compute_type"] = compute_type
    model = WhisperModel(model_size, **kwargs)
    segments_iter, info = model.transcribe(str(media_path), language=language)
    segments = [
        {
            "start": float(segment.start),
            "end": float(segment.end),
            "text": str(segment.text).strip(),
        }
        for segment in segments_iter
        if str(segment.text).strip()
    ]
    return {
        "duration": float(getattr(info, "duration", 0.0) or ffprobe_duration(media_path)),
        "language": getattr(info, "language", language or "auto"),
        "adapter": "faster-whisper",
        "model": model_size,
        "segments": segments,
    }


def _load_translated_segments(path: Path) -> list[dict[str, object]]:
    payload = _load_json(path)
    raw_segments = payload.get("segments", payload if isinstance(payload, list) else [])
    if not isinstance(raw_segments, list):
        raise ValueError("translated segments must be a list or an object with segments")
    segments: list[dict[str, object]] = []
    for index, item in enumerate(raw_segments, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"translation segment {index} must be an object")
        text = normalize_display_text(item.get("text") or item.get("translation") or "")
        if not text:
            raise ValueError(f"translation segment {index} has empty text")
        start = float(item.get("start", item.get("start_time", 0.0)))
        end = float(item.get("end", item.get("end_time", start)))
        if end <= start:
            raise ValueError(f"translation segment {index} has invalid time range")
        segments.append({"start": start, "end": end, "text": text})
    if not segments:
        raise ValueError("translated segments are empty")
    return segments


def _normal_segments(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for index, item in enumerate(transcript.get("segments", []) or [], start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        start = float(item.get("start", item.get("start_time", 0.0)))
        end = float(item.get("end", item.get("end_time", start)))
        if end <= start:
            continue
        segments.append({"index": index, "start": start, "end": end, "text": text})
    if not segments:
        raise ValueError("source transcript has no timed text segments")
    return segments


def _write_manifest(
    output_dir: Path,
    *,
    status: str,
    config: LocalTranslationConfig,
    working_video: Path,
    transcript_path: Path,
    prompt_path: Path,
    todo_translation_path: Path,
    translation_path: Path,
    subtitle_path: Path | None,
    output_video: Path | None,
) -> Path:
    manifest = {
        "backend": "logiccut-local",
        "status": status,
        "translation_driver": "codex-file",
        "source_video": str(config.input_video),
        "working_video": str(working_video),
        "target_language": config.target_language,
        "source_language": config.source_language,
        "clip_seconds": config.clip_seconds,
        "transcript": str(transcript_path),
        "codex_prompt": str(prompt_path),
        "todo_translation": str(todo_translation_path),
        "translation_json": str(translation_path),
        "subtitle": str(subtitle_path) if subtitle_path else None,
        "output_video": str(output_video) if output_video else None,
        "burn_subtitles": config.burn_subtitles,
    }
    manifest_path = output_dir / "translation_manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path


def _write_report(path: Path, *, config: LocalTranslationConfig, output_video: Path, segments: list[dict[str, object]]) -> Path:
    rows = "\n".join(
        f"<tr><td>{float(item['start']):.2f}-{float(item['end']):.2f}</td><td>{item['text']}</td></tr>"
        for item in segments[:80]
    )
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>LogicCut Translation Report</title>
  <style>
    body {{ margin: 32px; font-family: Arial, sans-serif; background: #0f172a; color: #e5e7eb; }}
    video {{ width: min(960px, 100%); border-radius: 8px; display: block; margin: 20px 0; }}
    table {{ width: min(960px, 100%); border-collapse: collapse; }}
    td, th {{ border-bottom: 1px solid #334155; padding: 10px; vertical-align: top; }}
    .meta {{ color: #94a3b8; }}
  </style>
</head>
<body>
  <h1>LogicCut Local Translation</h1>
  <p class="meta">Target: {config.target_language}</p>
  <video controls src="{output_video.name}"></video>
  <table>
    <thead><tr><th>Time</th><th>Subtitle</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
""",
        encoding="utf-8",
    )
    return path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
