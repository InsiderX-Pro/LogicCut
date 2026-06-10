from __future__ import annotations

import re
from typing import Any

from .text_normalize import normalize_display_text


_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2}):(\d{2})(?:[,.](\d{1,3}))?\s*$")


def parse_story_timestamp(value: str) -> tuple[float, float]:
    if "-" not in str(value):
        raise ValueError(f"timestamp range must contain '-': {value!r}")
    start_raw, end_raw = str(value).split("-", 1)
    return _parse_time(start_raw), _parse_time(end_raw)


def format_story_timestamp(start: float, end: float) -> str:
    return f"{_format_time(start)}-{_format_time(end)}"


def normalize_story_timeline(payload: dict[str, Any], *, duration: float | None = None) -> dict[str, Any]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("story timeline requires non-empty items")

    normalized_items: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise ValueError("story timeline items must be objects")
        ost = int(raw.get("OST", raw.get("ost", -1)))
        if ost not in (0, 1):
            raise ValueError(f"story item {index} has invalid OST={ost!r}")
        if "timestamp" in raw:
            start, end = parse_story_timestamp(str(raw["timestamp"]))
        else:
            start = float(raw.get("start", 0.0))
            end = float(raw.get("end", start))
        if duration is not None:
            start = max(0.0, min(float(duration), start))
            end = max(0.0, min(float(duration), end))
        if end <= start:
            raise ValueError(f"story item {index} has non-positive duration")

        item_type = "narration" if ost == 0 else "original"
        item = {
            "_id": int(raw.get("_id", raw.get("id", index)) or index),
            "type": str(raw.get("type") or item_type),
            "timestamp": format_story_timestamp(start, end),
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "picture": normalize_display_text(raw.get("picture") or raw.get("title") or ""),
            "narration": normalize_display_text(raw.get("narration") or ""),
            "OST": ost,
            "why": normalize_display_text(raw.get("why") or raw.get("virality_reason") or ""),
        }
        if item["type"] not in {"narration", "original"}:
            item["type"] = item_type
        if ost == 0:
            item["type"] = "narration"
        if ost == 1:
            item["type"] = "original"
        for key in ("title", "subtitle", "source_highlight_id", "hook_sentence", "score"):
            if key in raw and raw[key] is not None:
                value = raw[key]
                item[key] = normalize_display_text(value) if isinstance(value, str) else value
        normalized_items.append(item)

    _assert_no_source_overlap(normalized_items)
    return {
        "story_arc": normalize_display_text(payload.get("story_arc") or payload.get("summary") or ""),
        "style_id": str(payload.get("style_id") or payload.get("style") or "story_news"),
        "items": normalized_items,
    }


def _parse_time(value: str) -> float:
    match = _TIME_RE.match(value)
    if not match:
        raise ValueError(f"invalid timestamp: {value!r}")
    hours, minutes, seconds, millis = match.groups()
    ms = int((millis or "0").ljust(3, "0")[:3])
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + ms / 1000.0


def _format_time(seconds: float) -> str:
    millis = int(round(max(0.0, seconds) * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def _assert_no_source_overlap(items: list[dict[str, Any]]) -> None:
    ordered = sorted(items, key=lambda item: (float(item["start"]), float(item["end"])))
    previous: dict[str, Any] | None = None
    for item in ordered:
        if previous and float(item["start"]) < float(previous["end"]):
            raise ValueError(
                "story source ranges overlap: "
                f"{previous.get('_id')} {previous.get('timestamp')} and {item.get('_id')} {item.get('timestamp')}"
            )
        previous = item
