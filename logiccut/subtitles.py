from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .text_normalize import normalize_display_text


# Adapted from subcap 0.2.2's ASS style model and SRT bypass flow.
# subcap is MIT licensed. See THIRD_PARTY_NOTICES.md for attribution.
PRESET_NAMES = ("captioner", "modern", "outline", "minimal", "bold")
_POSITION_MAP = {"bottom": 2, "center": 5, "top": 8}
_TIMECODE_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
    r"\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)


@dataclass(frozen=True)
class SubtitleEntry:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class StyleConfig:
    font_name: str
    font_size: int
    bold: bool
    primary_color: str
    outline_color: str
    back_color: str
    border_style: int
    outline: int
    shadow: int
    margin_l: int
    margin_r: int
    margin_v: int
    alignment: int
    spacing: float
    play_res_x: int
    play_res_y: int


def parse_srt(path: Path) -> list[SubtitleEntry]:
    text = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n{2,}", text.strip())
    entries: list[SubtitleEntry] = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        timecode_index = next((index for index, line in enumerate(lines) if _TIMECODE_RE.search(line)), None)
        if timecode_index is None:
            continue
        match = _TIMECODE_RE.search(lines[timecode_index])
        if match is None:
            continue
        body = "\n".join(lines[timecode_index + 1 :]).strip()
        if body:
            entries.append(
                SubtitleEntry(
                    start=_timecode_to_seconds(match.group(1), match.group(2), match.group(3), match.group(4)),
                    end=_timecode_to_seconds(match.group(5), match.group(6), match.group(7), match.group(8)),
                    text=body,
                )
            )
    return entries


def style_for_video(
    preset: str,
    width: int,
    height: int,
    *,
    font_name: str = "Arial",
    line_spacing: float | None = None,
    position: str = "bottom",
) -> StyleConfig:
    if preset not in PRESET_NAMES:
        raise ValueError(f"Unknown subtitle preset {preset!r}. Valid: {PRESET_NAMES}")

    alignment = _POSITION_MAP.get(position, 2)
    landscape = width >= height
    clean_font_size = max(28, min(44 if landscape else 40, int(height * (0.071 if landscape else 0.052))))
    base = dict(
        font_name=font_name,
        font_size=clean_font_size if preset == "captioner" else (56 if landscape else 42),
        bold=True,
        primary_color="&H00FFFFFF",
        outline_color="&H00000000",
        back_color="&H00000000" if preset == "captioner" else "&H50000000",
        border_style=1 if preset == "captioner" else 3,
        outline=3 if preset == "captioner" else 14,
        shadow=1 if preset == "captioner" else 0,
        margin_l=48 if preset == "captioner" else (100 if landscape else 40),
        margin_r=48 if preset == "captioner" else (100 if landscape else 40),
        margin_v=28 if preset == "captioner" else (50 if landscape else 80),
        alignment=alignment,
        spacing=line_spacing if line_spacing is not None else 0.0,
        play_res_x=width,
        play_res_y=height,
    )
    if preset == "outline":
        base.update(back_color="&H00000000", border_style=1, outline=3)
    elif preset == "minimal":
        base.update(bold=False, back_color="&HA0000000", border_style=1, outline=1, shadow=2)
    elif preset == "bold":
        base.update(back_color="&H00000000", border_style=3, outline=16)
    return StyleConfig(**base)


def generate_ass(subtitles: Sequence[SubtitleEntry], config: StyleConfig) -> str:
    bold = -1 if config.bold else 0
    style_line = (
        f"Style: Default,{config.font_name},{config.font_size},"
        f"{config.primary_color},{config.primary_color},"
        f"{config.outline_color},{config.back_color},"
        f"{bold},0,0,0,"
        f"100,100,{config.spacing},0,"
        f"{config.border_style},{config.outline},{config.shadow},"
        f"{config.alignment},"
        f"{config.margin_l},{config.margin_r},{config.margin_v},1"
    )
    dialogue_lines = [
        f"Dialogue: 0,{_ass_time(item.start)},{_ass_time(item.end)},Default,,0,0,0,,{_ass_text(item.text)}"
        for item in subtitles
    ]
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "WrapStyle: 0",
            f"PlayResX: {config.play_res_x}",
            f"PlayResY: {config.play_res_y}",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            style_line,
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *dialogue_lines,
            "",
        ]
    )


def write_ass_from_srt(
    srt_path: Path,
    ass_path: Path,
    *,
    width: int,
    height: int,
    preset: str = "modern",
    font_name: str = "Arial",
    position: str = "bottom",
    max_chars: int | None = None,
    max_lines: int = 2,
    line_spacing: float | None = None,
) -> Path:
    max_chars = max_chars or (28 if height > width else 42)
    entries = [
        SubtitleEntry(item.start, item.end, _wrap_for_ass(item.text, max_chars=max_chars, max_lines=max_lines))
        for item in parse_srt(srt_path)
    ]
    config = style_for_video(
        preset,
        width,
        height,
        font_name=font_name,
        line_spacing=line_spacing,
        position=position,
    )
    ass_path.parent.mkdir(parents=True, exist_ok=True)
    ass_path.write_text(generate_ass(entries, config), encoding="utf-8")
    return ass_path


def ffmpeg_ass_filter(path: Path) -> str:
    return f"ass={_escape_filter_path(path.resolve())}"


def _wrap_for_ass(text: str, *, max_chars: int, max_lines: int) -> str:
    clean = normalize_display_text(text).replace("\\N", "\n")
    raw_lines: list[str] = []
    for part in clean.splitlines() or [clean]:
        raw_lines.extend(_wrap_cjk_line(part.strip(), max_chars=max_chars))
    return "\\N".join(raw_lines[:max_lines])


def _wrap_cjk_line(text: str, *, max_chars: int) -> list[str]:
    if not text:
        return [""]
    lines: list[str] = []
    rest = text
    while len(rest) > max_chars:
        split_at = _split_index(rest, max_chars)
        lines.append(rest[:split_at].strip())
        rest = rest[split_at:].strip()
    if rest:
        lines.append(rest)
    return lines


def _split_index(text: str, max_chars: int) -> int:
    window = text[: max_chars + 1]
    breakpoints = "，。！？；：、,.!?;: "
    for index in range(len(window) - 1, max(max_chars // 2, 1), -1):
        if window[index - 1] in breakpoints:
            return index
    return min(max_chars, len(text))


def _ass_text(text: str) -> str:
    return text.replace("{", "（").replace("}", "）").replace("\n", "\\N")


def _ass_time(seconds: float) -> str:
    centiseconds = int(round(seconds * 100))
    hours, rem = divmod(centiseconds, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _timecode_to_seconds(hours: str, minutes: str, seconds: str, millis: str) -> float:
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:")
