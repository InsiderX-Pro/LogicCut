from __future__ import annotations

import html
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .media import ffprobe_duration, run_command, subtitle_font_file
from .text_normalize import normalize_display_text


PORTRAIT_SIZE = (1080, 1920)
VIDEO_TOP = 656


def render_portrait_web_video(
    *,
    source_video: Path,
    output_html: Path,
    output_image: Path,
    output_video: Path,
    title: str,
    hook: str,
    reason: str,
    style_name: str,
    style_tone: str,
    log_file: Path | None = None,
) -> Path:
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_image.parent.mkdir(parents=True, exist_ok=True)
    output_video.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "title": normalize_display_text(title),
        "hook": normalize_display_text(hook),
        "reason": normalize_display_text(reason),
        "style_name": normalize_display_text(style_name),
        "style_tone": normalize_display_text(style_tone),
    }
    output_html.write_text(_portrait_html(data), encoding="utf-8")
    _paint_portrait_background(output_image, data)
    duration = ffprobe_duration(source_video)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(output_image),
            "-i",
            str(source_video),
            "-filter_complex",
            f"[1:v:0]scale=1080:-2,setsar=1[v];[0:v:0][v]overlay=(W-w)/2:{VIDEO_TOP}:shortest=1[outv]",
            "-map",
            "[outv]",
            "-map",
            "1:a:0?",
            "-t",
            f"{duration:.3f}",
            "-r",
            "30",
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
            str(output_video),
        ],
        log_file=log_file,
    )
    return output_video


def _portrait_html(data: dict[str, str]) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(data["title"])}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      width: 1080px;
      height: 1920px;
      overflow: hidden;
      background: #f4f7fa;
      color: #17212b;
      font-family: "Noto Sans SC", "Source Han Sans SC", "Microsoft YaHei", system-ui, sans-serif;
    }}
    .page {{
      width: 100%;
      height: 100%;
      display: grid;
      grid-template-rows: 620px 680px 1fr;
      padding: 44px;
      gap: 18px;
    }}
    .panel {{
      border: 1px solid #d8e1e9;
      border-radius: 22px;
      background: #fff;
      padding: 34px;
      box-shadow: 0 20px 64px rgba(31, 48, 64, 0.12);
    }}
    .eyebrow {{
      display: inline-flex;
      min-height: 40px;
      align-items: center;
      padding: 0 14px;
      border-radius: 999px;
      background: #eaf6f4;
      color: #0d7a7d;
      font-size: 24px;
      font-weight: 850;
    }}
    h1 {{
      margin: 24px 0 0;
      font-size: 68px;
      line-height: 1.06;
      letter-spacing: 0;
    }}
    .video-slot {{
      border-radius: 22px;
      background: #14202b;
      box-shadow: 0 22px 68px rgba(20, 32, 43, 0.22);
    }}
    .hook {{
      font-size: 42px;
      line-height: 1.22;
      font-weight: 900;
    }}
    .reason {{
      margin-top: 20px;
      color: #607283;
      font-size: 30px;
      line-height: 1.42;
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="panel">
      <span class="eyebrow">{html.escape(data["style_name"])} · LogicCut v0.3</span>
      <h1>{html.escape(data["title"])}</h1>
    </section>
    <section class="video-slot"></section>
    <section class="panel">
      <div class="hook">{html.escape(data["hook"])}</div>
      <div class="reason">{html.escape(data["reason"])}<br>{html.escape(data["style_tone"])}</div>
    </section>
  </main>
</body>
</html>
"""


def _paint_portrait_background(output_image: Path, data: dict[str, str]) -> None:
    width, height = PORTRAIT_SIZE
    image = Image.new("RGB", PORTRAIT_SIZE, (244, 247, 250))
    draw = ImageDraw.Draw(image)
    font_path = subtitle_font_file()
    title_font = _font(font_path, 66)
    hook_font = _font(font_path, 42)
    body_font = _font(font_path, 29)
    badge_font = _font(font_path, 24)
    ink = (23, 33, 43)
    muted = (96, 114, 131)
    line = (216, 225, 233)
    teal = (13, 122, 125)
    paper = (255, 255, 255)
    panel_margin = 44
    top_panel = (44, 44, width - 44, 620)
    bottom_panel = (44, 1354, width - 44, height - 44)
    video_box = (44, VIDEO_TOP, width - 44, VIDEO_TOP + 608)
    for box in (top_panel, bottom_panel):
        draw.rounded_rectangle(box, radius=22, fill=paper, outline=line, width=2)
    draw.rounded_rectangle(video_box, radius=22, fill=(20, 32, 43))
    draw.rounded_rectangle((panel_margin + 34, panel_margin + 34, panel_margin + 308, panel_margin + 76), radius=21, fill=(234, 246, 244))
    draw.text((panel_margin + 52, panel_margin + 39), f"{data['style_name']} · v0.3", fill=teal, font=badge_font)
    _draw_wrapped(draw, data["title"], (78, 116), title_font, ink, 924, max_lines=4)
    _draw_wrapped(draw, data["hook"], (78, 1398), hook_font, ink, 924, max_lines=3)
    _draw_wrapped(draw, data["reason"], (78, 1566), body_font, muted, 924, max_lines=4)
    _draw_wrapped(draw, data["style_tone"], (78, 1772), body_font, muted, 924, max_lines=2)
    output_image.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_image, quality=94)


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
    max_width: int,
    *,
    max_lines: int,
) -> None:
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = char
            if len(lines) >= max_lines:
                break
        else:
            current = candidate
    if current and len(lines) < max_lines:
        lines.append(current)
    x, y = xy
    for line in lines:
        draw.text((x, y), line, fill=fill, font=font)
        y += int(getattr(font, "size", 28) * 1.35)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()
