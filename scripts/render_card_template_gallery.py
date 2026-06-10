#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logiccut.card_templates import CardTemplate
from logiccut.html_cards import HighlightCard, list_card_templates, render_card_html
from logiccut.media import subtitle_font_file


ASPECT_SIZES = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
}


def build_gallery_html(
    items: list[dict[str, str]],
    *,
    title: str = "LogicCut 卡片模板 Gallery",
    description: str = "这些截图由模板 registry 实际渲染生成。横屏模板用于长视频和访谈，高光导览；竖屏模板用于短视频平台的开场钩子。",
) -> str:
    cards = "\n".join(_gallery_item(item) for item in items)
    escaped_title = html.escape(title)
    escaped_description = html.escape(description)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    :root {{
      --ink: #17212b;
      --muted: #607282;
      --line: #d9e2ea;
      --paper: #fff;
      --soft: #f5f7fa;
      --blue: #1f64b5;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--soft);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "Microsoft YaHei", sans-serif;
    }}
    main {{
      width: min(1320px, calc(100% - 40px));
      margin: 0 auto;
      padding: 42px 0 70px;
    }}
    header {{
      display: grid;
      gap: 12px;
      margin-bottom: 26px;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(34px, 4vw, 58px);
      line-height: 1.04;
      letter-spacing: 0;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.65;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }}
    article {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--paper);
      overflow: hidden;
    }}
    .preview {{
      display: grid;
      place-items: center;
      min-height: 300px;
      padding: 14px;
      background: #eaf0f4;
    }}
    .preview img {{
      display: block;
      max-width: 100%;
      max-height: 620px;
      border-radius: 7px;
      box-shadow: 0 16px 42px rgba(29, 48, 65, 0.18);
      object-fit: contain;
    }}
    .meta {{
      display: grid;
      gap: 7px;
      padding: 15px 17px 17px;
      border-top: 1px solid var(--line);
    }}
    .meta h2 {{
      margin: 0;
      font-size: 20px;
      line-height: 1.25;
    }}
    .id {{
      display: inline-flex;
      width: fit-content;
      padding: 3px 8px;
      border-radius: 999px;
      background: #edf3fb;
      color: var(--blue);
      font-size: 12px;
      font-weight: 850;
    }}
    .tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      margin-top: 3px;
    }}
    .tag {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 8px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #fbfcfd;
      color: #445767;
      font-size: 12px;
      font-weight: 760;
    }}
    .links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 4px;
      font-size: 13px;
      font-weight: 780;
    }}
    @media (max-width: 860px) {{
      .grid {{ grid-template-columns: 1fr; }}
      main {{ width: min(100% - 24px, 720px); padding-top: 26px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{escaped_title}</h1>
      <p>{escaped_description}</p>
    </header>
    <section class="grid">
{cards}
    </section>
  </main>
</body>
</html>
"""


def build_gallery_records(
    output_dir: Path | None = None,
    *,
    render: bool = True,
    template_pack: str | None = None,
) -> list[dict[str, str]]:
    output_dir = output_dir or Path("output/template-gallery")
    if render:
        output_dir.mkdir(parents=True, exist_ok=True)
    card = _sample_card()
    records: list[dict[str, str]] = []
    for template in list_card_templates():
        if template_pack and template.template_pack != template_pack:
            continue
        for aspect in template.aspect_ratios:
            size = ASPECT_SIZES.get(aspect, ASPECT_SIZES["16:9"])
            suffix = "portrait" if aspect == "9:16" else "landscape"
            html_name = f"{template.id}-{suffix}.html"
            image_name = f"{template.id}-{suffix}.png"
            record = {
                "id": template.id,
                "name": template.name,
                "description": template.description,
                "image": image_name,
                "html": html_name,
                "aspect": aspect,
                "template_pack": template.template_pack,
                "source_type": template.source_type,
                "origin_repo": template.origin_repo,
                "origin_license": template.origin_license,
                "adaptation_notes": template.adaptation_notes,
            }
            if render:
                html_path = output_dir / html_name
                image_path = output_dir / image_name
                html_path.write_text(render_card_html(card, poster_name="", size=size, template_id=template.id), encoding="utf-8")
                _render_preview_image(html_path, image_path, size=size, card=card, template=template, aspect=aspect)
            records.append(record)
    return records


def render_gallery(
    output_dir: Path,
    *,
    template_pack: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> Path:
    samples = build_gallery_records(output_dir, render=True, template_pack=template_pack)
    index_path = output_dir / "index.html"
    default_title = "LogicCut 卡片模板 Gallery"
    if template_pack:
        default_title = f"LogicCut {template_pack} 模板 Gallery"
    default_description = "这些截图由模板 registry 实际渲染生成。横屏模板用于长视频和访谈，高光导览；竖屏模板用于短视频平台的开场钩子。"
    if template_pack == "tech-news-neon":
        default_description = "科技新闻霓虹模板包：模仿科技资讯短视频的深色电路背景、紫蓝标题条、强冲突中文标题、视频主体和高亮字幕。"
    index_path.write_text(
        build_gallery_html(
            samples,
            title=title or default_title,
            description=description or default_description,
        ),
        encoding="utf-8",
    )
    return index_path


def _gallery_item(item: dict[str, str]) -> str:
    return f"""      <article>
        <div class="preview"><a href="{html.escape(item.get("html", "#"))}"><img src="{html.escape(item["image"])}" alt="{html.escape(item["name"])}"></a></div>
        <div class="meta">
          <span class="id">{html.escape(item["id"])} · {html.escape(item["aspect"])}</span>
          <h2>{html.escape(item["name"])}</h2>
          <p>{html.escape(item["description"])}</p>
          <div class="tags">
            <span class="tag">pack: {html.escape(item.get("template_pack", "logiccut-native"))}</span>
            <span class="tag">source: {html.escape(item.get("source_type", "native"))}</span>
            <span class="tag">license: {html.escape(item.get("origin_license", "project"))}</span>
          </div>
          <p>{html.escape(item.get("adaptation_notes", ""))}</p>
          <div class="links">
            <a href="{html.escape(item.get("html", "#"))}">打开 HTML</a>
            <span>{html.escape(item.get("origin_repo", ""))}</span>
          </div>
        </div>
      </article>"""


def _sample_card() -> HighlightCard:
    return HighlightCard(
        index=1,
        title="AI 创作工具如何改变视频二创工作流",
        hook="先用语义切出高光，再用章节卡片解释为什么值得看。",
        reason="这一段把工具定位、剪辑逻辑和用户收益压缩到一个可理解的开场，适合放在视频最前面做概括。",
        score=91,
        start=12.3,
        end=28.7,
        keywords=("语义高光", "章节卡片", "二创", "简体中文"),
    )


def _render_preview_image(
    html_path: Path,
    image_path: Path,
    *,
    size: tuple[int, int],
    card: HighlightCard,
    template: CardTemplate,
    aspect: str,
) -> None:
    script = Path(__file__).resolve().parent / "render_html_card.cjs"
    proc = subprocess.run(
        [
            "node",
            str(script),
            str(html_path.resolve()),
            str(image_path.resolve()),
            str(size[0]),
            str(size[1]),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.returncode == 0 and image_path.exists() and image_path.stat().st_size > 0:
        return
    _paint_fallback_preview(image_path, size=size, card=card, template=template, aspect=aspect)


def _paint_fallback_preview(
    output: Path,
    *,
    size: tuple[int, int],
    card: HighlightCard,
    template: CardTemplate,
    aspect: str,
) -> None:
    width, height = size
    palette = _palette(template.template_pack)
    image = Image.new("RGB", size, palette["bg"])
    draw = ImageDraw.Draw(image)
    font_path = subtitle_font_file()
    title_font = _font(font_path, max(34, min(width, height) // 17))
    body_font = _font(font_path, max(22, min(width, height) // 28))
    small_font = _font(font_path, max(15, min(width, height) // 42))
    margin = max(28, min(width, height) // 18)
    draw.rounded_rectangle((margin, margin, width - margin, height - margin), radius=18, fill=palette["paper"], outline=palette["line"], width=3)
    draw.rounded_rectangle((margin, margin, width - margin, margin + max(64, height // 10)), radius=18, fill=palette["accent"])
    draw.text((margin + 24, margin + 20), f"{template.name} · {aspect}", fill=(255, 255, 255), font=small_font)
    title_y = margin + max(96, height // 8)
    _draw_wrapped(draw, card.title, (margin + 28, title_y), title_font, palette["ink"], width - margin * 2 - 56, max_lines=3)
    body_y = title_y + max(128, height // 6)
    draw.rounded_rectangle((margin + 28, body_y, width - margin - 28, min(height - margin - 96, body_y + height // 4)), radius=12, fill=palette["soft"])
    _draw_wrapped(draw, card.reason, (margin + 52, body_y + 24), body_font, palette["muted"], width - margin * 2 - 104, max_lines=4)
    footer_y = height - margin - 62
    draw.text((margin + 28, footer_y), f"pack: {template.template_pack}", fill=palette["muted"], font=small_font)
    draw.text((margin + 28, footer_y + 28), "浏览器不可用时的静态预览图，HTML 模板仍已生成。", fill=palette["muted"], font=small_font)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, quality=92)


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
        y += int(getattr(font, "size", 24) * 1.35)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _palette(pack: str) -> dict[str, tuple[int, int, int]]:
    palettes = {
        "creator-news": {"bg": (230, 238, 243), "paper": (255, 255, 255), "soft": (241, 246, 249), "line": (202, 214, 224), "accent": (31, 100, 181), "ink": (23, 33, 43), "muted": (86, 104, 118)},
        "data-story": {"bg": (234, 244, 241), "paper": (255, 255, 255), "soft": (236, 248, 246), "line": (198, 219, 214), "accent": (13, 122, 125), "ink": (23, 33, 43), "muted": (83, 105, 111)},
        "podcast-quote": {"bg": (241, 238, 248), "paper": (255, 255, 255), "soft": (247, 244, 253), "line": (214, 207, 230), "accent": (101, 86, 164), "ink": (23, 33, 43), "muted": (92, 82, 122)},
        "course-explainer": {"bg": (245, 240, 231), "paper": (255, 255, 255), "soft": (255, 248, 235), "line": (226, 211, 185), "accent": (154, 104, 23), "ink": (23, 33, 43), "muted": (104, 89, 62)},
        "shorts-hook": {"bg": (235, 241, 248), "paper": (255, 255, 255), "soft": (237, 245, 251), "line": (202, 216, 229), "accent": (173, 81, 70), "ink": (23, 33, 43), "muted": (98, 83, 88)},
        "tech-news-neon": {"bg": (4, 6, 16), "paper": (9, 14, 34), "soft": (13, 20, 45), "line": (35, 217, 255), "accent": (35, 217, 255), "ink": (247, 251, 255), "muted": (169, 185, 216)},
    }
    return palettes.get(pack, palettes["creator-news"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render LogicCut card template gallery")
    parser.add_argument("--output-dir", type=Path, default=Path("output/template-gallery"))
    parser.add_argument("--template-pack", help="Only render templates from this template_pack")
    parser.add_argument("--title", help="Gallery page title")
    parser.add_argument("--description", help="Gallery page description")
    args = parser.parse_args(argv)
    index_path = render_gallery(
        args.output_dir,
        template_pack=args.template_pack,
        title=args.title,
        description=args.description,
    )
    print(index_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
