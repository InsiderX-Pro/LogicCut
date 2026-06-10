from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

from .subtitles import ffmpeg_ass_filter, write_ass_from_srt


def run_command(cmd: list[str], log_file: Path | None = None) -> None:
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write("$ " + " ".join(cmd) + "\n")
            proc = subprocess.run(cmd, stdout=handle, stderr=subprocess.STDOUT, text=True)
    else:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")


def ffprobe_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    data = json.loads(proc.stdout)
    return float(data["format"]["duration"])


def ffprobe_video_size(path: Path) -> tuple[int, int]:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    data = json.loads(proc.stdout)
    stream = data["streams"][0]
    return int(stream["width"]), int(stream["height"])


def ensure_sample_video(path: Path, duration: float = 6.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=16000",
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-movflags",
            "+faststart",
            str(path),
        ]
    )
    return path


def render_clip(
    source: Path,
    output: Path,
    start: float,
    duration: float,
    log_file: Path | None = None,
    *,
    accurate: bool = False,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if accurate:
        cmd.extend(["-i", str(source), "-ss", f"{start:.3f}"])
    else:
        cmd.extend(["-ss", f"{start:.3f}", "-i", str(source)])
    cmd.extend(
        [
            "-t",
            f"{max(duration, 0.1):.3f}",
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
            str(output),
        ]
    )
    run_command(cmd, log_file=log_file)
    return output


def concat_videos(inputs: list[Path], output: Path, log_file: Path | None = None) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    concat_file = output.with_suffix(".concat.txt")
    with concat_file.open("w", encoding="utf-8") as handle:
        for item in inputs:
            handle.write(f"file '{item.resolve()}'\n")
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ],
        log_file=log_file,
    )
    return output


def concat_videos_reencode(inputs: list[Path], output: Path, log_file: Path | None = None) -> Path:
    if not inputs:
        raise ValueError("concat_videos_reencode requires at least one input")
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = ffprobe_video_size(inputs[0])
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for item in inputs:
        cmd.extend(["-i", str(item)])

    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, _item in enumerate(inputs):
        filters.append(
            f"[{index}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{index}]"
        )
        filters.append(
            f"[{index}:a:0]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a{index}]"
        )
        concat_inputs.append(f"[v{index}][a{index}]")
    filters.append("".join(concat_inputs) + f"concat=n={len(inputs)}:v=1:a=1[v][a]")
    cmd.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[v]",
            "-map",
            "[a]",
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
            str(output),
        ]
    )
    run_command(
        cmd,
        log_file=log_file,
    )
    return output


def burn_subtitles(
    source: Path,
    subtitle: Path,
    output: Path,
    log_file: Path | None = None,
    *,
    style_size: tuple[int, int] | None = None,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    subtitle_filter = _styled_subtitle_filter(source, subtitle, style_size=style_size)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vf",
            subtitle_filter,
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
            str(output),
        ],
        log_file=log_file,
    )
    return output


def render_text_watermark(
    source: Path,
    output: Path,
    text: str,
    log_file: Path | None = None,
    *,
    font_size: int = 32,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    text_file = output.with_suffix(".watermark.txt")
    text_file.write_text(str(text or "").strip() or "高光剪辑", encoding="utf-8")
    font = subtitle_font_file().replace("\\", "\\\\").replace(":", "\\:")
    drawtext = (
        f"drawtext=fontfile={font}:textfile={text_file.resolve()}:"
        f"fontcolor=white:fontsize={font_size}:"
        "x=28:y=28:box=1:boxcolor=black@0.56:boxborderw=12"
    )
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vf",
            drawtext,
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
            str(output),
        ],
        log_file=log_file,
    )
    return output


def _styled_subtitle_filter(source: Path, subtitle: Path, *, style_size: tuple[int, int] | None = None) -> str:
    if subtitle.suffix.lower() == ".ass":
        return ffmpeg_ass_filter(subtitle)
    width, height = style_size or ffprobe_video_size(source)
    ass_path = subtitle.with_suffix(".ass")
    write_ass_from_srt(
        subtitle,
        ass_path,
        width=width,
        height=height,
        preset=os.environ.get("LOGICCUT_SUBTITLE_STYLE", "captioner"),
        font_name=subtitle_font_name(),
        position=os.environ.get("LOGICCUT_SUBTITLE_POSITION", "bottom"),
    )
    return ffmpeg_ass_filter(ass_path)


def subtitle_font_name() -> str:
    family = _fontconfig_match("%{family}", "family")
    return family or "DejaVu Sans"


def subtitle_font_file() -> str:
    path = _fontconfig_match("%{file}", "file")
    if path:
        return path
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _fontconfig_match(format_value: str, fallback_kind: str) -> str:
    candidates = (
        "Source Han Sans CN",
        "Noto Sans CJK SC",
        "WenQuanYi Zen Hei",
        "Droid Sans Fallback",
        "DejaVu Sans",
    )
    try:
        proc = subprocess.run(
            ["fc-match", "-f", format_value, ",".join(candidates)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        value = proc.stdout.strip().split(",")[0]
        if value:
            return value
    except Exception:
        pass
    if fallback_kind == "family":
        return "DejaVu Sans"
    return ""


def render_text_card(
    output: Path,
    text: str,
    *,
    duration: float = 3.0,
    size: tuple[int, int] = (1280, 720),
    log_file: Path | None = None,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = size
    text_file = output.with_suffix(".txt")
    wrapped = "\n".join(textwrap.wrap(str(text).strip() or "LogicCut", width=42, max_lines=6))
    text_file.write_text(wrapped, encoding="utf-8")
    font = subtitle_font_file().replace("\\", "\\\\").replace(":", "\\:")
    drawtext = (
        f"drawtext=fontfile={font}:textfile={text_file.resolve()}:"
        "fontcolor=white:fontsize=42:line_spacing=12:"
        "x=(w-text_w)/2:y=(h-text_h)/2:"
        "box=1:boxcolor=black@0.48:boxborderw=28"
    )
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=#18212f:s={width}x{height}:r=30",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t",
            f"{duration:.3f}",
            "-vf",
            drawtext,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ],
        log_file=log_file,
    )
    return output


def write_srt(path: Path, segments: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.append(str(index))
        lines.append(f"{_srt_time(float(segment['start']))} --> {_srt_time(float(segment['end']))}")
        lines.append(str(segment["text"]))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"
