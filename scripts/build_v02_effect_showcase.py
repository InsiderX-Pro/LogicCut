#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logiccut.card_templates import list_card_templates


def build_showcase_html(assets: Mapping[str, str]) -> str:
    template_count = len(list_card_templates())
    status_items = [
        ("模板来源可追溯", f"{template_count} 个模板已写入 pack、origin repo、license 和 adaptation notes。"),
        ("横竖屏模板预览", "gallery 按每个模板的 aspect_ratios 同时输出 16:9 和 9:16。"),
        ("v0.1 章节卡片旁白", "卡片 HTML -> 截图/兜底图 -> 静音卡片视频 -> TTS 旁白 -> 字幕混音。"),
        ("v0.2 导览高光成片", "章节旁白卡片和语义高光片段交替拼接，高光片段支持中文字幕烧录。"),
    ]
    status_html = "\n".join(_status_card(title, text) for title, text in status_items)
    links = {
        key: html.escape(value)
        for key, value in assets.items()
    }
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LogicCut v0.1-v0.2 效果展示</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17212b;
      --muted: #607283;
      --paper: #fff;
      --soft: #f4f7fa;
      --line: #d8e1e9;
      --blue: #1f64b5;
      --teal: #0d7a7d;
      --green: #247248;
      --amber: #9a6817;
      --violet: #6556a4;
      --coal: #26313d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--soft);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "Source Han Sans SC", "Microsoft YaHei", sans-serif;
      line-height: 1.62;
    }}
    a {{ color: var(--blue); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    main {{
      width: min(1240px, calc(100% - 40px));
      margin: 0 auto;
      padding: 34px 0 74px;
    }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(360px, 0.78fr);
      gap: 34px;
      align-items: center;
      min-height: 620px;
      padding: 26px 0 44px;
      border-bottom: 1px solid var(--line);
    }}
    .eyebrow {{
      display: inline-flex;
      width: fit-content;
      min-height: 32px;
      align-items: center;
      padding: 5px 12px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--paper);
      color: var(--muted);
      font-size: 13px;
      font-weight: 760;
    }}
    h1 {{
      margin: 18px 0;
      max-width: 860px;
      font-size: clamp(42px, 5.4vw, 74px);
      line-height: 1.02;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 0;
      font-size: clamp(27px, 3vw, 38px);
      line-height: 1.12;
      letter-spacing: 0;
    }}
    h3 {{
      margin: 0 0 8px;
      font-size: 20px;
      line-height: 1.25;
      letter-spacing: 0;
    }}
    p {{ margin: 0; }}
    .lead {{
      max-width: 820px;
      color: var(--muted);
      font-size: 18px;
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 26px;
    }}
    .chip {{
      display: inline-flex;
      align-items: center;
      min-height: 36px;
      padding: 6px 12px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--paper);
      color: #344858;
      font-size: 13px;
      font-weight: 760;
      white-space: nowrap;
    }}
    .hero-panel {{
      display: grid;
      gap: 13px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--paper);
      padding: 17px;
    }}
    .stage {{
      position: relative;
      overflow: hidden;
      aspect-ratio: 16 / 9;
      min-height: 250px;
      border: 1px solid #cbd7df;
      border-radius: 8px;
      background:
        linear-gradient(135deg, rgba(255,255,255,0.12), rgba(255,255,255,0.02)),
        repeating-linear-gradient(135deg, #28455e 0 18px, #203649 18px 36px);
      color: #fff;
      padding: 20px;
    }}
    .stage-card {{
      position: absolute;
      left: 20px;
      right: 20px;
      bottom: 20px;
      padding: 14px 16px;
      border-left: 5px solid #86d6d1;
      border-radius: 7px;
      background: rgba(13, 22, 33, 0.82);
    }}
    .stage-card strong {{
      display: block;
      font-size: clamp(23px, 3.2vw, 38px);
      line-height: 1.08;
    }}
    .stage-card span {{
      display: block;
      margin-top: 8px;
      color: rgba(255,255,255,0.76);
      font-size: 14px;
    }}
    section {{ margin-top: 58px; }}
    .section-head {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: end;
      margin-bottom: 20px;
    }}
    .section-head p {{
      max-width: 620px;
      color: var(--muted);
    }}
    .status-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 13px;
    }}
    .status, .card, .video-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--paper);
    }}
    .status {{
      min-height: 154px;
      padding: 16px;
    }}
    .status b {{
      display: block;
      margin-bottom: 8px;
      color: var(--teal);
      font-size: 16px;
    }}
    .status p, .card p, .video-card p {{
      color: var(--muted);
    }}
    .video-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }}
    .video-card {{
      overflow: hidden;
    }}
    video {{
      display: block;
      width: 100%;
      aspect-ratio: 16 / 9;
      background: #101820;
    }}
    .video-meta {{
      display: grid;
      gap: 8px;
      padding: 16px 18px 18px;
      border-top: 1px solid var(--line);
    }}
    .tag-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 4px;
    }}
    .tag {{
      display: inline-flex;
      min-height: 25px;
      align-items: center;
      padding: 3px 8px;
      border-radius: 999px;
      background: #edf6f6;
      color: var(--teal);
      font-size: 12px;
      font-weight: 820;
    }}
    .artifact-grid {{
      display: grid;
      grid-template-columns: 1.08fr 0.92fr;
      gap: 18px;
      align-items: stretch;
    }}
    .card {{
      padding: 18px;
    }}
    .card img {{
      display: block;
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #edf3f7;
    }}
    .link-list {{
      display: grid;
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .link-list li {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: center;
      padding: 12px 0;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
    }}
    .link-list li:last-child {{ border-bottom: 0; }}
    .timeline {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    .step {{
      min-height: 154px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--paper);
    }}
    .step span {{
      display: inline-flex;
      width: 30px;
      height: 30px;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      background: var(--coal);
      color: #fff;
      font-size: 13px;
      font-weight: 900;
    }}
    .step strong {{
      display: block;
      margin: 12px 0 8px;
      font-size: 16px;
    }}
    .step p {{
      color: var(--muted);
      font-size: 14px;
    }}
    @media (max-width: 980px) {{
      .hero, .video-grid, .artifact-grid {{ grid-template-columns: 1fr; }}
      .status-grid, .timeline {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 640px) {{
      main {{ width: min(100% - 28px, 1240px); padding-top: 22px; }}
      .hero {{ min-height: auto; padding-top: 12px; }}
      h1 {{ font-size: 42px; }}
      .section-head {{ display: block; }}
      .section-head p {{ margin-top: 10px; }}
      .status-grid, .timeline {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div>
        <div class="eyebrow">LogicCut v0.1-v0.2 implementation showcase</div>
        <h1>v0.2 的目标：让高光剪辑从“拼片段”升级成“有讲解的二创成片”。</h1>
        <p class="lead">这页集中展示当前已实现的 v0.1-v0.2 能力：v0.1 做章节卡片旁白，v0.2 做导览高光成片，并把模板体系按来源、license、横竖屏预览整理成可维护资产。</p>
        <div class="chips">
          <a class="chip" href="#videos">看视频效果</a>
          <a class="chip" href="#templates">看模板矩阵</a>
          <a class="chip" href="#pipeline">看实现链路</a>
        </div>
      </div>
      <div class="hero-panel">
        <div class="stage">
          <div class="stage-card">
            <strong>章节卡片先解释，再进入高光片段。</strong>
            <span>卡片旁白、字幕、高光片段字幕和模板来源都进入 manifest，可被后续 UI 和一键脚本复用。</span>
          </div>
        </div>
      </div>
    </section>

    <section>
      <div class="section-head">
        <h2>当前完成度</h2>
        <p>这部分对应这次 v0.2 完善后的实际工程状态，不是概念图。</p>
      </div>
      <div class="status-grid">
{status_html}
      </div>
    </section>

    <section id="videos">
      <div class="section-head">
        <h2>视频效果</h2>
        <p>v0.1 和 v0.2 都使用同一个 YouTube 参考项目目录下的真实输出，方便直接人工检查。</p>
      </div>
      <div class="video-grid">
        <article class="video-card">
          <video controls preload="metadata" src="{links.get("v01_video", "")}"></video>
          <div class="video-meta">
            <span class="tag">v0.1</span>
            <h3>章节卡片旁白</h3>
            <p>每个高光章节生成 HTML 卡片、旁白 TTS、旁白字幕和混音卡片视频，再串成章节导览。</p>
            <div class="tag-row">
              <span class="tag">HTML card</span>
              <span class="tag">Narration TTS</span>
              <span class="tag">SRT subtitles</span>
            </div>
          </div>
        </article>
        <article class="video-card">
          <video controls preload="metadata" src="{links.get("v02_video", "")}"></video>
          <div class="video-meta">
            <span class="tag">v0.2</span>
            <h3>导览高光成片</h3>
            <p>时间线变成“旁白卡片 -> 带中文字幕的高光片段 -> 下一张旁白卡片”，更接近可发布的二创短片。</p>
            <div class="tag-row">
              <span class="tag">Guided timeline</span>
              <span class="tag">Burned subtitles</span>
              <span class="tag">Template sequence</span>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section id="templates">
      <div class="section-head">
        <h2>模板和单卡验证</h2>
        <p>这里可以看模板矩阵，也可以打开 v0.2 真实生成的一张导览卡片 HTML。</p>
      </div>
      <div class="artifact-grid">
        <article class="card">
          <h3>v0.2 真实导览卡片</h3>
          <p>这张图来自当前项目输出目录，对应同名 HTML、旁白音频和字幕。</p>
          <div style="height: 12px"></div>
          <a href="{links.get("v02_card_html", "#")}"><img src="{links.get("v02_card_image", "")}" alt="v0.2 guided card"></a>
        </article>
        <article class="card">
          <h3>可检查文件</h3>
          <ul class="link-list">
            <li><span>模板 Gallery</span><a href="{links.get("template_gallery", "#")}">打开</a></li>
            <li><span>模板调研页</span><a href="{links.get("template_research", "#")}">打开</a></li>
            <li><span>单张卡片 HTML</span><a href="{links.get("v02_card_html", "#")}">打开</a></li>
            <li><span>旁白字幕 SRT</span><a href="{links.get("v02_subtitle", "#")}">打开</a></li>
            <li><span>项目 Manifest</span><a href="{links.get("v02_manifest", "#")}">打开</a></li>
          </ul>
        </article>
      </div>
    </section>

    <section id="pipeline">
      <div class="section-head">
        <h2>v0.1 到 v0.2 的实现链路</h2>
        <p>后续 v0.3 可以在这条链路上继续扩展更精美的模板包和更稳定的 TTS 声音。</p>
      </div>
      <div class="timeline">
        <div class="step"><span>1</span><strong>语义高光</strong><p>读取转写和语义分析，拿到高光片段、标题、分数、剪辑理由和翻译字幕。</p></div>
        <div class="step"><span>2</span><strong>章节卡片</strong><p>模板 registry 渲染 HTML 卡片，manifest 记录模板包、来源和适配说明。</p></div>
        <div class="step"><span>3</span><strong>旁白字幕</strong><p>为卡片生成 TTS 旁白和随时间变化的 SRT，字幕强制简体化并按中文断句。</p></div>
        <div class="step"><span>4</span><strong>导览成片</strong><p>把旁白卡片和高光片段交替拼接，高光片段可烧录中文字幕。</p></div>
      </div>
    </section>
  </main>
</body>
</html>
"""


def build_asset_map(*, output_dir: Path, repo_root: Path, project_dir: Path, gallery_dir: Path) -> dict[str, str]:
    return {
        "template_gallery": _rel(output_dir, gallery_dir / "index.html"),
        "template_research": _rel(output_dir, repo_root / "docs" / "template-reuse-research.html"),
        "v01_video": _rel(output_dir, project_dir / "renders" / "chapter_card_narration" / "chapter_card_narration.mp4"),
        "v02_video": _rel(output_dir, project_dir / "renders" / "guided_highlights" / "guided_highlights.mp4"),
        "v02_card_html": _rel(output_dir, project_dir / "assets" / "guided_highlights" / "guided_card_01.html"),
        "v02_card_image": _rel(output_dir, project_dir / "assets" / "guided_highlights" / "guided_card_01.png"),
        "v02_subtitle": _rel(output_dir, project_dir / "assets" / "guided_highlights" / "guided_card_01_narration.srt"),
        "v02_manifest": _rel(output_dir, project_dir / "project.json"),
    }


def write_showcase(output_dir: Path, *, repo_root: Path, project_dir: Path, gallery_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = build_asset_map(output_dir=output_dir, repo_root=repo_root, project_dir=project_dir, gallery_dir=gallery_dir)
    index_path = output_dir / "index.html"
    index_path.write_text(build_showcase_html(assets), encoding="utf-8")
    return index_path


def _status_card(title: str, text: str) -> str:
    return f"""        <article class="status">
          <b>{html.escape(title)}</b>
          <p>{html.escape(text)}</p>
        </article>"""


def _rel(base: Path, target: Path) -> str:
    return os.path.relpath(target.resolve(), base.resolve())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build LogicCut v0.1-v0.2 effect showcase page")
    parser.add_argument("--output-dir", type=Path, default=Path("output/v02-effect-showcase"))
    parser.add_argument("--project-dir", type=Path, default=Path("output/youtube-karpathy-zh/project"))
    parser.add_argument("--gallery-dir", type=Path, default=Path("output/template-gallery"))
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    index_path = write_showcase(
        args.output_dir,
        repo_root=args.repo_root,
        project_dir=args.project_dir,
        gallery_dir=args.gallery_dir,
    )
    print(index_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
