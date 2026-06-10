from __future__ import annotations

from typing import Any

from .story_styles import get_story_style
from .story_timeline import normalize_story_timeline
from .text_normalize import normalize_display_text


def build_story_timeline_from_semantic_plan(
    plan: dict[str, Any],
    *,
    duration: float,
    style_id: str = "story_news",
    item_count: int = 6,
    narration_duration: float = 3.2,
    original_duration: float = 4.0,
) -> dict[str, Any]:
    style = get_story_style(style_id)
    highlights = _select_highlights(plan)[: max(1, item_count)]
    if not highlights:
        raise ValueError("story planner requires highlights or micro highlight items")

    items: list[dict[str, Any]] = []
    for pair_index, highlight in enumerate(highlights, start=1):
        start = float(highlight.get("start_time", highlight.get("start", 0.0)))
        end = float(highlight.get("end_time", highlight.get("end", start + original_duration)))
        title = normalize_display_text(highlight.get("title") or f"片段 {pair_index}")
        narration_title = _title_for_sentence(title)
        reason = normalize_display_text(highlight.get("virality_reason") or highlight.get("reason") or highlight.get("hook_sentence") or title)
        hook = normalize_display_text(highlight.get("hook_sentence") or title)

        original_start = max(0.0, min(duration, start))
        original_end = max(original_start + 0.1, min(duration, original_start + min(max(end - start, 0.1), original_duration)))
        narration_end = max(0.0, original_start - 0.15)
        narration_start = max(0.0, narration_end - narration_duration)
        if narration_end - narration_start < 1.0:
            after_start = min(duration, original_end + 0.15)
            after_end = min(duration, after_start + narration_duration)
            if after_end - after_start >= 1.0:
                narration_start, narration_end = after_start, after_end
            else:
                narration_start = max(0.0, original_start)
                narration_end = min(duration, original_start + min(narration_duration, max(original_end - original_start, 1.0)))
                original_start = min(duration, narration_end + 0.15)
                original_end = min(duration, original_start + min(original_duration, max(end - start, 1.0)))

        narration_id = len(items) + 1
        items.append(
            {
                "_id": narration_id,
                "type": "narration",
                "timestamp": _timestamp(narration_start, narration_end),
                "title": title,
                "picture": f"{title}：{hook}",
                "narration": _limit_text(
                    style.narration_pattern.format(title=narration_title, reason=_short_reason(reason)),
                    max_chars=44,
                ),
                "OST": 0,
                "why": f"旁白先建立上下文：{reason}",
                "source_highlight_id": str(highlight.get("id") or highlight.get("source_clip_ids") or f"highlight_{pair_index:02}"),
                "hook_sentence": hook,
                "score": highlight.get("score", 0),
            }
        )
        items.append(
            {
                "_id": narration_id + 1,
                "type": "original",
                "timestamp": _timestamp(original_start, original_end),
                "title": title,
                "picture": f"{title}：保留原声高光",
                "narration": f"播放原片{narration_id + 1}",
                "OST": 1,
                "why": style.original_reason_pattern,
                "source_highlight_id": str(highlight.get("id") or highlight.get("source_clip_ids") or f"highlight_{pair_index:02}"),
                "hook_sentence": hook,
                "score": highlight.get("score", 0),
                "subtitle": _limit_text(reason, max_chars=52),
            }
        )

    return normalize_story_timeline(
        {
            "story_arc": normalize_display_text(plan.get("summary") or style.opening),
            "style_id": style.id,
            "items": _drop_overlaps_preserving_order(items),
        },
        duration=duration,
    )


def _select_highlights(plan: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("micro_food_highlights", "items", "expanded_highlights", "highlights"):
        value = plan.get(key)
        if isinstance(value, list) and value:
            return [_normalize_highlight(item) for item in value if isinstance(item, dict)]
    if isinstance(plan.get("micro_food_highlights"), dict):
        nested = plan["micro_food_highlights"].get("items")
        if isinstance(nested, list):
            return [_normalize_highlight(item) for item in nested if isinstance(item, dict)]
    return []


def _normalize_highlight(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    if "start_time" not in normalized and "start" in normalized:
        normalized["start_time"] = normalized["start"]
    if "end_time" not in normalized and "end" in normalized:
        normalized["end_time"] = normalized["end"]
    return normalized


def _drop_overlaps_preserving_order(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    last_end = -1.0
    for item in sorted(items, key=lambda raw: _start_from_timestamp(str(raw["timestamp"]))):
        start, end = _range_from_timestamp(str(item["timestamp"]))
        if start < last_end:
            continue
        kept.append(item)
        last_end = end
    for index, item in enumerate(kept, start=1):
        item["_id"] = index
        if int(item.get("OST", 0)) == 1:
            item["narration"] = f"播放原片{index}"
    return kept


def _timestamp(start: float, end: float) -> str:
    from .story_timeline import format_story_timestamp

    return format_story_timestamp(start, end)


def _range_from_timestamp(value: str) -> tuple[float, float]:
    from .story_timeline import parse_story_timestamp

    return parse_story_timestamp(value)


def _start_from_timestamp(value: str) -> float:
    return _range_from_timestamp(value)[0]


def _strip_sentence(text: str) -> str:
    return str(text).strip().rstrip("。.!！？")


def _title_for_sentence(title: str) -> str:
    clean = _strip_sentence(normalize_display_text(title))
    return clean or normalize_display_text(title)


def _short_reason(text: str, *, max_chars: int = 24) -> str:
    clean = _strip_sentence(normalize_display_text(text))
    for separator in ("，", "。", "；", "、", ",", ";"):
        if separator in clean:
            first = clean.split(separator, 1)[0].strip()
            if 4 <= len(first) <= max_chars:
                return first
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip("，。；：、 ")


def _limit_text(text: str, *, max_chars: int) -> str:
    clean = normalize_display_text(text)
    if len(clean) <= max_chars:
        return clean
    return clean[: max(1, max_chars - 1)].rstrip("，。；：、 ") + "。"
