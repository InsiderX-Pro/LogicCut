from __future__ import annotations

import html
import math
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .card_templates import CardTemplate, list_card_templates as _list_card_templates, render_template_html
from .media import run_command, subtitle_font_file
from .text_normalize import normalize_display_text


@dataclass(frozen=True)
class HighlightCard:
    index: int
    title: str
    reason: str
    hook: str
    score: int | None
    start: float
    end: float
    keywords: tuple[str, ...]


def build_highlight_card(item: dict[str, Any], *, index: int) -> HighlightCard:
    title = normalize_display_text(item.get("title") or f"高光 {index}")
    reason = normalize_display_text(item.get("virality_reason") or item.get("hook_sentence") or "")
    raw_hook = normalize_display_text(item.get("hook_sentence") or "")
    hook = raw_hook if _contains_cjk(raw_hook) else _hook_from_reason(reason)
    score_raw = item.get("score")
    score = int(score_raw) if isinstance(score_raw, (int, float)) else None
    start = float(item["start_time"])
    end = float(item["end_time"])
    return HighlightCard(
        index=index,
        title=title,
        reason=reason,
        hook=hook,
        score=score,
        start=start,
        end=end,
        keywords=_keywords(title, reason),
    )


def render_html_card_video(
    *,
    card: HighlightCard,
    source_video: Path,
    output_html: Path,
    output_image: Path,
    output_video: Path,
    duration: float,
    size: tuple[int, int] = (1920, 1080),
    template_id: str | None = None,
    log_file: Path | None = None,
) -> Path:
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_image.parent.mkdir(parents=True, exist_ok=True)
    output_video.parent.mkdir(parents=True, exist_ok=True)
    poster = output_image.with_suffix(".poster.jpg")
    _extract_poster(source_video, poster, card.start, log_file)
    output_html.write_text(render_card_html(card, poster.name, size=size, template_id=template_id), encoding="utf-8")
    if not _render_html_snapshot(output_html, output_image, size=size, log_file=log_file):
        _paint_card(card, poster, output_image, size=size)
    _image_to_video(output_image, output_video, duration=duration, log_file=log_file)
    return output_video


def render_intro_html_card_video(
    *,
    output_html: Path,
    output_image: Path,
    output_video: Path,
    duration: float,
    size: tuple[int, int] = (1920, 1080),
    template_id: str | None = None,
    log_file: Path | None = None,
) -> Path:
    card = HighlightCard(
        index=0,
        title="LogicCut 个性化高光剪辑",
        reason="每个片段先由 Codex 生成一张独立 HTML 小网页，用可视化方式解释为什么选这一段，再进入带中文字幕的配音片段。",
        hook="从“翻译搬运”升级为“有结构、有理由、有包装”的二创视频。",
        score=None,
        start=0,
        end=0,
        keywords=("HTML 场景", "语义剪辑", "个性化包装"),
    )
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_image.parent.mkdir(parents=True, exist_ok=True)
    output_video.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(render_card_html(card, "", size=size, template_id=template_id), encoding="utf-8")
    if not _render_html_snapshot(output_html, output_image, size=size, log_file=log_file):
        _paint_card(card, None, output_image, size=size, intro=True)
    _image_to_video(output_image, output_video, duration=duration, log_file=log_file)
    return output_video


def list_card_templates() -> list[CardTemplate]:
    return _list_card_templates()


def render_card_html(
    card: HighlightCard,
    poster_name: str,
    *,
    size: tuple[int, int] = (1920, 1080),
    template_id: str | None = None,
) -> str:
    keywords_html = "\n".join(f"<span>{html.escape(item)}</span>" for item in card.keywords)
    score_number = str(card.score) if card.score is not None else "--"
    score_html = (
        f"<div class=\"score\"><div><strong>{score_number}</strong><span>score</span></div></div>"
        if card.score is not None
        else ""
    )
    poster_html = (
        f"<img class=\"source-frame\" src=\"{html.escape(poster_name)}\" alt=\"source frame\" "
        "onerror=\"this.hidden=true;this.nextElementSibling.hidden=false\" />"
        + _workflow_html(hidden=True)
        if poster_name
        else _workflow_html()
    )
    label = "LOGICCUT CREATOR CARD" if card.index == 0 else f"SEMANTIC HIGHLIGHT {card.index:02}"
    hook = _truncate(card.hook, 72) if card.hook else "用网页式信息卡，把观众带入片段语境。"
    reason = _truncate(card.reason, 118) if card.reason else hook
    structure = "卡片先建立语境，旁白解释选择理由，随后进入高光片段。" if card.index else "翻译、剪辑和包装在同一条创作链路里完成。"
    width, height = size
    progress = min(88, 28 + max(0, card.index) * 13)
    values = {
        "width": width,
        "height": height,
        "title": html.escape(card.title),
        "hook": html.escape(hook),
        "reason": html.escape(reason),
        "label": html.escape(label),
        "time_label": html.escape(_time_range(card.start, card.end) if card.index else "Creator remix opening"),
        "structure": html.escape(structure),
        "keywords_html": keywords_html,
        "score_html": score_html,
        "score_number": html.escape(score_number),
        "poster_html": poster_html,
        "progress": progress,
        "timeline_items_html": _timeline_items_html(card),
    }
    return render_template_html(template_id or os.environ.get("LOGICCUT_CARD_TEMPLATE") or "news-hook", values)


def _workflow_html(*, hidden: bool = False) -> str:
    attr = " hidden" if hidden else ""
    return (
        f"<div class=\"workflow\"{attr}>"
        "<b><span>Translate</span><small>翻译</small></b>"
        "<b><span>Clip</span><small>切片</small></b>"
        "<b><span>Remix</span><small>重组</small></b>"
        "<b><span>Publish</span><small>发布</small></b>"
        "</div>"
    )


def _render_html_snapshot(
    html_path: Path,
    output_image: Path,
    *,
    size: tuple[int, int],
    log_file: Path | None = None,
) -> bool:
    script = Path(__file__).resolve().parents[1] / "scripts" / "render_html_card.cjs"
    if not script.exists():
        return False
    output_image.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/workspace/.cache/ms-playwright")
    cmd = [
        "node",
        str(script),
        str(html_path.resolve()),
        str(output_image.resolve()),
        str(size[0]),
        str(size[1]),
    ]
    try:
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write("$ " + " ".join(cmd) + "\n")
                proc = subprocess.run(cmd, stdout=handle, stderr=subprocess.STDOUT, text=True, env=env)
        else:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    except OSError:
        return False
    return proc.returncode == 0 and output_image.exists() and output_image.stat().st_size > 0


def _extract_poster(source_video: Path, output: Path, start: float, log_file: Path | None) -> None:
    if output.exists() and output.stat().st_size > 0:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{max(start, 0.0):.3f}",
            "-i",
            str(source_video),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(output),
        ],
        log_file=log_file,
    )


def _image_to_video(image: Path, output: Path, *, duration: float, log_file: Path | None) -> None:
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(image),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
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
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ],
        log_file=log_file,
    )


def _paint_card(
    card: HighlightCard,
    poster: Path | None,
    output: Path,
    *,
    size: tuple[int, int],
    intro: bool = False,
) -> None:
    width, height = size
    font_path = subtitle_font_file()
    bold_path = font_path.replace("Regular", "Bold") if "Regular" in font_path else font_path

    if poster and poster.exists():
        base = Image.open(poster).convert("RGB").resize(size, Image.Resampling.LANCZOS)
        background = base.filter(ImageFilter.GaussianBlur(12))
        canvas = Image.alpha_composite(
            background.convert("RGBA"),
            Image.new("RGBA", size, (10, 15, 20, 184)),
        )
        poster_img = _crop_cover(base, (710, 400))
    else:
        canvas = Image.new("RGBA", size, (245, 247, 249, 255))
        poster_img = None
    draw = ImageDraw.Draw(canvas)

    if intro:
        canvas = Image.alpha_composite(canvas, _vertical_gradient(size, (248, 251, 252, 255), (213, 226, 232, 255)))
    else:
        canvas = Image.alpha_composite(canvas, _vertical_gradient(size, (255, 255, 255, 22), (6, 10, 16, 152)))
    draw = ImageDraw.Draw(canvas)

    for x in range(-220, width, 170):
        draw.line([(x, -40), (x + 620, height + 40)], fill=(255, 255, 255, 18), width=2)
    draw.rectangle((0, height - 160, width, height), fill=(8, 13, 19, 90 if not intro else 20))
    draw.rectangle((92, 76, width - 92, height - 76), outline=(255, 255, 255, 68 if not intro else 120), width=2)

    font_label = _font(bold_path, 26)
    font_kicker = _font(font_path, 25)
    font_body = _font(font_path, 34)
    font_body_small = _font(font_path, 28)
    font_score = _font(bold_path, 58)
    font_chip = _font(font_path, 24)
    font_footer = _font(font_path, 24)

    left = 132
    top = 118
    content_w = 805
    visual_left = 1034
    accent = (28, 88, 153, 255)
    warm = (209, 73, 62, 255)
    paper = (247, 249, 250, 244)
    dark = (21, 29, 37, 255)
    muted = (91, 105, 119, 255)
    line = (213, 222, 230, 255)
    white = (255, 255, 255, 255)

    draw.rounded_rectangle((left, top, left + 365, top + 48), radius=8, fill=(255, 255, 255, 230))
    label = "LOGICCUT CREATOR CARD" if intro else f"SEMANTIC HIGHLIGHT {card.index:02}"
    draw.text((left + 20, top + 9), label, font=font_label, fill=accent)
    if card.score is not None:
        draw.rounded_rectangle((visual_left + 560, top, visual_left + 710, top + 92), radius=8, fill=(209, 73, 62, 245))
        score_cx = visual_left + 635
        draw.text((score_cx, top + 38), str(card.score), font=font_score, fill=white, anchor="mm")
        draw.text((score_cx, top + 72), "score", font=font_kicker, fill=(255, 230, 228, 255), anchor="mm")

    title_font, title_lines = _fit_wrapped_lines(
        card.title,
        bold_path,
        start_size=68,
        min_size=48,
        max_width=content_w,
        max_lines=3,
    )
    title_y = top + 88
    _draw_lines(draw, title_lines, left, title_y, title_font, white if not intro else dark, 12)
    after_title_y = title_y + len(title_lines) * (title_font.size + 12) + 28

    time_label = _time_range(card.start, card.end) if not intro else "Creator remix opening"
    draw.text((left, after_title_y), time_label, font=font_kicker, fill=(214, 224, 231, 255) if not intro else muted)
    _timeline(draw, left, after_title_y + 46, content_w, card.index, warm)

    reason_y = after_title_y + 102
    reason_h = 258 if not intro else 286
    draw.rounded_rectangle((left, reason_y, left + content_w, reason_y + reason_h), radius=8, fill=paper, outline=line, width=2)
    draw.rectangle((left, reason_y, left + 8, reason_y + reason_h), fill=warm)
    draw.text((left + 30, reason_y + 25), "为什么剪这一段", font=font_label, fill=warm)
    reason_lines = _wrap_pixels(card.reason, font_body, content_w - 72, max_lines=4)
    _draw_lines(draw, reason_lines, left + 30, reason_y + 78, font_body, dark, 10)

    hook = card.hook if card.hook else "用网页式信息卡，把观众带入片段语境。"
    hook_y = reason_y + reason_h + 28
    draw.text((left, hook_y), "观众入口", font=font_label, fill=(235, 242, 247, 255) if not intro else accent)
    hook_lines = _wrap_pixels(hook, font_body_small, content_w, max_lines=2)
    _draw_lines(draw, hook_lines, left, hook_y + 44, font_body_small, (229, 236, 241, 255) if not intro else muted, 8)

    if poster_img is not None:
        draw.rounded_rectangle((visual_left - 18, 244, visual_left + 728, 678), radius=8, fill=(255, 255, 255, 210))
        canvas.alpha_composite(_rounded_image(poster_img, 8), (visual_left, 262))
        draw.text((visual_left, 692), "source frame", font=font_kicker, fill=(221, 229, 235, 255))
    else:
        draw.rounded_rectangle((visual_left - 18, 244, visual_left + 728, 678), radius=8, fill=(255, 255, 255, 226), outline=line, width=2)
        workflow = (("Translate", "翻译"), ("Clip", "切片"), ("Remix", "重组"), ("Publish", "发布"))
        for i, (word, zh) in enumerate(workflow):
            x = visual_left + 36 + (i % 2) * 348
            yy = 292 + (i // 2) * 174
            draw.rounded_rectangle((x, yy, x + 298, yy + 116), radius=8, fill=(29, 48, 67, 255))
            draw.text((x + 28, yy + 22), word, font=_font(bold_path, 34), fill=white)
            draw.text((x + 28, yy + 70), zh, font=font_body_small, fill=(190, 213, 230, 255))

    panel_y = 720
    draw.rounded_rectangle((visual_left, panel_y, visual_left + 710, panel_y + 160), radius=8, fill=(255, 255, 255, 232), outline=line, width=2)
    draw.text((visual_left + 28, panel_y + 24), "剪辑结构", font=font_label, fill=accent)
    structure = "先解释选择理由，再进入中文字幕片段。" if not intro else "翻译、剪辑和包装在同一条创作链路里完成。"
    _draw_lines(
        draw,
        _wrap_pixels(structure, font_body_small, 642, max_lines=2),
        visual_left + 28,
        panel_y + 70,
        font_body_small,
        dark,
        8,
    )

    chip_x, chip_y = visual_left, 900
    for keyword in card.keywords[:5]:
        chip_w = max(118, int(draw.textlength(keyword, font=font_chip)) + 48)
        if chip_x + chip_w > visual_left + 710:
            chip_x = visual_left
            chip_y += 58
        draw.rounded_rectangle((chip_x, chip_y, chip_x + chip_w, chip_y + 42), radius=8, fill=(255, 255, 255, 222), outline=(202, 215, 225, 255))
        draw.text((chip_x + 24, chip_y + 7), keyword, font=font_chip, fill=accent)
        chip_x += chip_w + 16

    draw.text((left, height - 68), "Codex generated HTML page", font=font_footer, fill=(217, 226, 233, 255) if not intro else muted)
    draw.text((width - 430, height - 68), "LogicCut creator remix", font=font_footer, fill=(217, 226, 233, 255) if not intro else muted)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, quality=95)


def _card_html(card: HighlightCard, poster_name: str, *, size: tuple[int, int]) -> str:
    keywords = "\n".join(f"<span>{html.escape(item)}</span>" for item in card.keywords)
    score = f"<div class=\"score\"><strong>{card.score}</strong><span>score</span></div>" if card.score is not None else ""
    poster = (
        f"<img class=\"source-frame\" src=\"{html.escape(poster_name)}\" alt=\"source frame\" />"
        if poster_name
        else "<div class=\"workflow\"><b><span>Translate</span><small>翻译</small></b><b><span>Clip</span><small>切片</small></b><b><span>Remix</span><small>重组</small></b><b><span>Publish</span><small>发布</small></b></div>"
    )
    label = "LOGICCUT CREATOR CARD" if card.index == 0 else f"SEMANTIC HIGHLIGHT {card.index:02}"
    time_label = _time_range(card.start, card.end) if card.index else "Creator remix opening"
    hook = _truncate(card.hook, 72) if card.hook else "用网页式信息卡，把观众带入片段语境。"
    reason = _truncate(card.reason, 118) if card.reason else hook
    structure = "卡片先建立语境，旁白解释选择理由，随后进入高光片段。" if card.index else "翻译、剪辑和包装在同一条创作链路里完成。"
    width, height = size
    progress = min(88, 28 + max(0, card.index) * 13)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(card.title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ width: 100%; height: 100%; margin: 0; overflow: hidden; }}
    body {{
      font-family: "Noto Sans SC", "Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei", system-ui, sans-serif;
      color: #15212b;
      background: #e7edf2;
    }}
    [data-composition-id="logiccut-chapter-card"] {{
      position: relative;
      width: 100vw;
      height: 100vh;
      overflow: hidden;
      background:
        radial-gradient(circle at 78% 18%, rgba(12, 126, 132, 0.18), transparent 30%),
        radial-gradient(circle at 10% 88%, rgba(219, 91, 71, 0.16), transparent 31%),
        linear-gradient(135deg, #f8fbfd 0%, #edf3f6 48%, #dce7ed 100%);
    }}
    .stage {{
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(360px, 0.78fr);
      gap: clamp(34px, 4.2vw, 84px);
      width: 100%;
      height: 100%;
      padding: clamp(46px, 6vh, 92px) clamp(54px, 6vw, 116px);
    }}
    .copy {{
      min-width: 0;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: clamp(16px, 2.1vh, 30px);
    }}
    .eyebrow {{
      display: inline-flex;
      width: fit-content;
      align-items: center;
      min-height: clamp(28px, 4.4vh, 48px);
      padding: 0 clamp(14px, 1.4vw, 24px);
      border: 1px solid rgba(20, 38, 49, 0.14);
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.78);
      color: #0e7580;
      font-size: clamp(14px, 1.5vw, 24px);
      font-weight: 850;
      letter-spacing: 0;
    }}
    h1 {{
      margin: 0;
      max-width: 11.4em;
      color: #17212b;
      font-size: clamp(38px, 5.25vw, 86px);
      line-height: 1.05;
      letter-spacing: 0;
      text-wrap: balance;
    }}
    .hook {{
      max-width: 34em;
      color: #425564;
      font-size: clamp(20px, 2.15vw, 34px);
      line-height: 1.36;
      font-weight: 650;
    }}
    .reason {{
      position: relative;
      max-width: min(860px, 100%);
      padding: clamp(20px, 2.4vh, 34px) clamp(24px, 2.4vw, 38px);
      border: 1px solid rgba(20, 38, 49, 0.12);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.82);
      box-shadow: 0 18px 55px rgba(35, 55, 69, 0.12);
    }}
    .reason::before {{
      content: "";
      position: absolute;
      left: 0;
      top: 18px;
      bottom: 18px;
      width: 7px;
      border-radius: 0 999px 999px 0;
      background: #df5b4c;
    }}
    .reason b {{
      display: block;
      margin-bottom: clamp(8px, 1vh, 14px);
      color: #df5b4c;
      font-size: clamp(15px, 1.45vw, 24px);
      letter-spacing: 0;
    }}
    .reason span {{
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      color: #263744;
      font-size: clamp(18px, 1.86vw, 30px);
      line-height: 1.42;
    }}
    .meta {{
      display: flex;
      align-items: center;
      gap: clamp(14px, 1.3vw, 22px);
      min-width: 0;
      color: #5b6d7a;
      font-size: clamp(15px, 1.45vw, 23px);
      font-weight: 750;
    }}
    .progress {{
      position: relative;
      flex: 1;
      height: 10px;
      min-width: 160px;
      max-width: 560px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(33, 55, 68, 0.14);
    }}
    .progress span {{
      display: block;
      width: {progress}%;
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, #0e7580, #df5b4c);
    }}
    .media {{
      min-width: 0;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: clamp(14px, 2vh, 26px);
    }}
    .frame-wrap {{
      position: relative;
      aspect-ratio: 16 / 9;
      overflow: hidden;
      border-radius: 8px;
      background: #263744;
      box-shadow: 0 24px 70px rgba(30, 46, 58, 0.26);
    }}
    .source-frame {{
      display: block;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }}
    .workflow {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      width: 100%;
      height: 100%;
      padding: clamp(22px, 2.4vw, 38px);
      background: #263744;
    }}
    .workflow b {{
      display: flex;
      min-width: 0;
      flex-direction: column;
      justify-content: center;
      gap: 8px;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.08);
      padding: clamp(16px, 1.8vw, 28px);
      color: #fff;
      font-size: clamp(20px, 2.1vw, 34px);
    }}
    .workflow small {{
      color: #a9d7d4;
      font-size: clamp(16px, 1.7vw, 26px);
    }}
    .score {{
      position: absolute;
      right: clamp(14px, 1.4vw, 24px);
      top: clamp(14px, 1.4vw, 24px);
      display: grid;
      place-items: center;
      width: clamp(72px, 7vw, 118px);
      height: clamp(72px, 7vw, 118px);
      border-radius: 999px;
      background: #df5b4c;
      color: #fff;
      box-shadow: 0 16px 38px rgba(135, 54, 43, 0.24);
    }}
    .score strong {{
      display: block;
      font-size: clamp(28px, 3.4vw, 54px);
      line-height: 0.9;
    }}
    .score span {{
      display: block;
      color: rgba(255, 255, 255, 0.82);
      font-size: clamp(11px, 1.1vw, 17px);
      text-align: center;
    }}
    .structure {{
      display: grid;
      gap: clamp(8px, 1vh, 14px);
      padding: clamp(18px, 2.1vh, 30px) clamp(20px, 2vw, 32px);
      border: 1px solid rgba(20, 38, 49, 0.12);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.76);
      color: #263744;
    }}
    .structure strong {{
      color: #0e7580;
      font-size: clamp(15px, 1.45vw, 23px);
    }}
    .structure span {{
      font-size: clamp(17px, 1.72vw, 27px);
      line-height: 1.36;
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: clamp(8px, 1vw, 14px);
    }}
    .chips span {{
      max-width: 100%;
      min-height: clamp(28px, 3.8vh, 42px);
      padding: clamp(5px, 0.7vh, 8px) clamp(12px, 1.4vw, 20px);
      border-radius: 999px;
      background: rgba(14, 117, 128, 0.1);
      color: #0b6570;
      font-size: clamp(13px, 1.28vw, 20px);
      font-weight: 780;
    }}
    footer {{
      position: absolute;
      z-index: 2;
      left: clamp(54px, 6vw, 116px);
      right: clamp(54px, 6vw, 116px);
      bottom: clamp(24px, 3.6vh, 46px);
      display: flex;
      justify-content: space-between;
      gap: 20px;
      color: #647684;
      font-size: clamp(12px, 1.18vw, 18px);
      font-weight: 720;
    }}
    @media (max-aspect-ratio: 1/1) {{
      .stage {{
        grid-template-columns: 1fr;
        grid-template-rows: minmax(0, 1fr) auto;
        padding: 72px 62px 96px;
      }}
      h1 {{ font-size: clamp(52px, 9.2vw, 88px); }}
      .hook {{ font-size: clamp(26px, 4.6vw, 40px); }}
      .reason span {{ -webkit-line-clamp: 4; font-size: clamp(24px, 4vw, 34px); }}
      .media {{ justify-content: end; }}
      .frame-wrap {{ max-height: 42vh; }}
    }}
  </style>
</head>
<body>
  <main data-composition-id="logiccut-chapter-card" data-width="{width}" data-height="{height}" class="template-news-hook">
    <section class="stage">
      <article class="copy">
        <span class="eyebrow">{html.escape(label)}</span>
        <h1>{html.escape(card.title)}</h1>
        <div class="hook">{html.escape(hook)}</div>
        <div class="meta"><span>{html.escape(time_label)}</span><div class="progress"><span></span></div></div>
        <article class="reason" aria-label="why this clip">
          <b>为什么剪这一段</b>
          <span>{html.escape(reason)}</span>
        </article>
      </article>
      <aside class="media">
        <div class="frame-wrap">{poster}{score}</div>
        <div class="structure"><strong>剪辑结构</strong><span>{html.escape(structure)}</span></div>
        <div class="chips">{keywords}</div>
      </aside>
    </section>
    <footer><span>HyperFrames-style HTML composition</span><span>LogicCut creator remix</span></footer>
  </main>
</body>
</html>
"""


def _vertical_gradient(size: tuple[int, int], top: tuple[int, int, int, int], bottom: tuple[int, int, int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    steps = 60
    for i in range(steps):
        ratio = i / max(steps - 1, 1)
        color = tuple(int(top[j] * (1 - ratio) + bottom[j] * ratio) for j in range(4))
        y0 = int(height * i / steps)
        y1 = int(height * (i + 1) / steps)
        draw.rectangle((0, y0, width, y1), fill=color)
    return image


def _rounded_image(image: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, image.size[0], image.size[1]), radius=radius, fill=255)
    rounded = Image.new("RGBA", image.size)
    rounded.paste(image.convert("RGBA"), (0, 0), mask)
    return rounded


def _crop_cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    source_w, source_h = image.size
    scale = max(target_w / source_w, target_h / source_h)
    resized = image.resize((int(source_w * scale), int(source_h * scale)), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def _timeline(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, index: int, color: tuple[int, int, int, int]) -> None:
    draw.rounded_rectangle((x, y, x + width, y + 12), radius=6, fill=(216, 226, 220, 255))
    progress = 0.28 + min(max(index, 0), 4) * 0.13
    draw.rounded_rectangle((x, y, x + int(width * progress), y + 12), radius=6, fill=color)
    for tick in range(5):
        tx = x + int(width * tick / 4)
        draw.ellipse((tx - 8, y - 7, tx + 8, y + 19), fill=(250, 252, 247, 255), outline=(170, 190, 186, 255), width=2)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size=size)
    except Exception:
        return ImageFont.load_default()


def _fit_wrapped_lines(
    text: str,
    font_path: str,
    *,
    start_size: int,
    min_size: int,
    max_width: int,
    max_lines: int,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    for size in range(start_size, min_size - 1, -2):
        font = _font(font_path, size)
        lines = _wrap_pixels(text, font, max_width, max_lines=max_lines)
        if len(lines) <= max_lines and not (lines and lines[-1].endswith("...")):
            return font, lines
    font = _font(font_path, min_size)
    return font, _wrap_pixels(text, font, max_width, max_lines=max_lines)


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    line_gap: int,
) -> None:
    for index, line in enumerate(lines):
        draw.text((x, y + index * (font.size + line_gap)), line, font=font, fill=fill)


def _wrap_pixels(text: str, font: ImageFont.FreeTypeFont, max_width: int, *, max_lines: int) -> list[str]:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned:
        return [""]
    tokens = re.findall(r"[A-Za-z0-9.+#-]+|[\u4e00-\u9fff]|[^\u4e00-\u9fffA-Za-z0-9.+#-]", cleaned)
    lines: list[str] = []
    current = ""
    for token in tokens:
        candidate = current + token
        if current and font.getlength(candidate) > max_width:
            lines.append(current.rstrip())
            current = token.lstrip()
            if len(lines) == max_lines:
                break
        else:
            current = candidate
    if len(lines) < max_lines and current.strip():
        lines.append(current.rstrip())
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if tokens and "".join(lines).replace(" ", "") != cleaned.replace(" ", ""):
        if lines:
            while font.getlength(lines[-1] + "...") > max_width and len(lines[-1]) > 1:
                lines[-1] = lines[-1][:-1].rstrip()
            lines[-1] = lines[-1].rstrip() + "..."
    return lines or [""]


def _truncate(text: str, length: int) -> str:
    return text if len(text) <= length else text[: max(0, length - 1)].rstrip() + "..."


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _hook_from_reason(reason: str) -> str:
    clean = normalize_display_text(reason)
    if not clean:
        return ""
    first = re.split(r"[。！？!?；;]", clean, maxsplit=1)[0].strip()
    return first or clean


def _timeline_items_html(card: HighlightCard) -> str:
    items = [
        f"第 {card.index:02} 章进入高光",
        _truncate(card.hook or card.title, 24),
        _truncate(card.reason or "解释剪辑理由", 28),
    ]
    return "\n".join(f"<div><i></i><span>{html.escape(item)}</span></div>" for item in items if item)


def _keywords(*texts: str) -> tuple[str, ...]:
    raw = "".join(texts)
    candidates = re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{2,}|[\u4e00-\u9fff]{2,6}", raw)
    stop = {"这个", "一個", "一个", "就是", "可以", "因为", "這個", "透過", "极具", "引发", "人们", "作者", "剪辑", "理由"}
    seen: list[str] = []
    for item in candidates:
        item = item.strip("，。！？；：,.!?;:")
        if item in stop or len(item) < 2:
            continue
        if item not in seen:
            seen.append(item)
        if len(seen) >= 5:
            break
    return tuple(seen or ("语义高光", "二创包装", "传播钩子"))


def _time_range(start: float, end: float) -> str:
    return f"{_clock(start)} - {_clock(end)} / {max(0.0, end - start):.1f}s"


def _clock(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    secs = int(math.floor(seconds % 60))
    return f"{minutes:02}:{secs:02}"
