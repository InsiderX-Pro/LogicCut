from __future__ import annotations

import argparse
import html
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from logiccut.manifest import append_log, load_manifest, relpath, save_manifest, upsert_by_id
from logiccut.media import burn_subtitles, concat_videos_reencode, ffprobe_duration, render_clip, write_srt
from logiccut.semantic import (
    build_semantic_creation_plan,
    call_vertex_gemini,
    normalize_semantic_plan,
    parse_json_loose,
    transcribe_media,
    translate_segment_chunk,
    write_json,
)
from logiccut.text_normalize import normalize_display_text


@dataclass(frozen=True)
class CaseSpec:
    slug: str
    label: str
    category: str
    source_url: str
    case_dir: Path
    project_dir: Path
    translation_video: Path | None = None
    translation_source: Path | None = None


def expand_highlights(
    project_dir: Path,
    *,
    context_before: float,
    context_after: float,
    min_duration: float,
    merge_gap: float = 2.0,
    max_items: int = 5,
) -> Path:
    manifest = load_manifest(project_dir)
    source = (project_dir / manifest["input"]["path"]).resolve()
    source_duration = ffprobe_duration(source)
    raw_items = [
        item
        for item in manifest.get("clips", [])
        if item.get("recipe") == "semantic-highlights" and item.get("role") == "semantic_highlight"
    ]
    raw_items.sort(key=lambda item: float(item.get("start", 0)))
    raw_items = raw_items[:max_items]
    expanded: list[dict[str, Any]] = []
    for item in raw_items:
        start = max(0.0, float(item["start"]) - context_before)
        end = min(source_duration, float(item["end"]) + context_after)
        if end - start < min_duration:
            pad = (min_duration - (end - start)) / 2
            start = max(0.0, start - pad)
            end = min(source_duration, end + pad)
        next_item = {
            "source_clip_ids": [item["id"]],
            "start": round(start, 3),
            "end": round(end, 3),
            "title": item.get("title", item["id"]),
            "hook_sentence": item.get("hook_sentence", ""),
            "virality_reason": item.get("virality_reason", ""),
            "score": item.get("score"),
        }
        if expanded and next_item["start"] <= expanded[-1]["end"] + merge_gap:
            expanded[-1]["end"] = max(expanded[-1]["end"], next_item["end"])
            expanded[-1]["source_clip_ids"].extend(next_item["source_clip_ids"])
            if next_item.get("score", 0) and (expanded[-1].get("score") or 0) < next_item["score"]:
                expanded[-1]["title"] = next_item["title"]
                expanded[-1]["hook_sentence"] = next_item["hook_sentence"]
                expanded[-1]["virality_reason"] = next_item["virality_reason"]
                expanded[-1]["score"] = next_item["score"]
            continue
        expanded.append(next_item)

    clips: list[Path] = []
    log_file = project_dir / "logs" / "semantic-highlights-expanded.log"
    for index, item in enumerate(expanded, start=1):
        clip_id = f"semantic_highlight_expanded_{index:02}"
        clip_path = project_dir / "clips" / f"{clip_id}.mp4"
        render_clip(source, clip_path, item["start"], item["end"] - item["start"], log_file=log_file)
        clips.append(clip_path)
        upsert_by_id(
            manifest["clips"],
            {
                "id": clip_id,
                "recipe": "semantic-highlights-expanded",
                "adapter": "faster-whisper+vertex-gemini+ffmpeg",
                "path": relpath(clip_path, project_dir),
                "start": item["start"],
                "end": item["end"],
                "score": item.get("score"),
                "role": "semantic_highlight_expanded",
                "title": item["title"],
                "hook_sentence": item.get("hook_sentence", ""),
                "virality_reason": item.get("virality_reason", ""),
                "source_clip_ids": item["source_clip_ids"],
            },
        )

    render_path = project_dir / "renders" / "semantic_highlights_expanded.mp4"
    concat_videos_reencode(clips, render_path, log_file=log_file)
    analysis_path = project_dir / "assets" / "expanded_highlights.json"
    analysis_path.write_text(json.dumps(expanded, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upsert_by_id(
        manifest["renders"],
        {
            "id": "semantic_highlights_expanded",
            "recipe": "semantic-highlights-expanded",
            "adapter": "faster-whisper+vertex-gemini+ffmpeg",
            "path": relpath(render_path, project_dir),
            "analysis": relpath(analysis_path, project_dir),
        },
    )
    append_log(
        manifest,
        "recipe.semantic-highlights-expanded",
        "Rendered expanded semantic highlights for effect evaluation",
        output=relpath(render_path, project_dir),
        analysis=relpath(analysis_path, project_dir),
    )
    save_manifest(project_dir, manifest)
    return render_path


def recover_semantic_analysis(project_dir: Path, *, target_language: str = "中文", backend_name: str = "vertex-gemini") -> Path:
    assets_dir = project_dir / "assets"
    transcript_path = assets_dir / "source_transcript.json"
    raw_path = assets_dir / "gemini_semantic_response.raw.txt"
    if not transcript_path.exists():
        raise FileNotFoundError(transcript_path)
    if not raw_path.exists():
        raise FileNotFoundError(raw_path)
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    raw = raw_path.read_text(encoding="utf-8")
    plan = normalize_semantic_plan(
        parse_json_loose(raw),
        transcript=transcript,
        backend_name=backend_name,
        target_language=target_language,
    )
    plan["source_segments_preview"] = transcript.get("segments", [])[:20]
    output = assets_dir / "semantic_analysis.json"
    write_json(output, plan)
    write_json(
        assets_dir / "semantic_diagnostics.json",
        {
            "source": str((project_dir / load_manifest(project_dir)["input"]["path"]).resolve()),
            "stages": {
                "recover_semantic_analysis": {
                    "status": "ok",
                    "adapter": backend_name,
                    "raw_response": relpath(raw_path, project_dir),
                    "transcript": relpath(transcript_path, project_dir),
                    "highlight_count": len(plan.get("highlights", [])),
                    "chapter_count": len(plan.get("chapters", [])),
                    "note": "Recovered from cached Gemini semantic response after the long chunked translation stage stalled.",
                }
            },
        },
    )
    return output


def subtitle_highlights(project_dir: Path, *, render_id: str = "semantic_highlights_expanded") -> Path:
    manifest = load_manifest(project_dir)
    highlight = _render_by_id(project_dir, manifest, render_id)
    if highlight is None:
        raise FileNotFoundError(f"render id not found: {render_id}")
    expanded_path = project_dir / "assets" / "expanded_highlights.json"
    if not expanded_path.exists():
        raise FileNotFoundError(expanded_path)
    expanded = json.loads(expanded_path.read_text(encoding="utf-8"))
    translated_segments = _load_translated_segments(project_dir)
    subtitle_segments = _map_segments_to_highlight_timeline(expanded, translated_segments)
    subtitle_path = project_dir / "subtitles" / f"{render_id}_zh.srt"
    output = project_dir / "renders" / f"{render_id}_subtitled.mp4"
    log_file = project_dir / "logs" / f"{render_id}-subtitles.log"
    write_srt(subtitle_path, subtitle_segments)
    burn_subtitles(highlight, subtitle_path, output, log_file=log_file)
    upsert_by_id(
        manifest["transcripts"],
        {
            "id": f"{render_id}_zh_subtitles",
            "language": "zh-CN",
            "source_language": "en",
            "adapter": "gemini-translated-segments+ffmpeg-ass",
            "mode": "highlight-montage-subtitles",
            "path": relpath(subtitle_path, project_dir),
            "segments": subtitle_segments[:30],
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": f"{render_id}_subtitled",
            "recipe": "semantic-highlights-expanded-subtitled",
            "adapter": "gemini-translated-segments+ffmpeg-ass",
            "path": relpath(output, project_dir),
            "subtitle": relpath(subtitle_path, project_dir),
            "base_render": render_id,
        },
    )
    append_log(
        manifest,
        "recipe.semantic-highlights-expanded-subtitled",
        "Burned Chinese subtitles onto expanded semantic highlights",
        output=relpath(output, project_dir),
        subtitle=relpath(subtitle_path, project_dir),
    )
    save_manifest(project_dir, manifest)
    return output


def semantic_plan_only(
    project_dir: Path,
    *,
    highlights: int,
    chapters: int,
    source_language: str | None = None,
    target_language: str = "中文",
) -> Path:
    manifest = load_manifest(project_dir)
    source = (project_dir / manifest["input"]["path"]).resolve()
    assets_dir = project_dir / "assets"
    prompt_path = assets_dir / "gemini_micro_semantic_prompt.txt"
    raw_path = assets_dir / "gemini_micro_semantic_response.raw.txt"
    transcript_path = assets_dir / "source_transcript.json"
    diagnostics_path = assets_dir / "semantic_micro_diagnostics.json"
    transcript = transcribe_media(source, language=source_language)
    write_json(transcript_path, transcript)

    def capturing_llm(prompt: str) -> str:
        prompt_path.write_text(prompt, encoding="utf-8")
        raw = call_vertex_gemini(prompt)
        raw_path.write_text(raw, encoding="utf-8")
        return raw

    plan = build_semantic_creation_plan(
        transcript,
        llm_fn=capturing_llm,
        backend_name="vertex-gemini",
        target_language=target_language,
        highlight_count=highlights,
        chapter_count=chapters,
    )
    plan["source_segments_preview"] = transcript.get("segments", [])[:20]
    analysis_path = assets_dir / "semantic_analysis.json"
    write_json(analysis_path, plan)
    write_json(
        diagnostics_path,
        {
            "source": str(source),
            "stages": {
                "transcribe": {
                    "status": "ok",
                    "adapter": "faster-whisper",
                    "segment_count": len(transcript.get("segments", [])),
                    "duration": transcript.get("duration"),
                    "output": relpath(transcript_path, project_dir),
                },
                "gemini_semantic_analysis_only": {
                    "status": "ok",
                    "adapter": "vertex-gemini",
                    "requested_highlights": highlights,
                    "highlight_count": len(plan.get("highlights", [])),
                    "chapter_count": len(plan.get("chapters", [])),
                    "prompt": relpath(prompt_path, project_dir),
                    "raw_response": relpath(raw_path, project_dir),
                    "note": "Semantic plan only; intentionally skips full-transcript translation for long travel footage.",
                },
            },
        },
    )
    append_log(
        manifest,
        "recipe.semantic-plan-only",
        "Generated semantic highlight plan without full transcript translation",
        output=relpath(analysis_path, project_dir),
    )
    save_manifest(project_dir, manifest)
    return analysis_path


def render_micro_montage(
    project_dir: Path,
    *,
    target_seconds: float,
    clip_count: int,
    clip_seconds: float,
    source_language: str = "en",
    target_language: str = "中文",
) -> Path:
    manifest = load_manifest(project_dir)
    source = (project_dir / manifest["input"]["path"]).resolve()
    assets_dir = project_dir / "assets"
    analysis_path = assets_dir / "semantic_analysis.json"
    transcript_path = assets_dir / "source_transcript.json"
    if not analysis_path.exists():
        raise FileNotFoundError(analysis_path)
    if not transcript_path.exists():
        raise FileNotFoundError(transcript_path)
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    source_duration = ffprobe_duration(source)
    plan_items = _build_micro_items(
        analysis.get("highlights", []),
        source_duration=source_duration,
        target_seconds=target_seconds,
        clip_count=clip_count,
        clip_seconds=clip_seconds,
    )
    translated_segments = _translate_micro_segments(
        transcript,
        plan_items,
        source_language=source_language,
        target_language=target_language,
    )
    clips: list[Path] = []
    log_file = project_dir / "logs" / "micro-food-highlights.log"
    for index, item in enumerate(plan_items, start=1):
        clip_id = f"micro_food_highlight_{index:02}"
        clip_path = project_dir / "clips" / f"{clip_id}.mp4"
        render_clip(source, clip_path, item["start"], item["end"] - item["start"], log_file=log_file)
        clips.append(clip_path)
        upsert_by_id(
            manifest["clips"],
            {
                "id": clip_id,
                "recipe": "micro-food-highlights",
                "adapter": "vertex-gemini+ffmpeg",
                "path": relpath(clip_path, project_dir),
                "start": item["start"],
                "end": item["end"],
                "score": item.get("score"),
                "role": "micro_highlight",
                "title": item.get("title", ""),
                "virality_reason": item.get("virality_reason", ""),
            },
        )
    montage_path = project_dir / "renders" / "micro_food_highlights.mp4"
    concat_videos_reencode(clips, montage_path, log_file=log_file)
    subtitle_segments = _map_segments_to_highlight_timeline(plan_items, translated_segments)
    subtitle_path = project_dir / "subtitles" / "micro_food_highlights_zh.srt"
    subtitled_path = project_dir / "renders" / "micro_food_highlights_subtitled.mp4"
    write_srt(subtitle_path, subtitle_segments)
    burn_subtitles(montage_path, subtitle_path, subtitled_path, log_file=log_file)
    micro_path = assets_dir / "micro_food_highlights.json"
    write_json(
        micro_path,
        {
            "target_seconds": target_seconds,
            "clip_count": len(plan_items),
            "items": plan_items,
            "subtitle_segments": subtitle_segments,
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": "micro_food_highlights",
            "recipe": "micro-food-highlights",
            "adapter": "vertex-gemini+ffmpeg",
            "path": relpath(montage_path, project_dir),
            "analysis": relpath(micro_path, project_dir),
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": "micro_food_highlights_subtitled",
            "recipe": "micro-food-highlights",
            "adapter": "vertex-gemini+ffmpeg-ass",
            "path": relpath(subtitled_path, project_dir),
            "subtitle": relpath(subtitle_path, project_dir),
            "analysis": relpath(micro_path, project_dir),
        },
    )
    append_log(
        manifest,
        "recipe.micro-food-highlights",
        "Rendered sub-minute travel food micro highlight montage",
        output=relpath(subtitled_path, project_dir),
        analysis=relpath(micro_path, project_dir),
    )
    save_manifest(project_dir, manifest)
    return subtitled_path


def _build_micro_items(
    highlights: list[dict[str, Any]],
    *,
    source_duration: float,
    target_seconds: float,
    clip_count: int,
    clip_seconds: float,
) -> list[dict[str, Any]]:
    ranked = sorted(
        [item for item in highlights if "start_time" in item and "end_time" in item],
        key=lambda item: int(item.get("score", 0)),
        reverse=True,
    )[:clip_count]
    if not ranked:
        raise RuntimeError("semantic plan has no highlights for micro montage")
    per_clip = min(clip_seconds, max(1.8, target_seconds / max(len(ranked), 1)))
    items: list[dict[str, Any]] = []
    for item in ranked:
        start = float(item["start_time"])
        end = float(item["end_time"])
        center = start + min(max((end - start) * 0.35, per_clip / 2), max(end - start, per_clip) / 2)
        micro_start = max(0.0, min(center - per_clip / 2, source_duration - per_clip))
        micro_end = min(source_duration, micro_start + per_clip)
        items.append(
            {
                "start": round(micro_start, 3),
                "end": round(micro_end, 3),
                "title": normalize_display_text(item.get("title", ""), strict=False),
                "hook_sentence": normalize_display_text(item.get("hook_sentence", ""), strict=False),
                "virality_reason": normalize_display_text(item.get("virality_reason", ""), strict=False),
                "score": item.get("score"),
            }
        )
    items.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    total = sum(float(item["end"]) - float(item["start"]) for item in items)
    while total > target_seconds and len(items) > 1:
        item = items.pop()
        total -= float(item["end"]) - float(item["start"])
    return items


def _translate_micro_segments(
    transcript: dict[str, Any],
    micro_items: list[dict[str, Any]],
    *,
    source_language: str,
    target_language: str,
) -> list[dict[str, Any]]:
    selected: dict[int, dict[str, Any]] = {}
    for item in micro_items:
        start = float(item["start"])
        end = float(item["end"])
        for index, segment in enumerate(transcript.get("segments", [])):
            segment_start = float(segment.get("start", 0.0))
            segment_end = float(segment.get("end", 0.0))
            if segment_end <= start or segment_start >= end:
                continue
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            selected[index] = {
                "index": index,
                "start": segment_start,
                "end": segment_end,
                "text": text,
            }
    if not selected:
        return []
    translation_map: dict[int, str] = {}
    selected_items = list(selected.values())
    for start in range(0, len(selected_items), 8):
        chunk = selected_items[start : start + 8]
        translation_map.update(
            translate_segment_chunk(
                chunk,
                llm_fn=call_vertex_gemini,
                target_language=target_language,
                source_language=source_language,
            )
        )
    translated: list[dict[str, Any]] = []
    for index, segment in sorted(selected.items()):
        translated.append(
            {
                "start": segment["start"],
                "end": segment["end"],
                "text": normalize_display_text(translation_map.get(index) or segment["text"], strict=False),
            }
        )
    return translated


def _load_translated_segments(project_dir: Path) -> list[dict[str, Any]]:
    assets_dir = project_dir / "assets"
    analysis_path = assets_dir / "semantic_analysis.json"
    transcript_path = assets_dir / "source_transcript.json"
    if not analysis_path.exists():
        raise FileNotFoundError(analysis_path)
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    segments = [
        _segment_with_normalized_text(item)
        for item in analysis.get("translated_segments", [])
        if _segment_has_text(item)
    ]
    if _looks_chinese(segments):
        return segments

    chunks_path = assets_dir / "gemini_translation_chunks.jsonl"
    if chunks_path.exists() and transcript_path.exists():
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        rebuilt = _segments_from_translation_chunks(transcript, chunks_path)
        if rebuilt:
            write_json(assets_dir / "translated_segments_recovered.json", {"segments": rebuilt})
            return rebuilt
    return segments


def _segments_from_translation_chunks(transcript: dict[str, Any], chunks_path: Path) -> list[dict[str, Any]]:
    translations: dict[int, str] = {}
    for line in chunks_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        try:
            parsed = parse_json_loose(str(item.get("response", "")))
        except Exception:
            continue
        for translated in parsed.get("translations", []) or []:
            if isinstance(translated, dict) and "index" in translated:
                translations[int(translated["index"])] = normalize_display_text(translated.get("text", ""))
    rebuilt: list[dict[str, Any]] = []
    for index, segment in enumerate(transcript.get("segments", [])):
        text = translations.get(index)
        if not text:
            continue
        rebuilt.append(
            {
                "start": float(segment.get("start", 0.0)),
                "end": float(segment.get("end", 0.0)),
                "text": text,
            }
        )
    return rebuilt


def _map_segments_to_highlight_timeline(
    expanded: list[dict[str, Any]],
    translated_segments: list[dict[str, Any]],
) -> list[dict[str, object]]:
    subtitle_segments: list[dict[str, object]] = []
    timeline_cursor = 0.0
    for highlight in expanded:
        source_start = float(highlight["start"])
        source_end = float(highlight["end"])
        for segment in translated_segments:
            segment_start = float(segment["start"])
            segment_end = float(segment["end"])
            if segment_end <= source_start or segment_start >= source_end:
                continue
            start = timeline_cursor + max(segment_start, source_start) - source_start
            end = timeline_cursor + min(segment_end, source_end) - source_start
            if end - start < 0.25:
                continue
            text = normalize_display_text(segment.get("text", ""))
            if not text:
                continue
            subtitle_segments.append({"start": round(start, 3), "end": round(end, 3), "text": text})
        timeline_cursor += source_end - source_start
    return subtitle_segments


def _merge_tiny_gaps(segments: list[dict[str, object]]) -> list[dict[str, object]]:
    if not segments:
        return []
    merged: list[dict[str, object]] = []
    for segment in segments:
        if (
            merged
            and float(segment["start"]) - float(merged[-1]["end"]) < 0.08
            and len(str(merged[-1]["text"])) + len(str(segment["text"])) <= 34
        ):
            merged[-1]["end"] = segment["end"]
            merged[-1]["text"] = f"{merged[-1]['text']} {segment['text']}"
            continue
        merged.append(segment)
    return merged


def _segment_has_text(item: dict[str, Any]) -> bool:
    return isinstance(item, dict) and "start" in item and "end" in item and str(item.get("text", "")).strip()


def _segment_with_normalized_text(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "start": float(item.get("start", 0.0)),
        "end": float(item.get("end", 0.0)),
        "text": normalize_display_text(item.get("text", ""), strict=False),
    }


def _looks_chinese(segments: list[dict[str, Any]]) -> bool:
    sample = "".join(str(item.get("text", "")) for item in segments[:20])
    return any("\u4e00" <= char <= "\u9fff" for char in sample)


def build_fusion(summary_video: Path, translated_video: Path, output: Path, *, summary_seconds: float | None = None) -> Path:
    inputs = [summary_video]
    if summary_seconds is not None and ffprobe_duration(summary_video) > summary_seconds:
        trimmed = output.with_name(output.stem + "_summary_trim.mp4")
        render_clip(summary_video, trimmed, 0, summary_seconds)
        inputs = [trimmed]
    inputs.append(translated_video)
    return concat_videos_reencode(inputs, output)


def package_report(report_dir: Path, cases: list[CaseSpec]) -> Path:
    videos_dir = report_dir / "videos"
    report_dir.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)
    rendered_cases: list[dict[str, Any]] = []
    for case in cases:
        project = load_manifest(case.project_dir)
        source = (case.project_dir / project["input"]["path"]).resolve()
        highlight = _render_by_id(case.project_dir, project, "semantic_highlights_expanded_subtitled") or _render_by_id(
            case.project_dir,
            project,
            "semantic_highlights_expanded",
        )
        fusion = case.case_dir / "fusion_summary_plus_translation.mp4"
        expanded_json = case.project_dir / "assets" / "expanded_highlights.json"
        reasons = json.loads(expanded_json.read_text(encoding="utf-8")) if expanded_json.exists() else []

        copied = {
            "highlight": _copy_video(highlight, videos_dir / f"{case.slug}_highlight.mp4") if highlight else None,
            "fusion": _copy_video(fusion, videos_dir / f"{case.slug}_fusion.mp4") if fusion.exists() else None,
            "translation": (
                _copy_video(case.translation_video, videos_dir / f"{case.slug}_translation.mp4")
                if case.translation_video and case.translation_video.exists()
                else None
            ),
            "translation_source": (
                _copy_video(case.translation_source, videos_dir / f"{case.slug}_translation_source.mp4")
                if case.translation_source and case.translation_source.exists()
                else None
            ),
        }
        rendered_cases.append(
            {
                "slug": case.slug,
                "label": case.label,
                "category": case.category,
                "source_url": case.source_url,
                "source_duration": ffprobe_duration(source),
                "translation_duration": ffprobe_duration(case.translation_video)
                if case.translation_video and case.translation_video.exists()
                else None,
                "highlight_duration": ffprobe_duration(highlight) if highlight and highlight.exists() else None,
                "fusion_duration": ffprobe_duration(fusion) if fusion.exists() else None,
                "videos": copied,
                "reasons": reasons,
            }
        )

    report_path = report_dir / "index.html"
    report_path.write_text(_render_html(rendered_cases), encoding="utf-8")
    return report_path


def _render_by_id(project_dir: Path, manifest: dict[str, Any], render_id: str) -> Path | None:
    for item in manifest.get("renders", []):
        if item.get("id") == render_id:
            return (project_dir / item["path"]).resolve()
    return None


def _copy_video(source: Path, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return str(dest.relative_to(dest.parent.parent))


def _render_html(cases: list[dict[str, Any]]) -> str:
    case_html = "\n".join(_render_case(case) for case in cases)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LogicCut 效果评测报告</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #05070d;
      --panel: #101624;
      --panel-2: #151d2e;
      --line: rgba(102, 232, 255, .32);
      --cyan: #35e4ff;
      --violet: #b857ff;
      --text: #f5f7fb;
      --muted: #aab4c8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 20% 0%, rgba(96, 58, 255, .28), transparent 32rem),
        radial-gradient(circle at 100% 8%, rgba(25, 230, 255, .16), transparent 28rem),
        var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans CJK SC", sans-serif;
    }}
    header {{
      min-height: 52vh;
      display: grid;
      align-items: center;
      padding: 7vw 7vw 4vw;
      border-bottom: 1px solid var(--line);
      background:
        linear-gradient(90deg, rgba(53, 228, 255, .18), transparent 24rem),
        linear-gradient(135deg, rgba(184, 87, 255, .24), rgba(22, 37, 80, .12));
    }}
    h1 {{
      max-width: 1080px;
      margin: 0;
      font-size: clamp(42px, 7vw, 96px);
      line-height: .98;
      letter-spacing: 0;
      text-transform: none;
    }}
    .lead {{
      max-width: 900px;
      margin: 26px 0 0;
      color: var(--muted);
      font-size: clamp(17px, 2vw, 24px);
      line-height: 1.55;
    }}
    main {{ padding: 42px 7vw 90px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-bottom: 38px;
    }}
    .metric {{
      background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.03));
      border: 1px solid var(--line);
      padding: 18px;
      border-radius: 8px;
    }}
    .metric strong {{ display: block; font-size: 26px; color: var(--cyan); }}
    .metric span {{ color: var(--muted); font-size: 13px; }}
    section {{
      margin: 0 0 64px;
      padding: 28px;
      border: 1px solid rgba(255,255,255,.14);
      background: linear-gradient(180deg, rgba(16,22,36,.96), rgba(9,13,22,.96));
      border-radius: 8px;
      box-shadow: 0 24px 80px rgba(0,0,0,.32);
    }}
    h2 {{ margin: 0 0 8px; font-size: clamp(28px, 3.8vw, 52px); }}
    .meta {{ margin: 0 0 24px; color: var(--muted); }}
    .video-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 18px;
    }}
    figure {{
      margin: 0;
      background: var(--panel-2);
      border: 1px solid rgba(255,255,255,.12);
      border-radius: 8px;
      overflow: hidden;
    }}
    video {{ display: block; width: 100%; background: #000; aspect-ratio: 16 / 9; }}
    figcaption {{ padding: 13px 14px; color: var(--muted); font-size: 14px; }}
    figcaption b {{ color: var(--text); }}
    .reasons {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .reason {{
      border-left: 3px solid var(--cyan);
      padding: 14px 15px;
      background: rgba(255,255,255,.04);
      border-radius: 6px;
    }}
    .reason h3 {{ margin: 0 0 8px; font-size: 17px; }}
    .reason p {{ margin: 0; color: var(--muted); line-height: 1.55; font-size: 14px; }}
    a {{ color: var(--cyan); }}
    code {{ color: var(--cyan); }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>LogicCut 三类视频效果评测</h1>
      <p class="lead">本轮按“长视频做语义高光，短片段做翻译验证，高光摘要拼到翻译样例前面”的方式，覆盖播客、短剧、影视三种创作者搬运场景。</p>
    </div>
  </header>
  <main>
    <div class="metrics">
      <div class="metric"><strong>{len(cases)}</strong><span>视频类型</span></div>
      <div class="metric"><strong>3</strong><span>交付版本：翻译 / 高光 / 融合</span></div>
      <div class="metric"><strong>长视频</strong><span>高光剪辑基于完整素材</span></div>
      <div class="metric"><strong>短样例</strong><span>翻译只验证可听可看链路</span></div>
    </div>
    {case_html}
  </main>
</body>
</html>
"""


def _render_case(case: dict[str, Any]) -> str:
    videos = case["videos"]
    figures = []
    for key, title in [
        ("translation_source", "翻译输入片段"),
        ("translation", "中文翻译配音/字幕"),
        ("highlight", "完整素材语义高光（中文字幕）"),
        ("fusion", "高光摘要 + 翻译样例"),
    ]:
        if videos.get(key):
            figures.append(
                f"""<figure>
  <video src="{html.escape(videos[key])}" controls preload="metadata"></video>
  <figcaption><b>{title}</b></figcaption>
</figure>"""
            )
    reason_html = "\n".join(
        f"""<div class="reason">
  <h3>{html.escape(str(item.get("title", "高光片段")))}</h3>
  <p>{html.escape(_format_time(item.get("start", 0)))} - {html.escape(_format_time(item.get("end", 0)))} · {html.escape(str(item.get("virality_reason") or item.get("hook_sentence") or "语义模型选择的高信息密度片段"))}</p>
</div>"""
        for item in case.get("reasons", [])
    )
    return f"""<section>
  <h2>{html.escape(case["label"])}</h2>
  <p class="meta">{html.escape(case["category"])} · 原视频 {case["source_duration"]:.0f}s · <a href="{html.escape(case["source_url"])}">YouTube 源链接</a></p>
  <div class="video-grid">
    {''.join(figures)}
  </div>
  <div class="reasons">
    {reason_html}
  </div>
</section>"""


def _format_time(value: float) -> str:
    seconds = int(float(value))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _case_from_json(data: dict[str, Any]) -> CaseSpec:
    return CaseSpec(
        slug=data["slug"],
        label=data["label"],
        category=data["category"],
        source_url=data["source_url"],
        case_dir=Path(data["case_dir"]),
        project_dir=Path(data["project_dir"]),
        translation_video=Path(data["translation_video"]) if data.get("translation_video") else None,
        translation_source=Path(data["translation_source"]) if data.get("translation_source") else None,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    expand = subparsers.add_parser("expand")
    expand.add_argument("--project-dir", required=True, type=Path)
    expand.add_argument("--context-before", type=float, default=10)
    expand.add_argument("--context-after", type=float, default=16)
    expand.add_argument("--min-duration", type=float, default=24)
    expand.add_argument("--merge-gap", type=float, default=2)
    expand.add_argument("--max-items", type=int, default=5)

    recover = subparsers.add_parser("recover-semantic")
    recover.add_argument("--project-dir", required=True, type=Path)
    recover.add_argument("--target-language", default="中文")
    recover.add_argument("--backend-name", default="vertex-gemini")

    plan_only = subparsers.add_parser("semantic-plan-only")
    plan_only.add_argument("--project-dir", required=True, type=Path)
    plan_only.add_argument("--highlights", type=int, default=18)
    plan_only.add_argument("--chapters", type=int, default=6)
    plan_only.add_argument("--source-language", default=None)
    plan_only.add_argument("--target-language", default="中文")

    micro = subparsers.add_parser("micro-montage")
    micro.add_argument("--project-dir", required=True, type=Path)
    micro.add_argument("--target-seconds", type=float, default=58)
    micro.add_argument("--clip-count", type=int, default=18)
    micro.add_argument("--clip-seconds", type=float, default=3.2)
    micro.add_argument("--source-language", default="en")
    micro.add_argument("--target-language", default="中文")

    subtitle = subparsers.add_parser("subtitle-highlights")
    subtitle.add_argument("--project-dir", required=True, type=Path)
    subtitle.add_argument("--render-id", default="semantic_highlights_expanded")

    fusion = subparsers.add_parser("fusion")
    fusion.add_argument("--summary-video", required=True, type=Path)
    fusion.add_argument("--translated-video", required=True, type=Path)
    fusion.add_argument("--output", required=True, type=Path)
    fusion.add_argument("--summary-seconds", type=float, default=60)

    package = subparsers.add_parser("package")
    package.add_argument("--cases-json", required=True, type=Path)
    package.add_argument("--report-dir", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "expand":
        print(expand_highlights(args.project_dir, context_before=args.context_before, context_after=args.context_after, min_duration=args.min_duration, merge_gap=args.merge_gap, max_items=args.max_items))
        return 0
    if args.command == "recover-semantic":
        print(recover_semantic_analysis(args.project_dir, target_language=args.target_language, backend_name=args.backend_name))
        return 0
    if args.command == "semantic-plan-only":
        print(semantic_plan_only(args.project_dir, highlights=args.highlights, chapters=args.chapters, source_language=args.source_language, target_language=args.target_language))
        return 0
    if args.command == "micro-montage":
        print(render_micro_montage(args.project_dir, target_seconds=args.target_seconds, clip_count=args.clip_count, clip_seconds=args.clip_seconds, source_language=args.source_language, target_language=args.target_language))
        return 0
    if args.command == "subtitle-highlights":
        print(subtitle_highlights(args.project_dir, render_id=args.render_id))
        return 0
    if args.command == "fusion":
        print(build_fusion(args.summary_video, args.translated_video, args.output, summary_seconds=args.summary_seconds))
        return 0
    if args.command == "package":
        cases = [_case_from_json(item) for item in json.loads(args.cases_json.read_text(encoding="utf-8"))]
        print(package_report(args.report_dir, cases))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
