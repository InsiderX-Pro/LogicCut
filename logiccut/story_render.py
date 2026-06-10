from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

from .chapter_narration import prepare_narration_reference, safe_audio_duration, synthesize_narration_audio, write_narration_srt
from .manifest import relpath
from .media import burn_subtitles, concat_videos_reencode, ffprobe_duration, render_clip, run_command, write_srt
from .text_normalize import normalize_display_text


def render_story_timeline(
    project_dir: Path,
    *,
    source: Path,
    timeline: dict[str, Any],
    translated_segments: list[dict[str, Any]] | None = None,
    tts_engine: str | None = None,
    tts_ports: str | None = None,
    voice: str | None = None,
    output_name: str = "story_guided_highlights.mp4",
    log_file: Path | None = None,
) -> dict[str, Any]:
    translated_segments = translated_segments or []
    assets_dir = project_dir / "assets" / "story_guided_highlights"
    clips_dir = project_dir / "clips" / "story_guided_highlights"
    render_dir = project_dir / "renders" / "story_guided_highlights"
    for path in (assets_dir, clips_dir, render_dir):
        path.mkdir(parents=True, exist_ok=True)

    final_inputs: list[Path] = []
    parts: list[dict[str, Any]] = []
    selected_voice = voice or os.environ.get("LOGICCUT_STORY_NARRATION_VOICE") or os.environ.get("LOGICCUT_NARRATION_VOICE", "logiccut-story-narrator")
    selected_engine = tts_engine or os.environ.get("LOGICCUT_STORY_TTS_ENGINE") or os.environ.get("LOGICCUT_NARRATION_TTS_ENGINE", "indextts2")
    reference_audio = _resolve_story_reference(source, timeline, assets_dir, log_file=log_file)

    for index, item in enumerate(timeline.get("items", []), start=1):
        start = float(item["start"])
        end = float(item["end"])
        duration = max(end - start, 0.1)
        raw_clip = clips_dir / f"{index:02}_{item['type']}_raw.mp4"
        render_clip(source, raw_clip, start, duration, log_file=log_file)

        if int(item.get("OST", 0)) == 0:
            narration_text = normalize_display_text(item.get("narration") or item.get("title") or "")
            audio_path = assets_dir / f"{index:02}_narration.wav"
            _synthesize_or_fallback(
                narration_text,
                audio_path,
                engine=selected_engine,
                voice=selected_voice,
                tts_ports=tts_ports,
                ref_wav=reference_audio,
                log_file=log_file,
            )
            audio_duration = safe_audio_duration(audio_path, fallback=duration)
            mixed_duration = max(duration, audio_duration + 0.15 if audio_duration > duration + 0.1 else duration)
            source_for_mix = raw_clip
            if audio_duration > duration + 0.1:
                source_for_mix = clips_dir / f"{index:02}_{item['type']}_extended.mp4"
                extend_video_with_tpad(raw_clip, source_for_mix, target_duration=mixed_duration, log_file=log_file)
            narration_srt = assets_dir / f"{index:02}_narration.srt"
            write_narration_srt(narration_srt, narration_text, duration=mixed_duration)
            output = clips_dir / f"{index:02}_narration.mp4"
            mix_narration_over_source(
                source_for_mix,
                audio_path,
                narration_srt,
                output,
                source_audio_volume=float(os.environ.get("LOGICCUT_STORY_SOURCE_DUCK_VOLUME", "0.28")),
                narration_volume=float(os.environ.get("LOGICCUT_STORY_NARRATION_VOLUME", "1.0")),
                log_file=log_file,
            )
            subtitle_path = narration_srt
            adapter = f"logiccut-story-ffmpeg+tts:{selected_engine}"
        else:
            subtitle_path = assets_dir / f"{index:02}_original.srt"
            cues = _subtitle_segments_for_range(translated_segments, start, end)
            if not cues:
                text = normalize_display_text(item.get("subtitle") or item.get("why") or item.get("title") or "原声高光")
                cues = [{"start": 0.0, "end": duration, "text": text}]
            write_srt(subtitle_path, cues)
            output = clips_dir / f"{index:02}_original.mp4"
            burn_subtitles(raw_clip, subtitle_path, output, log_file=log_file)
            adapter = "logiccut-story-ffmpeg+subtitle"

        final_inputs.append(output)
        parts.append(
            {
                "id": f"story_part_{index:02}",
                "type": item["type"],
                "OST": item["OST"],
                "path": output,
                "raw_clip": raw_clip,
                "subtitle": subtitle_path,
                "start": start,
                "end": end,
                "duration": duration,
                "title": item.get("title") or item.get("picture") or f"Part {index}",
                "narration": item.get("narration", ""),
                "why": item.get("why", ""),
                "adapter": adapter,
            }
        )

    output = render_dir / output_name
    concat_videos_reencode(final_inputs, output, log_file=log_file)
    report_json = assets_dir / "story_guided_report.json"
    report_html = assets_dir / "story_guided_report.html"
    report_payload = {
        "story_arc": timeline.get("story_arc", ""),
        "style_id": timeline.get("style_id", "story_news"),
        "output": relpath(output, project_dir),
        "duration": _safe_render_duration(output, parts),
        "parts": [_portable_part(part, project_dir) for part in parts],
    }
    report_json.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_html.write_text(_report_html(report_payload), encoding="utf-8")
    return {
        "output": output,
        "report_json": report_json,
        "report_html": report_html,
        "parts": parts,
    }


def mix_narration_over_source(
    source_clip: Path,
    narration_audio: Path,
    subtitle_path: Path,
    output_path: Path,
    *,
    source_audio_volume: float = 0.28,
    narration_volume: float = 1.0,
    log_file: Path | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    narration_filter = _subtitle_filter(source_clip, subtitle_path)
    filter_complex = (
        f"[0:a:0]volume={source_audio_volume}[srca];"
        f"[1:a:0]volume={narration_volume}[narr];"
        "[srca][narr]amix=inputs=2:duration=longest:dropout_transition=0[aout]"
    )
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source_clip),
            "-i",
            str(narration_audio),
            "-vf",
            narration_filter,
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        log_file=log_file,
    )
    return output_path


def extend_video_with_tpad(
    video_path: Path,
    output_path: Path,
    *,
    target_duration: float,
    log_file: Path | None = None,
) -> Path:
    current = ffprobe_duration(video_path)
    extra = max(0.0, target_duration - current)
    if extra <= 0.05:
        output_path.write_bytes(video_path.read_bytes())
        return output_path
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-vf",
            f"tpad=stop=-1:stop_duration={extra:.3f}",
            "-af",
            f"apad=pad_dur={extra:.3f}",
            "-t",
            f"{target_duration:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        log_file=log_file,
    )
    return output_path


def _synthesize_or_fallback(
    text: str,
    output_path: Path,
    *,
    engine: str,
    voice: str,
    tts_ports: str | None,
    ref_wav: Path | None,
    log_file: Path | None,
) -> dict[str, Any]:
    backend_options: dict[str, Any] = {"recipe": "story-guided-highlights"}
    if ref_wav:
        backend_options["ref_wav"] = str(ref_wav)
    ref_text = os.environ.get("LOGICCUT_STORY_REF_TEXT") or os.environ.get("LOGICCUT_NARRATION_REF_TEXT")
    if ref_text:
        backend_options["ref_text"] = ref_text
    try:
        return synthesize_narration_audio(
            text,
            output_path,
            engine=engine,
            voice=voice,
            tts_ports=tts_ports,
            backend_options=backend_options,
            log_file=log_file,
        )
    except Exception:
        if os.environ.get("LOGICCUT_STORY_ALLOW_TTS_FALLBACK", "0").strip().lower() not in {"1", "true", "yes"}:
            raise
        duration = max(2.0, min(8.0, len(text) / 5.5))
        run_command(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=330:sample_rate=44100",
                "-t",
                f"{duration:.3f}",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ],
            log_file=log_file,
        )
        return {"success": True, "backend": "ffmpeg-tone-fallback", "output_path": str(output_path)}


def _resolve_story_reference(source: Path, timeline: dict[str, Any], assets_dir: Path, *, log_file: Path | None) -> Path | None:
    configured = os.environ.get("LOGICCUT_STORY_REF_WAV") or os.environ.get("LOGICCUT_NARRATION_REF_WAV")
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return path
    if os.environ.get("LOGICCUT_STORY_AUTO_REF", "1").strip().lower() in {"0", "false", "no"}:
        return None
    candidates = [
        item
        for item in timeline.get("items", [])
        if isinstance(item, dict) and int(item.get("OST", 0)) == 1
    ] or [item for item in timeline.get("items", []) if isinstance(item, dict)]
    if not candidates:
        return None
    item = candidates[0]
    try:
        return prepare_narration_reference(
            source,
            assets_dir / "story_narrator_ref.wav",
            start=float(item.get("start", 0.0)),
            end=float(item.get("end", float(item.get("start", 0.0)) + 4.0)),
            log_file=log_file,
        )
    except Exception:
        if os.environ.get("LOGICCUT_STORY_ALLOW_TTS_FALLBACK", "0").strip().lower() in {"1", "true", "yes"}:
            return None
        raise


def _subtitle_filter(source: Path, subtitle_path: Path) -> str:
    from .media import _styled_subtitle_filter  # Local import keeps this module close to public media helpers.

    return _styled_subtitle_filter(source, subtitle_path)


def _subtitle_segments_for_range(segments: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = normalize_display_text(segment.get("text", ""))
        if not text:
            continue
        seg_start = float(segment.get("start", 0.0))
        seg_end = float(segment.get("end", seg_start))
        overlap_start = max(seg_start, start)
        overlap_end = min(seg_end, end)
        if overlap_end <= overlap_start:
            continue
        cues.append(
            {
                "start": round(overlap_start - start, 3),
                "end": round(overlap_end - start, 3),
                "text": text,
            }
        )
    return cues


def _portable_part(part: dict[str, Any], project_dir: Path) -> dict[str, Any]:
    result = dict(part)
    for key in ("path", "raw_clip", "subtitle"):
        result[key] = relpath(Path(result[key]), project_dir)
    return result


def _safe_render_duration(output: Path, parts: list[dict[str, Any]]) -> float:
    try:
        return ffprobe_duration(output)
    except Exception:
        return round(sum(float(part.get("duration", 0.0)) for part in parts), 3)


def _report_html(payload: dict[str, Any]) -> str:
    rows = []
    for part in payload.get("parts", []):
        rows.append(
            f"<tr><td>{html.escape(str(part.get('id')))}</td>"
            f"<td>{html.escape(str(part.get('type')))}</td>"
            f"<td>{html.escape(str(part.get('title')))}</td>"
            f"<td>{html.escape(str(part.get('why')))}</td></tr>"
        )
    video = html.escape(str(payload.get("output", "")))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LogicCut Story Guided Highlights</title>
  <style>
    body {{ margin:0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:#0d1117; color:#eef2ff; }}
    main {{ max-width:1100px; margin:0 auto; padding:32px 20px; }}
    video {{ width:100%; border:1px solid rgba(255,255,255,.16); background:#000; }}
    .meta {{ color:#aab4cf; line-height:1.7; }}
    table {{ width:100%; border-collapse:collapse; margin-top:22px; }}
    td, th {{ border-bottom:1px solid rgba(255,255,255,.14); padding:12px; text-align:left; vertical-align:top; }}
    th {{ color:#93c5fd; }}
  </style>
</head>
<body>
<main>
  <h1>LogicCut 故事式高光剪辑</h1>
  <p class="meta">{html.escape(str(payload.get("story_arc", "")))}</p>
  <video controls preload="metadata" src="{video}"></video>
  <table>
    <thead><tr><th>ID</th><th>类型</th><th>标题</th><th>剪辑理由</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</main>
</body>
</html>
"""
