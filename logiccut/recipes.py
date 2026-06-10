from __future__ import annotations

import json
import os
import html as html_lib
import shutil
from pathlib import Path
from typing import Any

from .chapter_narration import (
    build_narration_text,
    mix_card_with_narration,
    prepare_narration_reference,
    safe_audio_duration,
    synthesize_narration_audio,
    write_narration_srt,
)
from .creator_styles import (
    build_cut_explanation,
    build_personalized_narration,
    get_creator_style,
    parse_catchphrases,
    parse_layouts,
    parse_style_ids,
)
from .html_cards import build_highlight_card, render_html_card_video
from .manifest import append_log, create_manifest, load_manifest, relpath, save_manifest, upsert_by_id
from .media import (
    burn_subtitles,
    concat_videos,
    concat_videos_reencode,
    ffprobe_duration,
    ffprobe_video_size,
    render_text_watermark,
    render_clip,
    render_text_card,
    write_srt,
)
from .portrait_web import render_portrait_web_video
from .semantic import (
    build_semantic_creation_plan,
    call_vertex_gemini,
    normalize_semantic_text_fields,
    transcribe_media,
    translate_transcript_segments,
    write_json,
)
from .story_planner import build_story_timeline_from_semantic_plan
from .story_render import render_story_timeline
from .text_normalize import normalize_display_text
from .theme_opener import (
    load_theme_opener_plan,
    write_theme_opener_codex_prompt,
)
from .video_translate_refine import config_from_env, run_video_translate_refine


RECIPE_IDS = ("translate-remix", "highlight-first", "chapter-clips")
SEMANTIC_RECIPE_IDS = (
    "video-translation",
    "semantic-highlights",
    "creator-remix",
    "chapter-card-narration",
    "guided-highlights",
    "story-guided-highlights",
)
_SEMANTIC_REFRESHED_PROJECTS: set[Path] = set()


def init_project(input_path: Path, project_dir: Path, title: str | None = None) -> dict[str, Any]:
    input_path = input_path.resolve()
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    for name in ("clips", "renders", "subtitles", "logs", "assets"):
        (project_dir / name).mkdir(parents=True, exist_ok=True)
    manifest = create_manifest(project_dir, input_path, title=title)
    append_log(manifest, "project.init", "Project initialized", input=manifest["input"]["path"])
    save_manifest(project_dir, manifest)
    return manifest


def run_recipe(project_dir: Path, recipe: str, chapters: int = 3) -> dict[str, Any]:
    if recipe == "all":
        manifest: dict[str, Any] = {}
        for item in RECIPE_IDS:
            manifest = run_recipe(project_dir, item, chapters=chapters)
        return manifest
    if recipe == "semantic-suite":
        manifest = {}
        for item in SEMANTIC_RECIPE_IDS:
            manifest = run_recipe(project_dir, item, chapters=chapters)
        return manifest
    if recipe == "translate-remix":
        return run_translate_remix(project_dir)
    if recipe == "highlight-first":
        return run_highlight_first(project_dir)
    if recipe == "chapter-clips":
        return run_chapter_clips(project_dir, chapters=chapters)
    if recipe == "video-translation":
        return run_video_translation(project_dir, chapters=chapters)
    if recipe == "semantic-highlights":
        return run_semantic_highlights(project_dir, chapters=chapters)
    if recipe == "creator-remix":
        return run_creator_remix(project_dir, chapters=chapters)
    if recipe == "chapter-card-narration":
        return run_chapter_card_narration(project_dir, chapters=chapters)
    if recipe == "guided-highlights":
        return run_guided_highlights(project_dir, chapters=chapters)
    if recipe == "story-guided-highlights":
        return run_story_guided_highlights(project_dir, chapters=chapters)
    if recipe == "theme-opener":
        return run_theme_opener(project_dir)
    if recipe == "personalized-highlights":
        return run_personalized_highlights(project_dir, chapters=chapters)
    raise ValueError(f"unknown recipe: {recipe}")


def run_translate_remix(project_dir: Path) -> dict[str, Any]:
    manifest = load_manifest(project_dir)
    source = _input_path(project_dir, manifest)
    duration = ffprobe_duration(source)
    log_file = project_dir / "logs" / "translate-remix.log"
    render_path = project_dir / "renders" / "translate_remix.mp4"
    subtitle_path = project_dir / "subtitles" / "translate_remix.srt"
    segment = {
        "start": 0.0,
        "end": min(duration, 4.0),
        "text": "LogicCut translated remix baseline.",
    }

    render_clip(source, render_path, 0.0, duration, log_file=log_file)
    write_srt(subtitle_path, [segment])

    upsert_by_id(
        manifest["transcripts"],
        {
            "id": "translate_remix_subtitle",
            "language": "zh-CN",
            "source_language": "auto",
            "adapter": "omnivoice-studio",
            "mode": "local-baseline",
            "path": relpath(subtitle_path, project_dir),
            "segments": [segment],
        },
    )
    upsert_by_id(
        manifest["tracks"],
        {
            "id": "source_audio",
            "kind": "audio",
            "adapter": "ffmpeg",
            "path": manifest["input"]["path"],
            "note": "Source audio is preserved in 0.3 baseline render.",
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": "translate_remix",
            "recipe": "translate-remix",
            "adapter": "omnivoice-studio",
            "mode": "local-baseline",
            "path": relpath(render_path, project_dir),
            "subtitle": relpath(subtitle_path, project_dir),
        },
    )
    _mark_recipe(manifest, "translate-remix", "ok", "Rendered translated remix baseline")
    append_log(manifest, "recipe.translate-remix", "Rendered translate remix", output=relpath(render_path, project_dir))
    save_manifest(project_dir, manifest)
    return manifest


def run_highlight_first(project_dir: Path) -> dict[str, Any]:
    manifest = load_manifest(project_dir)
    source = _input_path(project_dir, manifest)
    duration = ffprobe_duration(source)
    hook_duration = min(max(duration * 0.35, 1.0), duration, 5.0)
    log_file = project_dir / "logs" / "highlight-first.log"
    hook_path = project_dir / "clips" / "highlight_hook.mp4"
    body_path = project_dir / "clips" / "highlight_body.mp4"
    render_path = project_dir / "renders" / "highlight_first.mp4"

    render_clip(source, hook_path, 0.0, hook_duration, log_file=log_file)
    render_clip(source, body_path, 0.0, duration, log_file=log_file)
    concat_videos([hook_path, body_path], render_path, log_file=log_file)

    upsert_by_id(
        manifest["clips"],
        {
            "id": "highlight_hook",
            "recipe": "highlight-first",
            "adapter": "logiccut-ffmpeg",
            "path": relpath(hook_path, project_dir),
            "start": 0.0,
            "end": hook_duration,
            "score": 0.9,
            "role": "hook",
        },
    )
    upsert_by_id(
        manifest["timeline"],
        {
            "id": "highlight_first_timeline",
            "recipe": "highlight-first",
            "items": [
                {"clip_id": "highlight_hook", "role": "hook"},
                {"input": manifest["input"]["path"], "role": "body"},
            ],
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": "highlight_first",
            "recipe": "highlight-first",
            "adapter": "logiccut-ffmpeg",
            "path": relpath(render_path, project_dir),
        },
    )
    _mark_recipe(manifest, "highlight-first", "ok", "Rendered hook-first video")
    append_log(manifest, "recipe.highlight-first", "Rendered highlight-first video", output=relpath(render_path, project_dir))
    save_manifest(project_dir, manifest)
    return manifest


def run_chapter_clips(project_dir: Path, chapters: int = 3) -> dict[str, Any]:
    manifest = load_manifest(project_dir)
    source = _input_path(project_dir, manifest)
    duration = ffprobe_duration(source)
    count = max(1, chapters)
    segment_length = duration / count
    log_file = project_dir / "logs" / "chapter-clips.log"
    chapter_items: list[dict[str, Any]] = []

    for index in range(count):
        start = index * segment_length
        end = duration if index == count - 1 else (index + 1) * segment_length
        clip_id = f"chapter_{index + 1:02}"
        clip_path = project_dir / "clips" / f"{clip_id}.mp4"
        render_clip(source, clip_path, start, max(end - start, 0.1), log_file=log_file)
        item = {
            "id": clip_id,
            "recipe": "chapter-clips",
            "adapter": "logiccut-ffmpeg",
            "path": relpath(clip_path, project_dir),
            "start": start,
            "end": end,
            "role": "chapter",
            "title": f"Chapter {index + 1}",
        }
        upsert_by_id(manifest["clips"], item)
        chapter_items.append({"clip_id": clip_id, "role": "chapter"})

    upsert_by_id(
        manifest["timeline"],
        {
            "id": "chapter_clips_timeline",
            "recipe": "chapter-clips",
            "items": chapter_items,
        },
    )
    _mark_recipe(manifest, "chapter-clips", "ok", f"Rendered {count} chapter clips")
    append_log(manifest, "recipe.chapter-clips", f"Rendered {count} chapter clips")
    save_manifest(project_dir, manifest)
    return manifest


def run_video_translation(project_dir: Path, chapters: int = 4) -> dict[str, Any]:
    backend = os.environ.get("LOGICCUT_VIDEO_TRANSLATION_BACKEND", "video-translate-refine").strip()
    if backend in {"semantic", "legacy", "faster-whisper-gemini"}:
        return run_video_translation_legacy(project_dir, chapters=chapters)
    if backend in {"video-translate-refine", "vtr", "refine"}:
        return run_video_translate_refine_recipe(project_dir)
    raise ValueError(f"unknown LOGICCUT_VIDEO_TRANSLATION_BACKEND: {backend}")


def run_video_translate_refine_recipe(project_dir: Path) -> dict[str, Any]:
    manifest = load_manifest(project_dir)
    source = _input_path(project_dir, manifest)
    output_dir = project_dir / "renders" / "video_translation_refine"
    clip_raw = os.environ.get("LOGICCUT_VIDEO_TRANSLATION_CLIP_SECONDS", "").strip()
    clip_seconds = int(clip_raw) if clip_raw else None
    result = run_video_translate_refine(
        config_from_env(
            video=source,
            output_dir=output_dir,
            clip_seconds=clip_seconds,
        )
    )

    upsert_by_id(
        manifest["transcripts"],
        {
            "id": "video_translation_manifest",
            "language": os.environ.get("LOGICCUT_TARGET_LANGUAGE", "中文"),
            "source_language": os.environ.get("LOGICCUT_SOURCE_LANGUAGE", "en"),
            "adapter": "video-translate-refine",
            "mode": "profile-wrapper",
            "path": relpath(result.manifest_path, project_dir),
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": "video_translation",
            "recipe": "video-translation",
            "adapter": "video-translate-refine",
            "path": relpath(result.output_video, project_dir),
            "upstream_run_dir": str(result.run_dir),
            "log": relpath(result.log_path, project_dir),
            "manifest": relpath(result.manifest_path, project_dir),
        },
    )
    _mark_recipe(manifest, "video-translation", "ok", "Rendered video-translate-refine translation")
    append_log(
        manifest,
        "recipe.video-translation",
        "Rendered video translation with video-translate-refine",
        output=relpath(result.output_video, project_dir),
        upstream_run_dir=str(result.run_dir),
    )
    save_manifest(project_dir, manifest)
    return manifest


def run_video_translation_legacy(project_dir: Path, chapters: int = 4) -> dict[str, Any]:
    manifest = load_manifest(project_dir)
    source = _input_path(project_dir, manifest)
    plan = _ensure_semantic_plan(project_dir, chapters=chapters)
    log_file = project_dir / "logs" / "video-translation.log"
    subtitle_path = project_dir / "subtitles" / "video_translation.srt"
    render_path = project_dir / "renders" / "video_translation.mp4"

    write_srt(subtitle_path, plan["translated_segments"])
    burn_subtitles(source, subtitle_path, render_path, log_file=log_file)

    upsert_by_id(
        manifest["transcripts"],
        {
            "id": "source_transcript",
            "language": "auto",
            "adapter": "faster-whisper",
            "path": "assets/source_transcript.json",
            "segments": plan.get("source_segments_preview", []),
        },
    )
    upsert_by_id(
        manifest["transcripts"],
        {
            "id": "video_translation_subtitle",
            "language": plan["analysis_meta"]["target_language"],
            "source_language": "auto",
            "adapter": "faster-whisper+vertex-gemini",
            "mode": "semantic-subtitle-translation",
            "path": relpath(subtitle_path, project_dir),
            "segments": plan["translated_segments"][:20],
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": "video_translation",
            "recipe": "video-translation",
            "adapter": "faster-whisper+vertex-gemini+ffmpeg",
            "path": relpath(render_path, project_dir),
            "subtitle": relpath(subtitle_path, project_dir),
            "analysis": "assets/semantic_analysis.json",
        },
    )
    _mark_recipe(manifest, "video-translation", "ok", "Rendered Gemini-translated subtitle video")
    append_log(
        manifest,
        "recipe.video-translation",
        "Rendered semantic video translation",
        output=relpath(render_path, project_dir),
        analysis="assets/semantic_analysis.json",
    )
    save_manifest(project_dir, manifest)
    return manifest


def run_semantic_highlights(project_dir: Path, chapters: int = 4) -> dict[str, Any]:
    manifest = load_manifest(project_dir)
    source = _input_path(project_dir, manifest)
    plan = _ensure_semantic_plan(project_dir, chapters=chapters)
    log_file = project_dir / "logs" / "semantic-highlights.log"
    render_path = project_dir / "renders" / "semantic_highlights.mp4"
    highlight_paths: list[Path] = []
    render_count = int(
        os.environ.get(
            "LOGICCUT_RENDER_HIGHLIGHT_COUNT",
            os.environ.get("LOGICCUT_HIGHLIGHT_COUNT", "3"),
        )
    )

    for index, highlight in enumerate(plan["highlights"][: max(1, render_count)], start=1):
        clip_id = f"semantic_highlight_{index:02}"
        start = float(highlight["start_time"])
        end = float(highlight["end_time"])
        clip_path = project_dir / "clips" / f"{clip_id}.mp4"
        render_clip(source, clip_path, start, end - start, log_file=log_file)
        highlight_paths.append(clip_path)
        upsert_by_id(
            manifest["clips"],
            {
                "id": clip_id,
                "recipe": "semantic-highlights",
                "adapter": "faster-whisper+vertex-gemini+ffmpeg",
                "path": relpath(clip_path, project_dir),
                "start": start,
                "end": end,
                "score": highlight["score"],
                "role": "semantic_highlight",
                "title": highlight["title"],
                "hook_sentence": highlight["hook_sentence"],
                "virality_reason": highlight["virality_reason"],
            },
        )

    concat_videos_reencode(highlight_paths, render_path, log_file=log_file)
    upsert_by_id(
        manifest["timeline"],
        {
            "id": "semantic_highlights_timeline",
            "recipe": "semantic-highlights",
            "items": [{"clip_id": f"semantic_highlight_{idx:02}", "role": "highlight"} for idx in range(1, len(highlight_paths) + 1)],
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": "semantic_highlights",
            "recipe": "semantic-highlights",
            "adapter": "faster-whisper+vertex-gemini+ffmpeg",
            "path": relpath(render_path, project_dir),
            "analysis": "assets/semantic_analysis.json",
        },
    )
    _mark_recipe(manifest, "semantic-highlights", "ok", "Rendered semantic highlight montage")
    append_log(manifest, "recipe.semantic-highlights", "Rendered semantic highlights", output=relpath(render_path, project_dir))
    save_manifest(project_dir, manifest)
    return manifest


def run_creator_remix(project_dir: Path, chapters: int = 4) -> dict[str, Any]:
    run_video_translation(project_dir, chapters=chapters)
    run_semantic_highlights(project_dir, chapters=chapters)

    manifest = load_manifest(project_dir)
    source = _input_path(project_dir, manifest)
    plan = _ensure_semantic_plan(project_dir, chapters=chapters)
    translated_body = _render_path_by_id(
        project_dir,
        manifest,
        "video_translation",
        fallback=project_dir / "renders" / "video_translation.mp4",
    )
    log_file = project_dir / "logs" / "creator-remix.log"
    size = ffprobe_video_size(source)
    cards_dir = project_dir / "assets" / "cards"

    opener_text = str(plan.get("remix", {}).get("opening_summary") or plan.get("summary") or "LogicCut remix")
    intro_card = render_text_card(cards_dir / "opening_summary.mp4", opener_text, duration=3.2, size=size, log_file=log_file)

    summary_inputs = [intro_card]
    for index, highlight in enumerate(plan["highlights"][:2], start=1):
        clip_path = project_dir / "clips" / f"fusion_hook_{index:02}.mp4"
        start = float(highlight["start_time"])
        end = min(float(highlight["end_time"]), start + 5.0)
        render_clip(source, clip_path, start, end - start, log_file=log_file)
        summary_inputs.append(clip_path)
    summary_inputs.append(translated_body)

    summary_render = project_dir / "renders" / "fusion_summary_first.mp4"
    concat_videos_reencode(summary_inputs, summary_render, log_file=log_file)

    chapter_inputs: list[Path] = []
    chapter_items: list[dict[str, Any]] = []
    for index, chapter in enumerate(plan["chapters"][: max(1, chapters)], start=1):
        title = chapter.get("title") or f"Chapter {index}"
        summary = chapter.get("summary") or chapter.get("insert_strategy") or title
        card = render_text_card(
            cards_dir / f"chapter_{index:02}_summary.mp4",
            f"{title}\n{summary}",
            duration=2.8,
            size=size,
            log_file=log_file,
        )
        clip = project_dir / "clips" / f"fusion_chapter_{index:02}.mp4"
        start = float(chapter["start_time"])
        end = float(chapter["end_time"])
        render_clip(translated_body, clip, start, end - start, log_file=log_file)
        chapter_inputs.extend([card, clip])
        chapter_items.append(
            {
                "card": relpath(card, project_dir),
                "clip": relpath(clip, project_dir),
                "role": "chapter_summary_then_translation",
                "title": title,
                "summary": summary,
            }
        )

    chapter_render = project_dir / "renders" / "fusion_chapterized.mp4"
    concat_videos_reencode(chapter_inputs, chapter_render, log_file=log_file)

    upsert_by_id(
        manifest["timeline"],
        {
            "id": "fusion_summary_first_timeline",
            "recipe": "creator-remix",
            "items": [{"path": relpath(path, project_dir)} for path in summary_inputs],
            "concept": opener_text,
        },
    )
    upsert_by_id(
        manifest["timeline"],
        {
            "id": "fusion_chapterized_timeline",
            "recipe": "creator-remix",
            "items": chapter_items,
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": "fusion_summary_first",
            "recipe": "creator-remix",
            "adapter": "faster-whisper+vertex-gemini+ffmpeg",
            "path": relpath(summary_render, project_dir),
            "analysis": "assets/semantic_analysis.json",
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": "fusion_chapterized",
            "recipe": "creator-remix",
            "adapter": "faster-whisper+vertex-gemini+ffmpeg",
            "path": relpath(chapter_render, project_dir),
            "analysis": "assets/semantic_analysis.json",
        },
    )
    _mark_recipe(manifest, "creator-remix", "ok", "Rendered personalized semantic remix videos")
    append_log(
        manifest,
        "recipe.creator-remix",
        "Rendered creator remix videos",
        summary_first=relpath(summary_render, project_dir),
        chapterized=relpath(chapter_render, project_dir),
    )
    save_manifest(project_dir, manifest)
    return manifest


def run_chapter_card_narration(project_dir: Path, chapters: int = 4) -> dict[str, Any]:
    manifest = load_manifest(project_dir)
    source = _input_path(project_dir, manifest)
    plan = _ensure_semantic_plan(project_dir, chapters=chapters)
    log_file = project_dir / "logs" / "chapter-card-narration.log"
    size = ffprobe_video_size(source)
    cards_dir = project_dir / "assets" / "chapter_cards"
    render_dir = project_dir / "renders" / "chapter_card_narration"
    cards_dir.mkdir(parents=True, exist_ok=True)
    render_dir.mkdir(parents=True, exist_ok=True)
    default_duration = float(os.environ.get("LOGICCUT_NARRATION_CARD_DURATION", "7.5"))
    tts_engine = os.environ.get("LOGICCUT_NARRATION_TTS_ENGINE", "indextts2")
    tts_ports = os.environ.get("LOGICCUT_NARRATION_TTS_PORTS") or None
    voice = os.environ.get("LOGICCUT_NARRATION_VOICE", "logiccut-narrator")
    auto_ref = os.environ.get("LOGICCUT_NARRATION_AUTO_REF", "1").strip().lower() not in {"0", "false", "no"}
    template_sequence = _card_template_sequence()
    count = int(
        os.environ.get(
            "LOGICCUT_NARRATED_CARD_COUNT",
            os.environ.get("LOGICCUT_RENDER_HIGHLIGHT_COUNT", str(max(1, chapters))),
        )
    )
    source_items = _chapter_card_source_items(plan)[: max(1, count)]
    if not source_items:
        raise ValueError("chapter-card-narration requires semantic highlights or chapters")

    narrated_cards: list[Path] = []
    timeline_items: list[dict[str, Any]] = []
    for index, item in enumerate(source_items, start=1):
        card = build_highlight_card(item, index=index)
        narration_text = str(item.get("narration_text") or build_narration_text(card)).strip()
        audio_path = cards_dir / f"chapter_{index:02}_narration.wav"
        backend_options: dict[str, Any] = {"chapter_index": index}
        reference_audio: Path | None = None
        if auto_ref and not os.environ.get("LOGICCUT_NARRATION_REF_WAV"):
            reference_audio = prepare_narration_reference(
                source,
                cards_dir / f"chapter_{index:02}_ref.wav",
                start=card.start,
                end=card.end,
                log_file=log_file,
            )
            backend_options["ref_wav"] = str(reference_audio)
        tts_result = synthesize_narration_audio(
            narration_text,
            audio_path,
            engine=tts_engine,
            voice=voice,
            tts_ports=tts_ports,
            backend_options=backend_options,
            log_file=log_file,
        )
        duration = max(default_duration, safe_audio_duration(audio_path, fallback=default_duration) + 0.3)
        subtitle_path = cards_dir / f"chapter_{index:02}_narration.srt"
        write_narration_srt(subtitle_path, narration_text, duration=duration)
        html_path = cards_dir / f"chapter_{index:02}.html"
        image_path = cards_dir / f"chapter_{index:02}.png"
        silent_card = cards_dir / f"chapter_{index:02}_silent.mp4"
        narrated_card = cards_dir / f"chapter_{index:02}_narrated.mp4"
        template_id = _card_template_for_index(index, template_sequence)
        render_html_card_video(
            card=card,
            source_video=source,
            output_html=html_path,
            output_image=image_path,
            output_video=silent_card,
            duration=duration,
            size=size,
            template_id=template_id,
            log_file=log_file,
        )
        mix_card_with_narration(
            silent_card,
            audio_path,
            subtitle_path,
            narrated_card,
            log_file=log_file,
        )
        narrated_cards.append(narrated_card)
        track_id = f"chapter_narration_{index:02}"
        card_id = f"chapter_card_{index:02}"
        upsert_by_id(
            manifest["tracks"],
            {
                "id": track_id,
                "kind": "audio",
                "recipe": "chapter-card-narration",
                "adapter": f"tts:{tts_result.get('backend') or tts_engine}",
                "path": relpath(audio_path, project_dir),
                "subtitle": relpath(subtitle_path, project_dir),
                "text": narration_text,
                "voice": voice,
                "tts_engine": tts_result.get("engine") or tts_engine,
                "role": "chapter_card_narration",
                "reference_audio": relpath(reference_audio, project_dir) if reference_audio else None,
            },
        )
        upsert_by_id(
            manifest["clips"],
            {
                "id": card_id,
                "recipe": "chapter-card-narration",
                "adapter": "logiccut-html-card+tts+ffmpeg",
                "path": relpath(narrated_card, project_dir),
                "html": relpath(html_path, project_dir),
                "image": relpath(image_path, project_dir),
                "silent_card": relpath(silent_card, project_dir),
                "narration_track": track_id,
                "role": "narrated_chapter_card",
                "template_id": template_id,
                "title": card.title,
                "start": card.start,
                "end": card.end,
                "duration": duration,
            },
        )
        timeline_items.append(
            {
                "clip_id": card_id,
                "track_id": track_id,
                "role": "chapter_card_with_narration",
                "title": card.title,
                "narration_text": narration_text,
                "template_id": template_id,
            }
        )

    render_path = render_dir / "chapter_card_narration.mp4"
    concat_videos_reencode(narrated_cards, render_path, log_file=log_file)
    upsert_by_id(
        manifest["timeline"],
        {
            "id": "chapter_card_narration_timeline",
            "recipe": "chapter-card-narration",
            "items": timeline_items,
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": "chapter_card_narration",
            "recipe": "chapter-card-narration",
            "adapter": "logiccut-html-card+tts+ffmpeg",
            "path": relpath(render_path, project_dir),
            "analysis": "assets/semantic_analysis.json",
        },
    )
    _mark_recipe(manifest, "chapter-card-narration", "ok", "Rendered narrated chapter cards")
    append_log(
        manifest,
        "recipe.chapter-card-narration",
        "Rendered narrated chapter cards",
        output=relpath(render_path, project_dir),
        card_count=len(narrated_cards),
        tts_engine=tts_engine,
        voice=voice,
        templates=template_sequence,
    )
    save_manifest(project_dir, manifest)
    return manifest


def run_guided_highlights(project_dir: Path, chapters: int = 4) -> dict[str, Any]:
    manifest = load_manifest(project_dir)
    source = _input_path(project_dir, manifest)
    plan = _ensure_semantic_plan(project_dir, chapters=chapters)
    log_file = project_dir / "logs" / "guided-highlights.log"
    size = ffprobe_video_size(source)
    assets_dir = project_dir / "assets" / "guided_highlights"
    clips_dir = project_dir / "clips" / "guided_highlights"
    render_dir = project_dir / "renders" / "guided_highlights"
    assets_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)
    render_dir.mkdir(parents=True, exist_ok=True)

    default_card_duration = float(
        os.environ.get(
            "LOGICCUT_GUIDED_CARD_DURATION",
            os.environ.get("LOGICCUT_NARRATION_CARD_DURATION", "7.5"),
        )
    )
    count = int(
        os.environ.get(
            "LOGICCUT_GUIDED_HIGHLIGHT_COUNT",
            os.environ.get(
                "LOGICCUT_RENDER_HIGHLIGHT_COUNT",
                str(max(1, chapters)),
            ),
        )
    )
    tts_engine = os.environ.get("LOGICCUT_NARRATION_TTS_ENGINE", "indextts2")
    tts_ports = os.environ.get("LOGICCUT_NARRATION_TTS_PORTS") or None
    voice = os.environ.get("LOGICCUT_NARRATION_VOICE", "logiccut-narrator")
    auto_ref = os.environ.get("LOGICCUT_NARRATION_AUTO_REF", "1").strip().lower() not in {"0", "false", "no"}
    burn_highlight_subtitles = os.environ.get("LOGICCUT_GUIDED_BURN_SUBTITLES", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    template_sequence = _card_template_sequence()
    source_items = _chapter_card_source_items(plan)[: max(1, count)]
    if not source_items:
        raise ValueError("guided-highlights requires semantic highlights or chapters")

    final_inputs: list[Path] = []
    timeline_items: list[dict[str, Any]] = []
    translated_segments = plan.get("translated_segments", []) if isinstance(plan.get("translated_segments"), list) else []

    for index, item in enumerate(source_items, start=1):
        card = build_highlight_card(item, index=index)
        narration_text = normalize_display_text(item.get("narration_text") or build_narration_text(card))
        template_id = _card_template_for_index(index, template_sequence)
        card_id = f"guided_card_{index:02}"
        highlight_id = f"guided_highlight_{index:02}"
        track_id = f"guided_narration_{index:02}"

        narration_audio = assets_dir / f"{card_id}_narration.wav"
        reference_audio: Path | None = None
        backend_options: dict[str, Any] = {"chapter_index": index, "recipe": "guided-highlights"}
        if auto_ref and not os.environ.get("LOGICCUT_NARRATION_REF_WAV"):
            reference_audio = prepare_narration_reference(
                source,
                assets_dir / f"{card_id}_ref.wav",
                start=card.start,
                end=card.end,
                log_file=log_file,
            )
            backend_options["ref_wav"] = str(reference_audio)
        tts_result = synthesize_narration_audio(
            narration_text,
            narration_audio,
            engine=tts_engine,
            voice=voice,
            tts_ports=tts_ports,
            backend_options=backend_options,
            log_file=log_file,
        )
        card_duration = max(default_card_duration, safe_audio_duration(narration_audio, fallback=default_card_duration) + 0.3)
        narration_srt = assets_dir / f"{card_id}_narration.srt"
        write_narration_srt(narration_srt, narration_text, duration=card_duration)

        card_html = assets_dir / f"{card_id}.html"
        card_image = assets_dir / f"{card_id}.png"
        silent_card = assets_dir / f"{card_id}_silent.mp4"
        narrated_card = assets_dir / f"{card_id}_narrated.mp4"
        render_html_card_video(
            card=card,
            source_video=source,
            output_html=card_html,
            output_image=card_image,
            output_video=silent_card,
            duration=card_duration,
            size=size,
            template_id=template_id,
            log_file=log_file,
        )
        mix_card_with_narration(silent_card, narration_audio, narration_srt, narrated_card, log_file=log_file)

        raw_highlight = clips_dir / f"{highlight_id}_raw.mp4"
        highlight_duration = max(card.end - card.start, 0.1)
        render_clip(source, raw_highlight, card.start, highlight_duration, log_file=log_file)
        highlight_subtitle = assets_dir / f"{highlight_id}.srt"
        subtitle_segments = _subtitle_segments_for_range(translated_segments, card.start, card.end)
        write_srt(highlight_subtitle, subtitle_segments)
        final_highlight = clips_dir / f"{highlight_id}.mp4"
        if burn_highlight_subtitles and subtitle_segments:
            burn_subtitles(raw_highlight, highlight_subtitle, final_highlight, log_file=log_file)
        else:
            final_highlight.write_bytes(raw_highlight.read_bytes())

        final_inputs.extend([narrated_card, final_highlight])
        why_this_clip = card.reason
        upsert_by_id(
            manifest["tracks"],
            {
                "id": track_id,
                "kind": "audio",
                "recipe": "guided-highlights",
                "adapter": f"tts:{tts_result.get('backend') or tts_engine}",
                "path": relpath(narration_audio, project_dir),
                "subtitle": relpath(narration_srt, project_dir),
                "text": narration_text,
                "voice": voice,
                "tts_engine": tts_result.get("engine") or tts_engine,
                "role": "chapter_card_narration",
                "reference_audio": relpath(reference_audio, project_dir) if reference_audio else None,
            },
        )
        upsert_by_id(
            manifest["clips"],
            {
                "id": card_id,
                "recipe": "guided-highlights",
                "adapter": "logiccut-html-card+tts+ffmpeg",
                "path": relpath(narrated_card, project_dir),
                "html": relpath(card_html, project_dir),
                "image": relpath(card_image, project_dir),
                "silent_card": relpath(silent_card, project_dir),
                "narration_track": track_id,
                "role": "guided_chapter_card",
                "template_id": template_id,
                "title": card.title,
                "start": card.start,
                "end": card.end,
                "duration": card_duration,
                "why_this_clip": why_this_clip,
                "narration_text": narration_text,
            },
        )
        upsert_by_id(
            manifest["clips"],
            {
                "id": highlight_id,
                "recipe": "guided-highlights",
                "adapter": "logiccut-ffmpeg+subtitles" if burn_highlight_subtitles else "logiccut-ffmpeg",
                "path": relpath(final_highlight, project_dir),
                "raw_clip": relpath(raw_highlight, project_dir),
                "subtitle": relpath(highlight_subtitle, project_dir),
                "role": "guided_highlight_clip",
                "title": card.title,
                "start": card.start,
                "end": card.end,
                "duration": highlight_duration,
                "score": card.score,
                "why_this_clip": why_this_clip,
                "subtitle_mode": "burned" if burn_highlight_subtitles and subtitle_segments else "sidecar",
            },
        )
        timeline_items.extend(
            [
                {
                    "clip_id": card_id,
                    "track_id": track_id,
                    "role": "guided_card",
                    "title": card.title,
                    "template_id": template_id,
                    "narration_text": narration_text,
                    "why_this_clip": why_this_clip,
                },
                {
                    "clip_id": highlight_id,
                    "role": "guided_highlight",
                    "title": card.title,
                    "subtitle": relpath(highlight_subtitle, project_dir),
                    "why_this_clip": why_this_clip,
                },
            ]
        )

    render_path = render_dir / "guided_highlights.mp4"
    concat_videos_reencode(final_inputs, render_path, log_file=log_file)
    upsert_by_id(
        manifest["timeline"],
        {
            "id": "guided_highlights_timeline",
            "recipe": "guided-highlights",
            "items": timeline_items,
            "mode": "card_narration_then_highlight",
            "subtitle_mode": "burned" if burn_highlight_subtitles else "sidecar",
            "templates": template_sequence,
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": "guided_highlights",
            "recipe": "guided-highlights",
            "adapter": "logiccut-html-card+tts+ffmpeg",
            "path": relpath(render_path, project_dir),
            "analysis": "assets/semantic_analysis.json",
            "timeline": "guided_highlights_timeline",
        },
    )
    _mark_recipe(manifest, "guided-highlights", "ok", "Rendered guided highlight video")
    append_log(
        manifest,
        "recipe.guided-highlights",
        "Rendered guided highlight video",
        output=relpath(render_path, project_dir),
        highlight_count=len(source_items),
        tts_engine=tts_engine,
        voice=voice,
        templates=template_sequence,
    )
    save_manifest(project_dir, manifest)
    return manifest


def run_story_guided_highlights(project_dir: Path, chapters: int = 6) -> dict[str, Any]:
    manifest = load_manifest(project_dir)
    source = _input_path(project_dir, manifest)
    duration = ffprobe_duration(source)
    semantic_plan = _ensure_semantic_plan(project_dir, chapters=chapters)
    story_plan = _story_plan_input(project_dir, semantic_plan)
    item_count = int(os.environ.get("LOGICCUT_STORY_ITEM_COUNT", str(max(1, chapters))))
    style_id = os.environ.get("LOGICCUT_STORY_STYLE", "story_news")
    timeline = build_story_timeline_from_semantic_plan(
        story_plan,
        duration=duration,
        style_id=style_id,
        item_count=item_count,
        narration_duration=float(os.environ.get("LOGICCUT_STORY_NARRATION_DURATION", "3.2")),
        original_duration=float(os.environ.get("LOGICCUT_STORY_ORIGINAL_DURATION", "4.0")),
    )
    log_file = project_dir / "logs" / "story-guided-highlights.log"
    translated_segments = _story_translated_segments(semantic_plan)
    render = render_story_timeline(
        project_dir,
        source=source,
        timeline=timeline,
        translated_segments=translated_segments,
        tts_engine=os.environ.get("LOGICCUT_STORY_TTS_ENGINE") or os.environ.get("LOGICCUT_NARRATION_TTS_ENGINE"),
        tts_ports=os.environ.get("LOGICCUT_STORY_TTS_PORTS") or os.environ.get("LOGICCUT_NARRATION_TTS_PORTS"),
        voice=os.environ.get("LOGICCUT_STORY_NARRATION_VOICE") or os.environ.get("LOGICCUT_NARRATION_VOICE"),
        log_file=log_file,
    )

    timeline_items: list[dict[str, Any]] = []
    for index, part in enumerate(render["parts"], start=1):
        clip_id = f"story_guided_part_{index:02}"
        track_id = f"story_guided_narration_{index:02}" if part["type"] == "narration" else None
        upsert_by_id(
            manifest["clips"],
            {
                "id": clip_id,
                "recipe": "story-guided-highlights",
                "adapter": part["adapter"],
                "path": relpath(part["path"], project_dir),
                "raw_clip": relpath(part["raw_clip"], project_dir),
                "subtitle": relpath(part["subtitle"], project_dir),
                "role": f"story_{part['type']}",
                "OST": part["OST"],
                "start": part["start"],
                "end": part["end"],
                "duration": part["duration"],
                "title": part["title"],
                "narration_text": part["narration"],
                "why_this_clip": part["why"],
            },
        )
        if track_id:
            upsert_by_id(
                manifest["tracks"],
                {
                    "id": track_id,
                    "kind": "audio",
                    "recipe": "story-guided-highlights",
                    "adapter": "tts",
                    "path": relpath((project_dir / "assets" / "story_guided_highlights" / f"{index:02}_narration.wav"), project_dir),
                    "subtitle": relpath(part["subtitle"], project_dir),
                    "text": part["narration"],
                    "voice": os.environ.get("LOGICCUT_STORY_NARRATION_VOICE") or os.environ.get("LOGICCUT_NARRATION_VOICE") or "logiccut-story-narrator",
                },
            )
        timeline_items.append(
            {
                "clip_id": clip_id,
                "track_id": track_id,
                "role": f"story_{part['type']}",
                "OST": part["OST"],
                "title": part["title"],
                "why_this_clip": part["why"],
            }
        )

    upsert_by_id(
        manifest["timeline"],
        {
            "id": "story_guided_highlights_timeline",
            "recipe": "story-guided-highlights",
            "mode": "narration_broll_then_original_evidence",
            "style_id": timeline.get("style_id"),
            "story_arc": timeline.get("story_arc"),
            "items": timeline_items,
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": "story_guided_highlights",
            "recipe": "story-guided-highlights",
            "adapter": "logiccut-story-planner+ffmpeg+tts",
            "path": relpath(render["output"], project_dir),
            "report": relpath(render["report_html"], project_dir),
            "report_json": relpath(render["report_json"], project_dir),
            "timeline": "story_guided_highlights_timeline",
        },
    )
    _mark_recipe(manifest, "story-guided-highlights", "ok", "Rendered story-guided highlight remix")
    append_log(
        manifest,
        "recipe.story-guided-highlights",
        "Rendered story-guided highlight remix",
        output=relpath(render["output"], project_dir),
        report=relpath(render["report_html"], project_dir),
        style_id=timeline.get("style_id"),
        item_count=len(timeline_items),
    )
    save_manifest(project_dir, manifest)
    return manifest


def run_theme_opener(project_dir: Path) -> dict[str, Any]:
    manifest = load_manifest(project_dir)
    source = _input_path(project_dir, manifest)
    assets_dir = project_dir / "assets" / "theme_opener"
    clips_dir = project_dir / "clips" / "theme_opener"
    render_dir = project_dir / "renders" / "theme_opener"
    log_file = project_dir / "logs" / "theme-opener.log"
    plan_path = assets_dir / "theme_opener_plan.json"
    prompt_path = assets_dir / "codex_prompt.md"
    assets_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)
    render_dir.mkdir(parents=True, exist_ok=True)

    if not plan_path.exists():
        transcript = _ensure_source_transcript(project_dir, source)
        write_theme_opener_codex_prompt(
            prompt_path,
            transcript,
            source_name=source.name,
            theme=os.environ.get("LOGICCUT_THEME_OPENER_THEME") or None,
            target_seconds=int(os.environ.get("LOGICCUT_THEME_OPENER_TARGET_SECONDS", "20")),
        )
        _mark_recipe(
            manifest,
            "theme-opener",
            "needs_codex_plan",
            "Codex prompt generated; write assets/theme_opener/theme_opener_plan.json to render.",
        )
        append_log(
            manifest,
            "recipe.theme-opener",
            "Generated Codex prompt for theme opener",
            prompt=relpath(prompt_path, project_dir),
            plan=relpath(plan_path, project_dir),
        )
        save_manifest(project_dir, manifest)
        return manifest

    duration = ffprobe_duration(source)
    transcript = _ensure_source_transcript(project_dir, source)
    plan = load_theme_opener_plan(plan_path, source_duration=duration, transcript=transcript)
    final_inputs: list[Path] = []
    timeline_items: list[dict[str, Any]] = []

    for index, clip in enumerate(plan["clips"], start=1):
        clip_id = f"theme_opener_clip_{index:02}"
        raw_clip = clips_dir / f"{clip_id}_raw.mp4"
        subtitled_clip = clips_dir / f"{clip_id}_subtitled.mp4"
        final_clip = clips_dir / f"{clip_id}.mp4"
        subtitle_path = assets_dir / f"{clip_id}.srt"
        write_srt(
            subtitle_path,
            [{"start": 0.0, "end": float(clip["duration"]), "text": clip["subtitle"]}],
        )
        render_clip(source, raw_clip, float(clip["start"]), float(clip["duration"]), log_file=log_file, accurate=True)
        burn_subtitles(raw_clip, subtitle_path, subtitled_clip, log_file=log_file)
        render_text_watermark(subtitled_clip, final_clip, plan["watermark"], log_file=log_file)
        final_inputs.append(final_clip)
        timeline_items.append({"clip_id": clip_id, "role": "theme_evidence", "visual_role": clip["visual_role"]})
        upsert_by_id(
            manifest["clips"],
            {
                "id": clip_id,
                "recipe": "theme-opener",
                "adapter": "logiccut-ffmpeg+ass-subtitles+watermark",
                "path": relpath(final_clip, project_dir),
                "raw_clip": relpath(raw_clip, project_dir),
                "subtitled_clip": relpath(subtitled_clip, project_dir),
                "subtitle": relpath(subtitle_path, project_dir),
                "start": clip["start"],
                "end": clip["end"],
                "duration": clip["duration"],
                "theme": plan["theme"],
                "title": clip["visual_role"],
                "subtitle_text": clip["subtitle"],
                "why_this_clip": clip["reason"],
                "visual_role": clip["visual_role"],
            },
        )

    render_path = render_dir / "theme_opener.mp4"
    concat_videos_reencode(final_inputs, render_path, log_file=log_file)
    report_json = assets_dir / "theme_opener_report.json"
    report_html = assets_dir / "theme_opener_report.html"
    report_payload = {
        "theme": plan["theme"],
        "opening_hook": plan["opening_hook"],
        "watermark": plan["watermark"],
        "total_duration": plan["total_duration"],
        "source": relpath(source, project_dir),
        "output": relpath(render_path, project_dir),
        "report_video_path": os.path.relpath(render_path, report_html.parent).replace(os.sep, "/"),
        "clips": plan["clips"],
    }
    write_json(report_json, report_payload)
    report_html.write_text(_theme_opener_report_html(report_payload), encoding="utf-8")

    upsert_by_id(
        manifest["timeline"],
        {
            "id": "theme_opener_timeline",
            "recipe": "theme-opener",
            "mode": "theme_evidence_opener",
            "theme": plan["theme"],
            "items": timeline_items,
        },
    )
    upsert_by_id(
        manifest["renders"],
        {
            "id": "theme_opener",
            "recipe": "theme-opener",
            "adapter": "logiccut-theme-opener+ffmpeg",
            "path": relpath(render_path, project_dir),
            "report": relpath(report_html, project_dir),
            "report_json": relpath(report_json, project_dir),
            "plan": relpath(plan_path, project_dir),
            "theme": plan["theme"],
            "opening_hook": plan["opening_hook"],
            "duration": plan["total_duration"],
        },
    )
    _mark_recipe(manifest, "theme-opener", "ok", "Rendered Codex-assisted theme opener")
    append_log(
        manifest,
        "recipe.theme-opener",
        "Rendered theme opener",
        output=relpath(render_path, project_dir),
        report=relpath(report_html, project_dir),
        theme=plan["theme"],
    )
    save_manifest(project_dir, manifest)
    return manifest


def run_personalized_highlights(project_dir: Path, chapters: int = 4) -> dict[str, Any]:
    manifest = load_manifest(project_dir)
    source = _input_path(project_dir, manifest)
    plan = _ensure_semantic_plan(project_dir, chapters=chapters)
    styles = parse_style_ids(os.environ.get("LOGICCUT_PERSONALIZED_STYLES"))
    layouts = parse_layouts(os.environ.get("LOGICCUT_PERSONALIZED_LAYOUTS"))
    catchphrases = parse_catchphrases(os.environ.get("LOGICCUT_CREATOR_CATCHPHRASES"))
    count = int(os.environ.get("LOGICCUT_PERSONALIZED_HIGHLIGHT_COUNT", str(max(1, chapters))))
    tts_engine = os.environ.get("LOGICCUT_NARRATION_TTS_ENGINE", "indextts2")
    tts_ports = os.environ.get("LOGICCUT_NARRATION_TTS_PORTS") or None
    voice = os.environ.get("LOGICCUT_NARRATION_VOICE", "logiccut-creator")
    creator_ref_wav = os.environ.get("LOGICCUT_CREATOR_REF_WAV", "").strip()
    creator_ref_text = os.environ.get("LOGICCUT_CREATOR_REF_TEXT", "").strip()
    default_card_duration = float(os.environ.get("LOGICCUT_PERSONALIZED_CARD_DURATION", os.environ.get("LOGICCUT_GUIDED_CARD_DURATION", "7.5")))
    burn_highlight_subtitles = os.environ.get("LOGICCUT_GUIDED_BURN_SUBTITLES", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    source_items = _chapter_card_source_items(plan)[: max(1, count)]
    if not source_items:
        raise ValueError("personalized-highlights requires semantic highlights or chapters")
    translated_segments = plan.get("translated_segments", []) if isinstance(plan.get("translated_segments"), list) else []
    log_file = project_dir / "logs" / "personalized-highlights.log"
    size = ffprobe_video_size(source)
    report_entries: list[dict[str, Any]] = []
    render_summaries: list[dict[str, Any]] = []

    for style_id in styles:
        style = get_creator_style(style_id)
        for layout in layouts:
            result = _render_personalized_variant(
                project_dir,
                manifest,
                source=source,
                source_items=source_items,
                translated_segments=translated_segments,
                source_size=size,
                style=style,
                layout=layout,
                catchphrases=catchphrases,
                creator_ref_wav=creator_ref_wav,
                creator_ref_text=creator_ref_text,
                tts_engine=tts_engine,
                tts_ports=tts_ports,
                voice=voice,
                default_card_duration=default_card_duration,
                burn_highlight_subtitles=burn_highlight_subtitles,
                log_file=log_file,
            )
            report_entries.extend(result["report_entries"])
            render_summaries.append(result["render"])

    report_json = project_dir / "assets" / "personalized_highlights" / "personalized_report.json"
    report_html = project_dir / "assets" / "personalized_highlights" / "personalized_report.html"
    portable_render_summaries = _make_personalized_report_portable(project_dir, render_summaries)
    report_payload = {
        "styles": list(styles),
        "layouts": list(layouts),
        "catchphrases": list(catchphrases),
        "creator_ref_wav": creator_ref_wav or None,
        "creator_ref_text": creator_ref_text or None,
        "renders": portable_render_summaries,
        "chapters": report_entries,
    }
    write_json(report_json, report_payload)
    report_html.write_text(_personalized_report_html(report_payload), encoding="utf-8")
    upsert_by_id(
        manifest["renders"],
        {
            "id": "personalized_highlights_report",
            "recipe": "personalized-highlights",
            "adapter": "logiccut-report",
            "path": relpath(report_html, project_dir),
            "json": relpath(report_json, project_dir),
        },
    )
    _mark_recipe(manifest, "personalized-highlights", "ok", "Rendered personalized creator voice highlight variants")
    append_log(
        manifest,
        "recipe.personalized-highlights",
        "Rendered personalized highlight variants",
        styles=list(styles),
        layouts=list(layouts),
        report=relpath(report_html, project_dir),
    )
    save_manifest(project_dir, manifest)
    return manifest


def _render_personalized_variant(
    project_dir: Path,
    manifest: dict[str, Any],
    *,
    source: Path,
    source_items: list[dict[str, Any]],
    translated_segments: list[dict[str, Any]],
    source_size: tuple[int, int],
    style: Any,
    layout: str,
    catchphrases: tuple[str, ...],
    creator_ref_wav: str,
    creator_ref_text: str,
    tts_engine: str,
    tts_ports: str | None,
    voice: str,
    default_card_duration: float,
    burn_highlight_subtitles: bool,
    log_file: Path,
) -> dict[str, Any]:
    namespace = f"{style.id}_{layout}"
    assets_dir = project_dir / "assets" / "personalized_highlights" / namespace
    clips_dir = project_dir / "clips" / "personalized_highlights" / namespace
    render_dir = project_dir / "renders" / "personalized_highlights"
    assets_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)
    render_dir.mkdir(parents=True, exist_ok=True)
    card_size = (1080, 1920) if layout == "portrait" else source_size
    template_sequence = list(style.template_sequence)
    final_inputs: list[Path] = []
    timeline_items: list[dict[str, Any]] = []
    report_entries: list[dict[str, Any]] = []

    for index, item in enumerate(source_items, start=1):
        card = build_highlight_card(item, index=index)
        template_id = _card_template_for_index(index, template_sequence)
        narration_text = str(item.get("narration_text") or build_personalized_narration(card, style, catchphrases=catchphrases)).strip()
        card_id = f"personalized_{style.id}_{layout}_card_{index:02}"
        highlight_id = f"personalized_{style.id}_{layout}_highlight_{index:02}"
        track_id = f"personalized_{style.id}_{layout}_narration_{index:02}"
        narration_audio = assets_dir / f"{card_id}_narration.wav"
        reference_audio: Path | None = None
        backend_options: dict[str, Any] = {
            "chapter_index": index,
            "recipe": "personalized-highlights",
            "creator_style": style.id,
            "catchphrases": list(catchphrases),
        }
        if creator_ref_wav:
            backend_options["ref_wav"] = creator_ref_wav
            reference_audio = Path(creator_ref_wav)
        elif os.environ.get("LOGICCUT_NARRATION_AUTO_REF", "1").strip().lower() not in {"0", "false", "no"}:
            reference_audio = prepare_narration_reference(
                source,
                assets_dir / f"{card_id}_ref.wav",
                start=card.start,
                end=card.end,
                log_file=log_file,
            )
            backend_options["ref_wav"] = str(reference_audio)
        if creator_ref_text:
            backend_options["ref_text"] = creator_ref_text
        tts_result = synthesize_narration_audio(
            narration_text,
            narration_audio,
            engine=tts_engine,
            voice=voice,
            tts_ports=tts_ports,
            backend_options=backend_options,
            log_file=log_file,
        )
        card_duration = max(default_card_duration, safe_audio_duration(narration_audio, fallback=default_card_duration) + 0.3)
        narration_srt = assets_dir / f"{card_id}_narration.srt"
        write_narration_srt(narration_srt, narration_text, duration=card_duration)
        card_html = assets_dir / f"{card_id}.html"
        card_image = assets_dir / f"{card_id}.png"
        silent_card = assets_dir / f"{card_id}_silent.mp4"
        narrated_card = assets_dir / f"{card_id}_narrated.mp4"
        render_html_card_video(
            card=card,
            source_video=source,
            output_html=card_html,
            output_image=card_image,
            output_video=silent_card,
            duration=card_duration,
            size=card_size,
            template_id=template_id,
            log_file=log_file,
        )
        mix_card_with_narration(silent_card, narration_audio, narration_srt, narrated_card, log_file=log_file)

        raw_highlight = clips_dir / f"{highlight_id}_raw.mp4"
        render_clip(source, raw_highlight, card.start, max(card.end - card.start, 0.1), log_file=log_file)
        highlight_subtitle = assets_dir / f"{highlight_id}.srt"
        subtitle_segments = _subtitle_segments_for_range(translated_segments, card.start, card.end)
        write_srt(highlight_subtitle, subtitle_segments)
        subtitled_highlight = clips_dir / f"{highlight_id}_subtitled.mp4"
        if burn_highlight_subtitles and subtitle_segments:
            style_size = (1080, 608) if layout == "portrait" else None
            burn_subtitles(
                raw_highlight,
                highlight_subtitle,
                subtitled_highlight,
                log_file=log_file,
                style_size=style_size,
            )
        else:
            subtitled_highlight.write_bytes(raw_highlight.read_bytes())
        final_highlight = subtitled_highlight
        portrait_html: Path | None = None
        portrait_image: Path | None = None
        if layout == "portrait":
            portrait_html = assets_dir / f"{highlight_id}_portrait_shell.html"
            portrait_image = assets_dir / f"{highlight_id}_portrait_shell.png"
            final_highlight = clips_dir / f"{highlight_id}_portrait.mp4"
            render_portrait_web_video(
                source_video=subtitled_highlight,
                output_html=portrait_html,
                output_image=portrait_image,
                output_video=final_highlight,
                title=card.title,
                hook=card.hook,
                reason=card.reason,
                style_name=style.name,
                style_tone=style.tone,
                log_file=log_file,
            )

        final_inputs.extend([narrated_card, final_highlight])
        explanation = build_cut_explanation(
            card,
            style,
            narration_text=narration_text,
            layout=layout,
            template_id=template_id,
            reference_audio=str(reference_audio) if reference_audio else None,
            catchphrases=catchphrases,
        )
        report_entries.append(explanation)
        upsert_by_id(
            manifest["tracks"],
            {
                "id": track_id,
                "kind": "audio",
                "recipe": "personalized-highlights",
                "adapter": f"tts:{tts_result.get('backend') or tts_engine}",
                "path": relpath(narration_audio, project_dir),
                "subtitle": relpath(narration_srt, project_dir),
                "text": narration_text,
                "voice": voice,
                "tts_engine": tts_result.get("engine") or tts_engine,
                "creator_style": style.id,
                "catchphrases": list(catchphrases),
                "reference_audio": relpath(reference_audio, project_dir) if reference_audio and reference_audio.exists() else str(reference_audio) if reference_audio else None,
            },
        )
        upsert_by_id(
            manifest["clips"],
            {
                "id": card_id,
                "recipe": "personalized-highlights",
                "adapter": "logiccut-html-card+tts+ffmpeg",
                "path": relpath(narrated_card, project_dir),
                "html": relpath(card_html, project_dir),
                "image": relpath(card_image, project_dir),
                "role": "personalized_chapter_card",
                "template_id": template_id,
                "creator_style": style.id,
                "layout": layout,
                "title": card.title,
                "narration_track": track_id,
                "narration_text": narration_text,
                "why_this_clip": card.reason,
            },
        )
        upsert_by_id(
            manifest["clips"],
            {
                "id": highlight_id,
                "recipe": "personalized-highlights",
                "adapter": "logiccut-ffmpeg+subtitles+portrait-shell" if layout == "portrait" else "logiccut-ffmpeg+subtitles",
                "path": relpath(final_highlight, project_dir),
                "raw_clip": relpath(raw_highlight, project_dir),
                "subtitle": relpath(highlight_subtitle, project_dir),
                "portrait_html": relpath(portrait_html, project_dir) if portrait_html else None,
                "portrait_image": relpath(portrait_image, project_dir) if portrait_image else None,
                "role": "personalized_highlight_clip",
                "template_id": template_id,
                "creator_style": style.id,
                "layout": layout,
                "title": card.title,
                "start": card.start,
                "end": card.end,
                "why_this_clip": card.reason,
            },
        )
        timeline_items.extend(
            [
                {"clip_id": card_id, "track_id": track_id, "role": "personalized_card", "style": style.id, "layout": layout},
                {"clip_id": highlight_id, "role": "personalized_highlight", "style": style.id, "layout": layout},
            ]
        )

    render_path = render_dir / f"personalized_{style.id}_{layout}.mp4"
    concat_videos_reencode(final_inputs, render_path, log_file=log_file)
    render_item = {
        "id": f"personalized_{style.id}_{layout}",
        "recipe": "personalized-highlights",
        "adapter": "logiccut-html-card+tts+ffmpeg",
        "path": relpath(render_path, project_dir),
        "style_id": style.id,
        "style_name": style.name,
        "layout": layout,
        "timeline": f"personalized_{style.id}_{layout}_timeline",
    }
    upsert_by_id(manifest["renders"], render_item)
    upsert_by_id(
        manifest["timeline"],
        {
            "id": f"personalized_{style.id}_{layout}_timeline",
            "recipe": "personalized-highlights",
            "items": timeline_items,
            "mode": "personalized_card_then_highlight",
            "style_id": style.id,
            "layout": layout,
            "catchphrases": list(catchphrases),
            "templates": template_sequence,
        },
    )
    return {"render": render_item, "report_entries": report_entries}


def _make_personalized_report_portable(project_dir: Path, renders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    video_dir = project_dir / "assets" / "personalized_highlights" / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    portable: list[dict[str, Any]] = []
    for item in renders:
        cloned = dict(item)
        render_rel = str(item.get("path") or "")
        if render_rel:
            source = (project_dir / render_rel).resolve()
            target = video_dir / Path(render_rel).name
            if source.exists():
                shutil.copy2(source, target)
                cloned["report_video_path"] = f"videos/{target.name}"
        portable.append(cloned)
    return portable


def _theme_opener_report_html(report: dict[str, Any]) -> str:
    clips = "".join(
        f"""
        <article class="clip">
          <strong>{index}. {html_lib.escape(str(clip.get("visual_role") or "主题证据"))}</strong>
          <span>{float(clip.get("start", 0.0)):.1f}s - {float(clip.get("end", 0.0)):.1f}s</span>
          <p>{html_lib.escape(str(clip.get("subtitle") or ""))}</p>
          <em>{html_lib.escape(str(clip.get("reason") or ""))}</em>
        </article>
        """
        for index, clip in enumerate(report.get("clips", []), start=1)
    )
    video_src = html_lib.escape(str(report.get("report_video_path") or report.get("output") or ""))
    theme = html_lib.escape(str(report.get("theme") or "主题开头"))
    hook = html_lib.escape(str(report.get("opening_hook") or ""))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LogicCut Theme Opener - {theme}</title>
  <style>
    :root {{ color-scheme: dark; --bg:#080b12; --panel:#121a27; --line:rgba(120,220,255,.24); --text:#f8fbff; --muted:#a8b6c8; --cyan:#32e6ff; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:linear-gradient(180deg,#05070d,#101724); color:var(--text); font-family:"PingFang SC","Microsoft YaHei",Arial,sans-serif; }}
    main {{ width:min(1120px, calc(100% - 36px)); margin:0 auto; padding:38px 0 70px; }}
    header {{ min-height:300px; display:grid; align-content:center; border-bottom:1px solid var(--line); }}
    .eyebrow {{ color:var(--cyan); font-weight:850; letter-spacing:0; }}
    h1 {{ margin:10px 0; font-size:clamp(42px,6vw,76px); line-height:1.02; letter-spacing:0; }}
    .hook {{ max-width:820px; color:var(--muted); font-size:20px; line-height:1.65; }}
    .grid {{ display:grid; grid-template-columns:minmax(0,1.1fr) minmax(320px,.9fr); gap:22px; margin-top:30px; }}
    video {{ width:100%; background:#000; border:1px solid var(--line); }}
    .panel, .clip {{ border:1px solid var(--line); background:rgba(18,26,39,.86); border-radius:8px; }}
    .panel {{ padding:18px; }}
    .clip {{ padding:14px; margin-bottom:12px; }}
    .clip strong {{ display:block; color:var(--cyan); font-size:17px; }}
    .clip span {{ display:block; margin-top:4px; color:var(--muted); font-size:13px; }}
    .clip p {{ margin:10px 0 6px; font-size:18px; line-height:1.45; }}
    .clip em {{ color:var(--muted); font-style:normal; line-height:1.55; }}
    @media (max-width:900px) {{ .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="eyebrow">LogicCut V0.2 Theme Opener</div>
      <h1>{theme}</h1>
      <p class="hook">{hook}</p>
    </header>
    <section class="grid">
      <div><video controls preload="metadata" src="{video_src}"></video></div>
      <div class="panel">{clips}</div>
    </section>
  </main>
</body>
</html>
"""


def _personalized_report_html(report: dict[str, Any]) -> str:
    renders = "\n".join(
        f"""<article class="render"><span>{html_lib.escape(item.get("style_name", ""))} · {html_lib.escape(item.get("layout", ""))}</span><video controls src="{html_lib.escape(item.get("report_video_path") or item.get("path", ""))}"></video></article>"""
        for item in report.get("renders", [])
    )
    chapters = "\n".join(_personalized_report_chapter(item) for item in report.get("chapters", []))
    catchphrases = "、".join(str(item) for item in report.get("catchphrases", [])) or "未设置"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LogicCut v0.3 个性化创作者口吻报告</title>
  <style>
    :root {{ --ink:#17212b; --muted:#607283; --line:#d8e1e9; --paper:#fff; --soft:#f4f7fa; --blue:#1f64b5; --teal:#0d7a7d; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--soft); color:var(--ink); font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","Microsoft YaHei",sans-serif; line-height:1.62; }}
    main {{ width:min(1220px,calc(100% - 40px)); margin:0 auto; padding:36px 0 74px; }}
    h1 {{ margin:14px 0; font-size:clamp(40px,5vw,70px); line-height:1.04; letter-spacing:0; }}
    h2 {{ margin:0 0 16px; font-size:clamp(26px,3vw,38px); line-height:1.12; letter-spacing:0; }}
    p {{ margin:0; color:var(--muted); }}
    .eyebrow {{ display:inline-flex; min-height:32px; align-items:center; padding:5px 12px; border:1px solid var(--line); border-radius:999px; background:var(--paper); color:var(--teal); font-size:13px; font-weight:850; }}
    section {{ margin-top:48px; }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }}
    .render,.chapter {{ border:1px solid var(--line); border-radius:8px; background:var(--paper); padding:16px; }}
    .render span,.badge {{ display:inline-flex; width:fit-content; min-height:28px; align-items:center; padding:4px 9px; border-radius:999px; background:#edf6f6; color:var(--teal); font-size:12px; font-weight:850; }}
    video {{ display:block; width:100%; margin-top:12px; border-radius:8px; background:#111b24; }}
    .chapter {{ display:grid; gap:8px; margin-bottom:12px; }}
    .chapter h3 {{ margin:0; font-size:20px; }}
    .meta {{ color:var(--muted); font-size:14px; }}
    @media (max-width: 860px) {{ .grid {{ grid-template-columns:1fr; }} main {{ width:min(100% - 28px,1220px); }} }}
  </style>
</head>
<body>
  <main>
    <span class="eyebrow">LogicCut v0.3 personalized creator voice</span>
    <h1>个性化创作者口吻导出报告</h1>
    <p>本次导出风格：{html_lib.escape(", ".join(report.get("styles", [])))}。布局：{html_lib.escape(", ".join(report.get("layouts", [])))}。常用口头禅：{html_lib.escape(catchphrases)}。参考音色：{html_lib.escape(str(report.get("creator_ref_wav") or "自动从原视频裁剪"))}。</p>
    <section>
      <h2>导出视频</h2>
      <div class="grid">{renders}</div>
    </section>
    <section>
      <h2>每章为什么这样剪</h2>
      {chapters}
    </section>
  </main>
</body>
</html>
"""


def _personalized_report_chapter(item: dict[str, Any]) -> str:
    return f"""<article class="chapter">
      <span class="badge">{html_lib.escape(str(item.get("style_name", "")))} · {html_lib.escape(str(item.get("layout", "")))}</span>
      <h3>{html_lib.escape(str(item.get("title", "")))}</h3>
      <div class="meta">{float(item.get("start", 0.0)):.1f}s - {float(item.get("end", 0.0)):.1f}s · score {html_lib.escape(str(item.get("score", "--")))}</div>
      <p><b>剪辑理由：</b>{html_lib.escape(str(item.get("why_this_clip", "")))}</p>
      <p><b>口吻策略：</b>{html_lib.escape(str(item.get("cut_strategy", "")))}</p>
      <p><b>旁白：</b>{html_lib.escape(str(item.get("narration_text", "")))}</p>
    </article>"""


def _input_path(project_dir: Path, manifest: dict[str, Any]) -> Path:
    return (project_dir / manifest["input"]["path"]).resolve()


def _render_path_by_id(project_dir: Path, manifest: dict[str, Any], render_id: str, *, fallback: Path) -> Path:
    for render in manifest.get("renders", []):
        if render.get("id") == render_id and render.get("path"):
            return (project_dir / str(render["path"])).resolve()
    return fallback


def _mark_recipe(manifest: dict[str, Any], recipe_id: str, status: str, message: str) -> None:
    upsert_by_id(
        manifest["recipes"],
        {
            "id": recipe_id,
            "status": status,
            "message": message,
        },
    )


def _ensure_semantic_plan(project_dir: Path, *, chapters: int = 4) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    manifest = load_manifest(project_dir)
    source = _input_path(project_dir, manifest)
    assets_dir = project_dir / "assets"
    analysis_path = assets_dir / "semantic_analysis.json"
    transcript_path = assets_dir / "source_transcript.json"
    raw_path = assets_dir / "gemini_semantic_response.raw.txt"
    prompt_path = assets_dir / "gemini_semantic_prompt.txt"
    translation_chunks_path = assets_dir / "gemini_translation_chunks.jsonl"
    translated_segments_path = assets_dir / "translated_segments.json"
    diagnostics_path = assets_dir / "semantic_diagnostics.json"
    refresh = str(os.environ.get("LOGICCUT_SEMANTIC_REFRESH", "")).lower() in {"1", "true", "yes"}
    should_refresh = refresh and project_dir not in _SEMANTIC_REFRESHED_PROJECTS

    if analysis_path.exists() and transcript_path.exists() and not should_refresh:
        with analysis_path.open("r", encoding="utf-8") as handle:
            plan = json_load_with_preview(handle)
        write_json(analysis_path, plan)
        return plan

    diagnostics: dict[str, Any] = {
        "source": str(source),
        "stages": {},
    }
    transcript = transcribe_media(source, language=os.environ.get("LOGICCUT_SOURCE_LANGUAGE") or None)
    write_json(transcript_path, transcript)
    diagnostics["stages"]["transcribe"] = {
        "status": "ok",
        "adapter": "faster-whisper",
        "model": os.environ.get("LOCAL_WHISPER_MODEL"),
        "device": os.environ.get("LOCAL_WHISPER_DEVICE", "cpu"),
        "segment_count": len(transcript.get("segments", [])),
        "duration": transcript.get("duration"),
        "output": relpath(transcript_path, project_dir),
    }

    def capturing_llm(prompt: str) -> str:
        prompt_path.write_text(prompt, encoding="utf-8")
        raw = call_vertex_gemini(prompt)
        raw_path.write_text(raw, encoding="utf-8")
        return raw

    plan = build_semantic_creation_plan(
        transcript,
        llm_fn=capturing_llm,
        backend_name="vertex-gemini",
        target_language=os.environ.get("LOGICCUT_TARGET_LANGUAGE", "English"),
        highlight_count=int(os.environ.get("LOGICCUT_HIGHLIGHT_COUNT", "3")),
        chapter_count=chapters,
    )

    translation_calls = 0

    def capturing_translation_llm(prompt: str) -> str:
        nonlocal translation_calls
        translation_calls += 1
        raw = call_vertex_gemini(prompt)
        with translation_chunks_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "chunk": translation_calls,
                        "prompt_chars": len(prompt),
                        "response": raw,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        return raw

    if translation_chunks_path.exists():
        translation_chunks_path.unlink()
    translated_segments = translate_transcript_segments(
        transcript,
        llm_fn=capturing_translation_llm,
        target_language=os.environ.get("LOGICCUT_TARGET_LANGUAGE", "English"),
        source_language=os.environ.get("LOGICCUT_SOURCE_LANGUAGE", "auto"),
        max_segments_per_chunk=int(os.environ.get("LOGICCUT_TRANSLATION_CHUNK_SEGMENTS", "32")),
        max_chars_per_chunk=int(os.environ.get("LOGICCUT_TRANSLATION_CHUNK_CHARS", "9000")),
    )
    plan["translated_segments"] = translated_segments
    write_json(translated_segments_path, {"segments": translated_segments})
    plan["source_segments_preview"] = transcript.get("segments", [])[:20]
    diagnostics["stages"]["gemini_semantic_analysis"] = {
        "status": "ok",
        "adapter": "vertex-gemini",
        "model": plan["analysis_meta"].get("model"),
        "location": plan["analysis_meta"].get("location"),
        "prompt": relpath(prompt_path, project_dir),
        "raw_response": relpath(raw_path, project_dir),
        "highlight_count": len(plan.get("highlights", [])),
        "chapter_count": len(plan.get("chapters", [])),
        "translated_segment_count": len(plan.get("translated_segments", [])),
    }
    diagnostics["stages"]["gemini_chunked_translation"] = {
        "status": "ok",
        "adapter": "vertex-gemini",
        "model": plan["analysis_meta"].get("model"),
        "location": plan["analysis_meta"].get("location"),
        "chunk_count": translation_calls,
        "translated_segment_count": len(translated_segments),
        "raw_chunks": relpath(translation_chunks_path, project_dir),
        "output": relpath(translated_segments_path, project_dir),
    }
    write_json(analysis_path, plan)
    write_json(diagnostics_path, diagnostics)
    _SEMANTIC_REFRESHED_PROJECTS.add(project_dir)
    return plan


def _ensure_source_transcript(project_dir: Path, source: Path) -> dict[str, Any]:
    transcript_path = project_dir / "assets" / "source_transcript.json"
    if transcript_path.exists():
        with transcript_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    transcript = transcribe_media(source, language=os.environ.get("LOGICCUT_SOURCE_LANGUAGE") or None)
    write_json(transcript_path, transcript)
    return transcript


def json_load_with_preview(handle: Any) -> dict[str, Any]:
    data = normalize_semantic_text_fields(json.load(handle))
    data.setdefault("source_segments_preview", [])
    return data


def _chapter_card_source_items(plan: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for highlight in plan.get("highlights", []) or []:
        if isinstance(highlight, dict):
            items.append(dict(highlight))
    if items:
        return items
    for index, chapter in enumerate(plan.get("chapters", []) or [], start=1):
        if not isinstance(chapter, dict):
            continue
        start = float(chapter.get("start_time") or 0.0)
        end = float(chapter.get("end_time") or start + 1.0)
        title = str(chapter.get("title") or f"章节 {index}")
        summary = str(chapter.get("summary") or chapter.get("insert_strategy") or title)
        items.append(
            {
                "title": title,
                "start_time": start,
                "end_time": max(end, start + 0.1),
                "score": chapter.get("score", 80),
                "hook_sentence": summary,
                "virality_reason": summary,
            }
        )
    return items


def _story_plan_input(project_dir: Path, semantic_plan: dict[str, Any]) -> dict[str, Any]:
    assets_dir = project_dir / "assets"
    micro_path = assets_dir / "micro_food_highlights.json"
    if micro_path.exists():
        data = json.loads(micro_path.read_text(encoding="utf-8"))
        items = data.get("items")
        if isinstance(items, list) and items:
            return {
                "summary": semantic_plan.get("summary") or "探店素材的高密度美食高光。",
                "items": items,
            }
    expanded_path = assets_dir / "expanded_highlights.json"
    if expanded_path.exists():
        data = json.loads(expanded_path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return {
                "summary": semantic_plan.get("summary") or "剧情素材的关键冲突和情绪转折。",
                "expanded_highlights": data,
            }
    return semantic_plan


def _story_translated_segments(plan: dict[str, Any]) -> list[dict[str, Any]]:
    segments = plan.get("translated_segments")
    if not isinstance(segments, list):
        return []
    text_items = [str(item.get("text", "")) for item in segments if isinstance(item, dict)]
    if not text_items:
        return []
    cjk_count = sum(1 for text in text_items if _has_cjk(text))
    if cjk_count < max(1, len(text_items) // 3):
        return []
    return [item for item in segments if isinstance(item, dict)]


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _subtitle_segments_for_range(
    segments: list[dict[str, Any]],
    start: float,
    end: float,
) -> list[dict[str, Any]]:
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


def _card_template_sequence() -> list[str]:
    raw_sequence = os.environ.get("LOGICCUT_CARD_TEMPLATE_SEQUENCE", "").strip()
    if raw_sequence:
        return [item.strip() for item in raw_sequence.split(",") if item.strip()]
    return [os.environ.get("LOGICCUT_CARD_TEMPLATE", "news-hook").strip() or "news-hook"]


def _card_template_for_index(index: int, sequence: list[str]) -> str:
    if not sequence:
        return "news-hook"
    return sequence[(max(index, 1) - 1) % len(sequence)]
