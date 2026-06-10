from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from .text_normalize import normalize_display_text


LLMFn = Callable[[str], str]


def transcribe_media(media_path: Path, *, language: str | None = None) -> dict[str, Any]:
    """Transcribe a local video/audio file with AI-Youtube-Shorts' faster-whisper adapter."""
    root = Path(os.environ.get("LOGICCUT_ROOT", Path(__file__).resolve().parents[1]))
    third_party = root / "third_party" / "AI-Youtube-Shorts-Generator"
    if str(third_party) not in sys.path:
        sys.path.insert(0, str(third_party))

    try:
        from shorts_generator.local.transcriber import transcribe_local
    except Exception as exc:  # pragma: no cover - deployment dependency
        if _env_truthy("LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK"):
            return _fallback_transcript(media_path, language=language)
        raise RuntimeError(
            "AI-Youtube-Shorts-Generator transcription is not installed. "
            "Install third_party/AI-Youtube-Shorts-Generator for real ASR, or set "
            "LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK=1 only for the local demo path."
        ) from exc

    return transcribe_local(str(media_path), language=language)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _fallback_transcript(media_path: Path, *, language: str | None = None) -> dict[str, Any]:
    duration = _probe_duration(media_path)
    segment_count = max(3, min(6, int(round(duration / 6.0)) or 3))
    step = duration / segment_count if segment_count else duration
    seed_text = [
        "The opening shows a visual hook that can introduce the source video.",
        "This moment gives the viewer a clear reason to keep watching.",
        "The middle section acts as supporting evidence for the selected theme.",
        "The clip builds momentum with a stronger visual beat.",
        "This part can work as the final proof point before the full video.",
        "The ending closes the opener and prepares the audience for the main story.",
    ]
    segments: list[dict[str, Any]] = []
    for index in range(segment_count):
        start = round(index * step, 3)
        end = round(duration if index == segment_count - 1 else (index + 1) * step, 3)
        segments.append(
            {
                "start": start,
                "end": end,
                "text": seed_text[index % len(seed_text)],
            }
        )
    return {
        "duration": round(duration, 3),
        "language": language or "synthetic-demo",
        "source": str(media_path),
        "adapter": "logiccut-fallback-transcript",
        "warning": "Synthetic transcript for local demo only. Use real ASR for production editing.",
        "segments": segments,
    }


def _probe_duration(media_path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(media_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return 30.0
    try:
        return max(0.1, float(json.loads(proc.stdout)["format"]["duration"]))
    except Exception:
        return 30.0


def call_vertex_gemini(prompt: str) -> str:
    """Call Vertex Gemini with the same service-account style used by the original project."""
    try:
        import vertexai
        from vertexai.generative_models import GenerationConfig, GenerativeModel
    except Exception as exc:  # pragma: no cover - deployment dependency
        raise RuntimeError("vertexai is required for Gemini semantic analysis") from exc

    credentials_json = Path(os.environ.get("GEMINI_CREDENTIALS_JSON", "")).expanduser()
    if not credentials_json.exists():
        raise RuntimeError("GEMINI_CREDENTIALS_JSON is required for Gemini semantic analysis")

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_json.resolve())
    with credentials_json.open("r", encoding="utf-8") as handle:
        project_id = str(json.load(handle).get("project_id") or "").strip()
    if not project_id:
        raise RuntimeError("Gemini credentials json missing project_id")

    location = os.environ.get("GEMINI_VERTEX_LOCATION", "us-central1")
    model_name = os.environ.get("LOGICCUT_GEMINI_MODEL", "gemini-2.5-pro")
    vertexai.init(project=project_id, location=location)
    model = GenerativeModel(model_name)
    response = model.generate_content(
        prompt,
        generation_config=GenerationConfig(
            response_mime_type="application/json",
            temperature=float(os.environ.get("LOGICCUT_GEMINI_TEMPERATURE", "0.2")),
            max_output_tokens=int(os.environ.get("LOGICCUT_GEMINI_MAX_OUTPUT_TOKENS", "8192")),
        ),
    )
    text = getattr(response, "text", "") or ""
    if not text.strip():
        raise RuntimeError("Gemini returned an empty semantic-analysis response")
    return text


def build_semantic_creation_plan(
    transcript: dict[str, Any],
    *,
    llm_fn: LLMFn = call_vertex_gemini,
    backend_name: str = "vertex-gemini",
    target_language: str = "English",
    highlight_count: int = 3,
    chapter_count: int = 4,
) -> dict[str, Any]:
    prompt = build_semantic_prompt(
        transcript,
        target_language=target_language,
        highlight_count=highlight_count,
        chapter_count=chapter_count,
    )
    raw = llm_fn(prompt)
    parsed = parse_json_loose(raw)
    return normalize_semantic_plan(
        parsed,
        transcript=transcript,
        backend_name=backend_name,
        target_language=target_language,
    )


def build_semantic_prompt(
    transcript: dict[str, Any],
    *,
    target_language: str,
    highlight_count: int,
    chapter_count: int,
) -> str:
    transcript_text = format_transcript(transcript)
    return f"""
You are LogicCut's creative video editor. Analyze the transcript semantically,
not by fixed timestamps. Select viral highlight moments and design a personalized
remix structure for creators who need differentiated repost/remix videos.

Return JSON only. Do not use markdown.

Required JSON shape:
{{
  "summary": "one-paragraph source video summary in {target_language}",
  "highlights": [
    {{
      "title": "short highlight title in {target_language}",
      "start_time": 0.0,
      "end_time": 1.0,
      "score": 0,
      "hook_sentence": "the opening sentence that makes this a viral highlight",
      "virality_reason": "why this moment should be cut as a hook"
    }}
  ],
  "chapters": [
    {{
      "title": "chapter title in {target_language}",
      "start_time": 0.0,
      "end_time": 1.0,
      "summary": "chapter summary in {target_language}",
      "insert_strategy": "how to personalize this chapter with a summary card, insert, or commentary"
    }}
  ],
  "remix": {{
    "opening_summary": "10-second opener concept in {target_language}",
    "closing_summary": "ending takeaway in {target_language}",
    "style_notes": "specific editing style notes"
  }}
}}

Rules:
- Use transcript meaning, conflict, surprise, practical value, and narrative turns.
- A viral highlight must not be just the first seconds unless the transcript itself proves it.
- Generate around {highlight_count} highlights and {chapter_count} semantic chapters.
- Chapters should follow topic/story boundaries, not equal-duration slicing.
- Clamp all timestamps inside the source duration.
- Do not translate the full transcript in this response. Translation is handled by a separate chunked step.

Transcript:
{transcript_text}
""".strip()


def translate_transcript_segments(
    transcript: dict[str, Any],
    *,
    llm_fn: LLMFn = call_vertex_gemini,
    target_language: str = "中文",
    source_language: str = "auto",
    max_segments_per_chunk: int = 32,
    max_chars_per_chunk: int = 9000,
) -> list[dict[str, Any]]:
    """Translate every transcript segment while preserving the original timeline."""
    segments = [
        {
            "index": index,
            "start": float(segment.get("start", 0.0)),
            "end": float(segment.get("end", 0.0)),
            "text": str(segment.get("text", "")).strip(),
        }
        for index, segment in enumerate(transcript.get("segments", []))
        if str(segment.get("text", "")).strip()
    ]
    translations: dict[int, str] = {}
    for chunk in chunk_segments(
        segments,
        max_segments_per_chunk=max_segments_per_chunk,
        max_chars_per_chunk=max_chars_per_chunk,
    ):
        translations.update(
            translate_segment_chunk(
                chunk,
                llm_fn=llm_fn,
                target_language=target_language,
                source_language=source_language,
            )
        )

    translated_segments: list[dict[str, Any]] = []
    for segment in segments:
        text = translations.get(int(segment["index"])) or segment["text"]
        translated_segments.append(
            {
                "start": segment["start"],
                "end": segment["end"],
                "text": normalize_display_text(text),
            }
        )
    return translated_segments


def translate_segment_chunk(
    segments: list[dict[str, Any]],
    *,
    llm_fn: LLMFn,
    target_language: str,
    source_language: str,
) -> dict[int, str]:
    prompt = build_translation_prompt(
        segments,
        target_language=target_language,
        source_language=source_language,
    )
    try:
        raw = llm_fn(prompt)
        parsed = parse_json_loose(raw)
        items = parsed.get("translations") or parsed.get("translated_segments") or []
        return {
            int(item["index"]): str(item.get("text", "")).strip()
            for item in items
            if isinstance(item, dict) and "index" in item
        }
    except Exception:
        if len(segments) <= 1:
            item = segments[0]
            return {int(item["index"]): str(item.get("text", "")).strip()}
        midpoint = max(1, len(segments) // 2)
        left = translate_segment_chunk(
            segments[:midpoint],
            llm_fn=llm_fn,
            target_language=target_language,
            source_language=source_language,
        )
        right = translate_segment_chunk(
            segments[midpoint:],
            llm_fn=llm_fn,
            target_language=target_language,
            source_language=source_language,
        )
        left.update(right)
        return left


def chunk_segments(
    segments: list[dict[str, Any]],
    *,
    max_segments_per_chunk: int,
    max_chars_per_chunk: int,
) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for segment in segments:
        text_len = len(str(segment.get("text", "")))
        would_exceed_count = len(current) >= max(1, max_segments_per_chunk)
        would_exceed_chars = current and current_chars + text_len > max_chars_per_chunk
        if would_exceed_count or would_exceed_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(segment)
        current_chars += text_len
    if current:
        chunks.append(current)
    return chunks


def build_translation_prompt(
    segments: list[dict[str, Any]],
    *,
    target_language: str,
    source_language: str,
) -> str:
    payload = {
        "segments": [
            {
                "index": int(item["index"]),
                "start": float(item["start"]),
                "end": float(item["end"]),
                "text": str(item["text"]),
            }
            for item in segments
        ]
    }
    return (
        "Translate each segment into "
        f"{target_language}. Preserve meaning, names, technical terms, and speaker intent. "
        "Return JSON only with this shape: "
        '{"translations":[{"index":0,"text":"translated text"}]}. '
        f"Source language: {source_language}.\n\n"
        "SEGMENTS_JSON:\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def format_transcript(transcript: dict[str, Any], *, max_chars: int = 28000) -> str:
    rows = []
    for segment in transcript.get("segments", []):
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        text = str(segment.get("text", "")).strip()
        if text:
            rows.append(f"[{start:.2f}-{end:.2f}] {text}")
    joined = "\n".join(rows)
    if len(joined) > max_chars:
        return joined[:max_chars] + "\n[TRUNCATED]"
    return joined


def parse_json_loose(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def normalize_semantic_plan(
    data: dict[str, Any],
    *,
    transcript: dict[str, Any],
    backend_name: str,
    target_language: str,
) -> dict[str, Any]:
    duration = float(transcript.get("duration") or _duration_from_segments(transcript.get("segments", [])))
    translated = [
        _normalize_segment(item, duration)
        for item in data.get("translated_segments", [])
        if _has_time_range(item)
    ]
    highlights = [
        _normalize_highlight(item, duration, index)
        for index, item in enumerate(data.get("highlights", []), start=1)
        if _has_highlight_range(item)
    ]
    chapters = [
        _normalize_chapter(item, duration, index)
        for index, item in enumerate(data.get("chapters", []), start=1)
        if _has_highlight_range(item)
    ]

    if not translated:
        translated = [
            {
                "start": float(s.get("start", 0.0)),
                "end": float(s.get("end", 0.0)),
                "text": str(s.get("text", "")).strip(),
            }
            for s in transcript.get("segments", [])
            if str(s.get("text", "")).strip()
        ]
    if not highlights:
        raise RuntimeError("semantic analysis returned no highlights")
    if not chapters:
        chapters = _fallback_chapters(transcript, duration)

    plan = {
        "analysis_meta": {
            "backend": backend_name,
            "model": os.environ.get("LOGICCUT_GEMINI_MODEL", "gemini-2.5-pro")
            if "gemini" in backend_name
            else backend_name,
            "location": os.environ.get("GEMINI_VERTEX_LOCATION", "us-central1")
            if "gemini" in backend_name
            else None,
            "target_language": target_language,
            "duration": duration,
            "segment_count": len(transcript.get("segments", [])),
        },
        "summary": str(data.get("summary", "")).strip(),
        "translated_segments": translated,
        "highlights": sorted(highlights, key=lambda item: int(item.get("score", 0)), reverse=True),
        "chapters": sorted(chapters, key=lambda item: float(item.get("start_time", 0.0))),
        "remix": data.get("remix") if isinstance(data.get("remix"), dict) else {},
    }
    return normalize_semantic_text_fields(plan)


def normalize_semantic_text_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize semantic-plan display strings to simplified Chinese."""
    return _normalize_json_strings(data)


def write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


def _duration_from_segments(segments: list[dict[str, Any]]) -> float:
    if not segments:
        return 0.0
    return max(float(item.get("end", 0.0)) for item in segments)


def _has_time_range(item: dict[str, Any]) -> bool:
    return isinstance(item, dict) and "start" in item and "end" in item


def _has_highlight_range(item: dict[str, Any]) -> bool:
    return isinstance(item, dict) and "start_time" in item and "end_time" in item


def _normalize_segment(item: dict[str, Any], duration: float) -> dict[str, Any]:
    start, end = _clamp_range(float(item["start"]), float(item["end"]), duration)
    return {"start": start, "end": end, "text": normalize_display_text(item.get("text", ""))}


def _normalize_highlight(item: dict[str, Any], duration: float, index: int) -> dict[str, Any]:
    start, end = _clamp_range(float(item["start_time"]), float(item["end_time"]), duration)
    return {
        "id": f"semantic_highlight_{index:02}",
        "title": normalize_display_text(item.get("title") or f"Highlight {index}"),
        "start_time": start,
        "end_time": end,
        "score": int(float(item.get("score", 0))),
        "hook_sentence": normalize_display_text(item.get("hook_sentence", "")),
        "virality_reason": normalize_display_text(item.get("virality_reason", "")),
    }


def _normalize_chapter(item: dict[str, Any], duration: float, index: int) -> dict[str, Any]:
    start, end = _clamp_range(float(item["start_time"]), float(item["end_time"]), duration)
    return {
        "id": f"semantic_chapter_{index:02}",
        "title": normalize_display_text(item.get("title") or f"Chapter {index}"),
        "start_time": start,
        "end_time": end,
        "summary": normalize_display_text(item.get("summary", "")),
        "insert_strategy": normalize_display_text(item.get("insert_strategy", "")),
    }


def _clamp_range(start: float, end: float, duration: float) -> tuple[float, float]:
    safe_duration = max(duration, 0.1)
    start = max(0.0, min(start, safe_duration - 0.1))
    end = max(start + 0.1, min(end, safe_duration))
    return round(start, 3), round(end, 3)


def _normalize_json_strings(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_display_text(value)
    if isinstance(value, list):
        return [_normalize_json_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_json_strings(item) for key, item in value.items()}
    return value


def _fallback_chapters(transcript: dict[str, Any], duration: float) -> list[dict[str, Any]]:
    segments = transcript.get("segments", [])
    if not segments:
        return []
    count = min(4, max(1, len(segments)))
    step = duration / count if duration else 1.0
    chapters = []
    for index in range(count):
        start = index * step
        end = duration if index == count - 1 else (index + 1) * step
        chapters.append(
            {
                "id": f"semantic_chapter_{index + 1:02}",
                "title": f"Chapter {index + 1}",
                "start_time": round(start, 3),
                "end_time": round(end, 3),
                "summary": "",
                "insert_strategy": "Fallback chapter generated because semantic analysis omitted chapters.",
            }
        )
    return chapters
