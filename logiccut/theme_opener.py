from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .text_normalize import normalize_display_text


DEFAULT_THEME_OPENER_TARGET_SECONDS = 20


def build_codex_prompt(
    transcript: dict[str, Any],
    *,
    source_name: str,
    theme: str | None = None,
    target_seconds: int = DEFAULT_THEME_OPENER_TARGET_SECONDS,
    max_chars: int = 24000,
) -> str:
    requested_theme = normalize_display_text(theme or "由 Codex 从 transcript 中推荐一个最适合做开头的主题")
    transcript_text = _format_transcript(transcript, max_chars=max_chars)
    return f"""# LogicCut V0.2 Theme Opener Plan

你现在是 LogicCut 的 Codex 创意分析层。请只基于下面的 transcript 做判断。

重要边界：
- 不要调用 OpenAI/Gemini/Claude API。
- 不要写代码。
- 你要像视频二创编导一样，直接分析 transcript，写出一个可执行 JSON。
- 输出文件名必须是 `theme_opener_plan.json`。

任务：
为输入视频制作一个 15-30 秒的开头吸引片段。这个片段要围绕一个明确主题，用 3-6 个短片段快速证明主题，让观众愿意继续看正片。

用户指定主题：
{requested_theme}

视频文件：
{source_name}

剪辑要求：
- 总时长接近 {target_seconds} 秒，必须在 15-30 秒之间。
- 默认选 3 个片段；每个片段建议 3-8 秒。
- 每个片段都要有中文字幕，不要繁体字。
- 每个片段必须解释为什么能证明主题。
- 片段不能只是平均切片，要有画面/语义证据。
- 最终渲染时 LogicCut 会在左上角加 `高光剪辑` 水印，你不用在 JSON 里写水印样式。

请写入 JSON，格式严格如下：

```json
{{
  "theme": "中国安全",
  "opening_hook": "一句能放在报告里的开头判断",
  "clips": [
    {{
      "start": 0.0,
      "end": 5.0,
      "subtitle": "这一段要烧录到视频底部的中文字幕",
      "reason": "为什么这一段能证明主题",
      "visual_role": "建立主题 / 反差证明 / 情绪收尾"
    }}
  ]
}}
```

Transcript:
{transcript_text}
""".strip()


def write_theme_opener_codex_prompt(
    path: Path,
    transcript: dict[str, Any],
    *,
    source_name: str,
    theme: str | None = None,
    target_seconds: int = DEFAULT_THEME_OPENER_TARGET_SECONDS,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        build_codex_prompt(transcript, source_name=source_name, theme=theme, target_seconds=target_seconds),
        encoding="utf-8",
    )
    return path


def load_theme_opener_plan(
    path: Path,
    *,
    source_duration: float,
    transcript: dict[str, Any] | None = None,
    min_total_seconds: float = 15.0,
    max_total_seconds: float = 30.0,
) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("theme opener plan must be a JSON object")
    clips_raw = data.get("clips")
    if not isinstance(clips_raw, list):
        raise ValueError("theme opener plan requires clips")
    if not 3 <= len(clips_raw) <= 6:
        raise ValueError("theme opener plan requires 3-6 clips")

    clips = [
        _normalize_clip(item, index=index, source_duration=source_duration, transcript=transcript)
        for index, item in enumerate(clips_raw, start=1)
    ]
    total_duration = round(sum(float(item["duration"]) for item in clips), 3)
    if not (min_total_seconds <= total_duration <= max_total_seconds):
        raise ValueError(f"theme opener total duration must be 15-30 seconds, got {total_duration:.3f}")
    return {
        "theme": normalize_display_text(data.get("theme") or "主题开头"),
        "opening_hook": normalize_display_text(data.get("opening_hook") or data.get("hook") or ""),
        "watermark": normalize_display_text(data.get("watermark") or "高光剪辑"),
        "clips": clips,
        "total_duration": total_duration,
    }


def _normalize_clip(
    item: Any,
    *,
    index: int,
    source_duration: float,
    transcript: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"theme opener clip {index} must be an object")
    start = float(item.get("start", item.get("start_time", 0.0)))
    end = float(item.get("end", item.get("end_time", start)))
    if source_duration > 0:
        start = max(0.0, min(start, max(0.0, source_duration - 0.1)))
        end = max(0.0, min(end, source_duration))
    start, end = _snap_range_to_transcript(start, end, transcript)
    if end <= start:
        raise ValueError(f"theme opener clip {index} has invalid time range")
    return {
        "id": f"theme_opener_clip_{index:02}",
        "start": round(start, 3),
        "end": round(end, 3),
        "duration": round(end - start, 3),
        "subtitle": normalize_display_text(item.get("subtitle") or item.get("text") or ""),
        "reason": normalize_display_text(item.get("reason") or item.get("why") or ""),
        "visual_role": normalize_display_text(item.get("visual_role") or item.get("role") or ""),
    }


def _snap_range_to_transcript(
    start: float,
    end: float,
    transcript: dict[str, Any] | None,
    *,
    tolerance: float = 0.18,
    end_guard: float = 0.08,
) -> tuple[float, float]:
    if not transcript:
        return start, end
    segments = transcript.get("segments", [])
    if not isinstance(segments, list):
        return start, end
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        try:
            segment_end = float(segment.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        if abs(end - segment_end) <= tolerance:
            return start, max(start + 0.1, segment_end - end_guard)
    return start, end


def _format_transcript(transcript: dict[str, Any], *, max_chars: int) -> str:
    rows = []
    for segment in transcript.get("segments", []):
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        rows.append(f"[{start:.2f}-{end:.2f}] {text}")
    joined = "\n".join(rows)
    if len(joined) > max_chars:
        return joined[:max_chars] + "\n[TRUNCATED]"
    return joined
