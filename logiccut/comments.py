from __future__ import annotations

import html
import json
import re
import subprocess
import time
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chapter_narration import (
    mix_card_with_narration,
    safe_audio_duration,
    synthesize_narration_audio,
    write_narration_srt,
)
from .media import concat_videos_reencode, run_command, subtitle_font_file
from .text_normalize import normalize_display_text


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


def scrape_comments(
    url: str,
    output_dir: Path,
    *,
    platform: str = "auto",
    max_comments: int = 50,
    cookies: Path | None = None,
    download_images: bool = True,
    capture_screenshots: bool = True,
    screenshot_count: int = 4,
    viewport_width: int = 1280,
    viewport_height: int = 720,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_platform = detect_comment_platform(url) if platform == "auto" else platform
    if resolved_platform == "youtube":
        payload = scrape_youtube_comments(url, max_comments=max_comments, cookies=cookies)
    elif resolved_platform == "bilibili":
        payload = scrape_bilibili_comments(url, max_comments=max_comments)
    else:
        raise ValueError(f"Unsupported comment platform: {platform}")

    comments = payload.get("comments", [])
    if download_images:
        images = download_comment_images(comments, output_dir / "images")
    else:
        images = collect_comment_images(comments)

    screenshot_manifest: dict[str, Any] = {"status": "skipped", "screenshots": []}
    if capture_screenshots:
        try:
            screenshot_manifest = capture_comment_screenshots(
                url,
                output_dir,
                platform=resolved_platform,
                count=screenshot_count,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                cookies=cookies,
            )
        except RuntimeError as exc:
            screenshot_manifest = {
                "schema_version": "logiccut.comment_screenshots.v1",
                "status": "failed",
                "error": str(exc),
                "screenshots": [],
            }
            (output_dir / "comment_screenshots.json").write_text(
                json.dumps(screenshot_manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    screenshots = screenshot_manifest.get("screenshots") or []
    visual_items = screenshot_manifest.get("visual_items") or []
    visual_items_path = output_dir / "comment_visual_items.json"
    visual_items_path.write_text(json.dumps(visual_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {
        "schema_version": "logiccut.comments.v1",
        "platform": resolved_platform,
        "url": url,
        "video_id": payload.get("video_id", ""),
        "title": payload.get("title", ""),
        "comment_count": len(comments),
        "image_count": len(images),
        "screenshot_count": len(screenshots),
        "visual_item_count": len(visual_items),
        "comments": comments,
        "images": images,
        "comment_screenshots": screenshots,
        "comment_visual_items": visual_items,
        "comment_visual_items_path": str(visual_items_path),
        "comment_screenshot_manifest": screenshot_manifest,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": payload.get("source", {}),
    }
    comments_path = output_dir / "comments.json"
    comments_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path = write_comments_report(output_dir, result)
    result["comments_path"] = str(comments_path)
    result["report_path"] = str(report_path)
    return result


def capture_comment_screenshots(
    url: str,
    output_dir: Path,
    *,
    platform: str,
    count: int,
    viewport_width: int,
    viewport_height: int,
    cookies: Path | None = None,
) -> dict[str, Any]:
    cmd = build_comment_screenshot_command(
        url,
        output_dir,
        platform=platform,
        count=count,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        cookies=cookies,
    )
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"comment screenshot capture failed ({proc.returncode}): {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"comment screenshot capture returned invalid JSON: {proc.stdout[:500]}") from exc


def build_comment_screenshot_command(
    url: str,
    output_dir: Path,
    *,
    platform: str,
    count: int,
    viewport_width: int,
    viewport_height: int,
    cookies: Path | None = None,
) -> list[str]:
    script = Path(__file__).resolve().parents[1] / "scripts" / "capture_comment_screenshots.cjs"
    cmd = [
        "node",
        str(script),
        "--url",
        url,
        "--output-dir",
        str(output_dir),
        "--platform",
        platform,
        "--count",
        str(max(1, count)),
        "--viewport-width",
        str(viewport_width),
        "--viewport-height",
        str(viewport_height),
    ]
    if cookies:
        cmd.extend(["--cookies", str(cookies.expanduser().resolve())])
    return cmd


def scrape_youtube_comments(url: str, *, max_comments: int, cookies: Path | None = None) -> dict[str, Any]:
    cmd = build_youtube_comments_command(url, max_comments=max_comments, cookies=cookies)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp comments failed ({proc.returncode}): {proc.stderr.strip()}")
    metadata = json.loads(proc.stdout)
    video_id = str(metadata.get("id") or metadata.get("display_id") or "")
    raw_comments = metadata.get("comments") or []
    comments = [normalize_youtube_comment(item, video_id=video_id) for item in raw_comments[:max_comments]]
    return {
        "video_id": video_id,
        "title": metadata.get("title") or "",
        "comments": comments,
        "source": {
            "engine": "yt-dlp",
            "extractor_key": metadata.get("extractor_key"),
            "comment_count": metadata.get("comment_count"),
            "command": cmd,
        },
    }


def build_youtube_comments_command(url: str, *, max_comments: int, cookies: Path | None = None) -> list[str]:
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--skip-download",
        "--write-comments",
        "--dump-single-json",
        "--no-clean-info-json",
        "--extractor-args",
        f"youtube:comment_sort=top,max_comments={max(1, max_comments)}",
    ]
    if cookies:
        cmd.extend(["--cookies", str(cookies.expanduser().resolve())])
    cmd.append(url)
    return cmd


def scrape_bilibili_comments(url: str, *, max_comments: int) -> dict[str, Any]:
    metadata = fetch_bilibili_video_metadata(url)
    aid = metadata["aid"]
    video_id = metadata.get("bvid") or str(aid)
    comments: list[dict[str, Any]] = []
    page = 1
    while len(comments) < max_comments:
        data = fetch_bilibili_reply_page(aid=aid, page=page, page_size=min(20, max_comments))
        replies = data.get("replies") or []
        if not replies:
            break
        for reply in replies:
            comments.append(normalize_bilibili_reply(reply, video_id=video_id))
            for child in reply.get("replies") or []:
                comments.append(
                    normalize_bilibili_reply(
                        child,
                        video_id=video_id,
                        parent_id=str(reply.get("rpid_str") or reply.get("rpid") or ""),
                    )
                )
            if len(comments) >= max_comments:
                break
        page += 1
        if page > 20:
            break
        time.sleep(0.2)
    return {
        "video_id": video_id,
        "title": metadata.get("title") or "",
        "comments": comments[:max_comments],
        "source": {
            "engine": "bilibili-web-api",
            "aid": aid,
            "bvid": metadata.get("bvid"),
            "owner": metadata.get("owner"),
        },
    }


def fetch_bilibili_video_metadata(url: str) -> dict[str, Any]:
    bvid = extract_bvid(url)
    aid = extract_aid(url)
    if not bvid and not aid:
        raise ValueError(f"Could not find Bilibili bvid/aid in URL: {url}")
    params = {"bvid": bvid} if bvid else {"aid": aid}
    api_url = "https://api.bilibili.com/x/web-interface/view?" + urllib.parse.urlencode(params)
    payload = http_json(api_url, referer=url)
    if payload.get("code") != 0:
        raise RuntimeError(f"Bilibili metadata API failed: {payload}")
    data = payload.get("data") or {}
    return {
        "aid": int(data.get("aid") or aid),
        "bvid": data.get("bvid") or bvid,
        "title": data.get("title") or "",
        "owner": (data.get("owner") or {}).get("name") or "",
    }


def fetch_bilibili_reply_page(*, aid: int, page: int, page_size: int) -> dict[str, Any]:
    params = {
        "type": 1,
        "oid": aid,
        "pn": page,
        "ps": page_size,
        "sort": 2,
    }
    api_url = "https://api.bilibili.com/x/v2/reply?" + urllib.parse.urlencode(params)
    payload = http_json(api_url, referer="https://www.bilibili.com")
    if payload.get("code") != 0:
        raise RuntimeError(f"Bilibili reply API failed: {payload}")
    return payload.get("data") or {}


def normalize_youtube_comment(raw: dict[str, Any], *, video_id: str) -> dict[str, Any]:
    timestamp = raw.get("timestamp")
    parent_id = str(raw.get("parent") or raw.get("parent_id") or "") or None
    if parent_id == "root":
        parent_id = None
    return {
        "id": str(raw.get("id") or raw.get("cid") or ""),
        "platform": "youtube",
        "video_id": video_id,
        "author": raw.get("author") or raw.get("author_name") or "",
        "author_id": str(raw.get("author_id") or ""),
        "author_avatar": raw.get("author_thumbnail") or raw.get("author_avatar") or "",
        "text": raw.get("text") or raw.get("html") or "",
        "like_count": int_or_none(raw.get("like_count")) or 0,
        "reply_count": int_or_none(raw.get("reply_count")) or 0,
        "published_at": iso_from_timestamp(timestamp),
        "parent_id": parent_id,
        "images": [],
        "raw_url": raw.get("author_url") or "",
    }


def normalize_bilibili_reply(raw: dict[str, Any], *, video_id: str, parent_id: str | None = None) -> dict[str, Any]:
    member = raw.get("member") or {}
    content = raw.get("content") or {}
    images = []
    for picture in content.get("pictures") or []:
        url = picture.get("img_src") or picture.get("url") or picture.get("src") or ""
        if not url:
            continue
        images.append(
            {
                "url": normalize_protocol_url(url),
                "width": int_or_none(picture.get("img_width") or picture.get("width")),
                "height": int_or_none(picture.get("img_height") or picture.get("height")),
                "kind": "comment_picture",
            }
        )
    return {
        "id": str(raw.get("rpid_str") or raw.get("rpid") or ""),
        "platform": "bilibili",
        "video_id": video_id,
        "author": member.get("uname") or "",
        "author_id": str(member.get("mid") or ""),
        "author_avatar": normalize_protocol_url(member.get("avatar") or ""),
        "text": content.get("message") or "",
        "like_count": int_or_none(raw.get("like")) or 0,
        "reply_count": int_or_none(raw.get("rcount")) or 0,
        "published_at": iso_from_timestamp(raw.get("ctime")),
        "parent_id": parent_id,
        "images": images,
        "raw_url": "",
    }


def write_comments_report(output_dir: Path, data: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / "comments_report.html"
    comments = data.get("comments") or []
    rows = "\n".join(render_comment_card(item) for item in comments)
    screenshots = data.get("comment_screenshots") or []
    screenshot_gallery = render_screenshot_gallery(screenshots, data.get("comment_screenshot_manifest") or {})
    visual_gallery = render_visual_item_gallery(data.get("comment_visual_items") or [])
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LogicCut V0.2.2 评论区抓取验收</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #080b16;
      --panel: rgba(16, 24, 42, 0.82);
      --line: rgba(148, 163, 184, 0.22);
      --text: #f8fafc;
      --muted: #94a3b8;
      --cyan: #22d3ee;
      --pink: #d946ef;
      --blue: #2563eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Inter, "Noto Sans SC", "Microsoft YaHei", Arial, sans-serif;
      background:
        radial-gradient(circle at 12% 18%, rgba(34, 211, 238, 0.18), transparent 30%),
        radial-gradient(circle at 78% 5%, rgba(217, 70, 239, 0.18), transparent 32%),
        linear-gradient(135deg, #070914 0%, #0b1020 46%, #060716 100%);
      color: var(--text);
    }}
    .wrap {{ width: min(1160px, calc(100% - 40px)); margin: 0 auto; padding: 44px 0 64px; }}
    .hero {{ border-bottom: 1px solid var(--line); padding-bottom: 28px; }}
    .eyebrow {{ color: var(--cyan); font-size: 13px; letter-spacing: .08em; text-transform: uppercase; }}
    h1 {{ margin: 12px 0 12px; font-size: clamp(32px, 5vw, 58px); line-height: 1.05; letter-spacing: 0; }}
    .subtitle {{ margin: 0; max-width: 820px; color: #cbd5e1; font-size: 17px; line-height: 1.7; }}
    .stats {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin: 28px 0; }}
    .stat {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }}
    .stat b {{ display:block; font-size: 24px; }}
    .stat span {{ color: var(--muted); font-size: 13px; }}
    .source {{ color: var(--muted); overflow-wrap: anywhere; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 24px; }}
    .card {{
      display: grid;
      grid-template-columns: 52px minmax(0, 1fr);
      gap: 14px;
      background: rgba(15, 23, 42, 0.76);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 24px 80px rgba(0,0,0,.25);
    }}
    .avatar {{ width: 52px; height: 52px; border-radius: 50%; object-fit: cover; background: linear-gradient(135deg, var(--cyan), var(--blue), var(--pink)); }}
    .avatar.fallback {{ display: grid; place-items: center; color: white; font-weight: 800; }}
    .meta {{ display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:8px; }}
    .author {{ font-weight: 800; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .time {{ color: var(--muted); font-size: 12px; white-space: nowrap; }}
    .text {{ color: #e2e8f0; font-size: 15px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .badges {{ display:flex; gap: 8px; margin-top: 12px; color: var(--muted); font-size: 12px; }}
    .images {{ display:flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }}
    .images img {{ width: 120px; height: 80px; object-fit: cover; border-radius: 6px; border: 1px solid var(--line); }}
    .screenshots {{ margin: 26px 0; }}
    .screenshots h2 {{ margin: 0 0 12px; font-size: 24px; }}
    .visuals {{ margin: 26px 0; }}
    .visuals h2 {{ margin: 0 0 12px; font-size: 24px; }}
    .notice {{ margin: 0 0 14px; padding: 12px 14px; border: 1px solid rgba(251,191,36,.38); border-radius: 8px; background: rgba(251,191,36,.12); color: #fde68a; line-height: 1.55; }}
    .shotgrid {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .shot {{ border: 1px solid var(--line); border-radius: 8px; background: rgba(15,23,42,.72); padding: 10px; }}
    .shot img {{ width: 100%; display:block; border-radius: 6px; }}
    .shot span {{ display:block; margin-top: 8px; color: var(--muted); font-size: 12px; }}
    .visualgrid {{ display:grid; grid-template-columns: 1fr; gap: 16px; }}
    .visual {{ border: 1px solid var(--line); border-radius: 8px; background: rgba(15,23,42,.72); padding: 12px; }}
    .visual img {{ width: 100%; display:block; border-radius: 6px; background:#fff; }}
    .visual b {{ display:block; margin-top: 10px; color:#fff; }}
    .visual span {{ display:block; margin-top: 6px; color: var(--muted); line-height:1.55; }}
    .empty {{ padding: 28px; border: 1px solid var(--line); border-radius: 8px; color: var(--muted); }}
    @media (max-width: 820px) {{
      .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div class="eyebrow">LogicCut V0.2.2</div>
      <h1>评论区抓取验收</h1>
      <p class="subtitle">抓取公开视频评论区，把评论文本、作者信息、点赞回复数和评论图片整理成可复用 JSON，并生成这个验收页面。后续可以把评论转成选题、开头文案、争议点对比和评论驱动二创视频。</p>
    </section>
    <section class="stats">
      <div class="stat"><b>{html.escape(str(data.get("platform", "")))}</b><span>平台</span></div>
      <div class="stat"><b>{html.escape(str(data.get("comment_count", len(comments))))}</b><span>评论数</span></div>
      <div class="stat"><b>{html.escape(str(data.get("image_count", len(data.get("images") or []))))}</b><span>评论图片</span></div>
      <div class="stat"><b>{html.escape(str(data.get("screenshot_count", len(screenshots))))}</b><span>评论区截图</span></div>
      <div class="stat"><b>{html.escape(str(data.get("video_id", "")))}</b><span>视频 ID</span></div>
    </section>
    <p class="source">视频：{html.escape(str(data.get("title") or ""))}<br>URL：{html.escape(str(data.get("url") or ""))}</p>
    {screenshot_gallery}
    {visual_gallery}
    <section class="grid">
      {rows if rows else '<div class="empty">没有抓取到评论。可能是视频关闭评论、平台限制或需要 cookies。</div>'}
    </section>
  </main>
</body>
</html>
"""
    report.write_text(html_text, encoding="utf-8")
    return report


def render_comment_card(item: dict[str, Any]) -> str:
    author = item.get("author") or "匿名用户"
    avatar = item.get("author_avatar") or ""
    if avatar:
        avatar_html = f'<img class="avatar" src="{html.escape(avatar)}" alt="">'
    else:
        avatar_html = f'<div class="avatar fallback">{html.escape(author[:1] or "?")}</div>'
    image_html = "".join(
        f'<img src="{html.escape(image.get("local_path") or image.get("url") or "")}" alt="">'
        for image in item.get("images") or []
        if image.get("local_path") or image.get("url")
    )
    return f"""<article class="card">
  {avatar_html}
  <div>
    <div class="meta">
      <div class="author">{html.escape(str(author))}</div>
      <div class="time">{html.escape(str(item.get("published_at") or ""))}</div>
    </div>
    <div class="text">{html.escape(str(item.get("text") or ""))}</div>
    <div class="badges"><span>赞 {html.escape(str(item.get("like_count", 0)))}</span><span>回复 {html.escape(str(item.get("reply_count", 0)))}</span><span>{html.escape(str(item.get("platform", "")))}</span></div>
    {f'<div class="images">{image_html}</div>' if image_html else ''}
  </div>
</article>"""


def render_screenshot_gallery(screenshots: list[dict[str, Any]], manifest: dict[str, Any] | None = None) -> str:
    manifest = manifest or {}
    status = manifest.get("status") or ""
    warning = manifest.get("warning") or manifest.get("error") or ""
    notice = ""
    if status and status not in {"ok", "skipped"}:
        message = f"截图状态：{status}"
        if warning:
            message += f" · {warning}"
        notice = f'<div class="notice">{html.escape(message)}</div>'
    if not screenshots:
        return f"""<section class="screenshots">
  <h2>真实评论区截图</h2>
  {notice}
  <div class="empty">没有生成评论区截图。可能是命令禁用了截图，或平台页面需要登录 / cookies。</div>
</section>"""
    items = "\n".join(
        f"""<figure class="shot">
  <img src="{html.escape(str(item.get("path") or ""))}" alt="评论区截图 {html.escape(str(item.get("index") or ""))}">
  <span>截图 {html.escape(str(item.get("index") or ""))} · scrollY {html.escape(str(item.get("scroll_y") or ""))}</span>
</figure>"""
        for item in screenshots
        if item.get("path")
    )
    return f"""<section class="screenshots">
  <h2>真实评论区截图</h2>
  {notice}
  <div class="shotgrid">{items}</div>
</section>"""


def render_visual_item_gallery(visual_items: list[dict[str, Any]]) -> str:
    if not visual_items:
        return ""
    items = "\n".join(
        f"""<figure class="visual">
  <img src="{html.escape(str(item.get("path") or ""))}" alt="完整评论截图 {html.escape(str(index))}">
  <b>{html.escape(str(item.get("author") or "匿名评论"))}</b>
  <span>{html.escape(sanitize_comment_display_text(item.get("visible_text") or "", max_chars=160))}</span>
</figure>"""
        for index, item in enumerate(visual_items, start=1)
        if item.get("path")
    )
    if not items:
        return ""
    return f"""<section class="visuals">
  <h2>完整评论截图</h2>
  <div class="visualgrid">{items}</div>
</section>"""


def write_comments_showcase(output_dir: Path, cases: list[dict[str, Any]]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / "index.html"
    cards = "\n".join(render_showcase_case(item) for item in cases)
    research = render_comment_research()
    report.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LogicCut V0.2.2 评论区抓取 Showcase</title>
  <style>
    body {{ margin: 0; font-family: Inter, "Noto Sans SC", Arial, sans-serif; background: #070914; color: #f8fafc; }}
    .wrap {{ width: min(1180px, calc(100% - 40px)); margin: 0 auto; padding: 46px 0 64px; }}
    h1 {{ font-size: clamp(34px, 5vw, 64px); margin: 0 0 12px; letter-spacing: 0; }}
    p {{ color: #cbd5e1; line-height: 1.7; max-width: 860px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-top: 28px; }}
    .case {{ background: linear-gradient(135deg, rgba(30,41,59,.9), rgba(15,23,42,.86)); border: 1px solid rgba(148,163,184,.22); border-radius: 8px; padding: 22px; }}
    .case h2 {{ margin: 0 0 8px; }}
    .stat {{ display: flex; gap: 12px; flex-wrap: wrap; color: #94a3b8; font-size: 13px; margin: 14px 0; }}
    a {{ color: #22d3ee; }}
    .sample {{ margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(148,163,184,.2); }}
    .sample div {{ margin: 10px 0; color: #e2e8f0; line-height: 1.55; }}
    .preview {{ margin-top: 14px; border-radius: 8px; overflow: hidden; border: 1px solid rgba(148,163,184,.22); }}
    .preview img {{ width: 100%; display:block; }}
    .research {{ margin-top: 34px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }}
    .repo {{ border: 1px solid rgba(148,163,184,.22); background: rgba(15,23,42,.72); border-radius: 8px; padding: 18px; }}
    .repo b {{ display: block; margin-bottom: 8px; }}
    .repo span {{ display: block; color: #cbd5e1; line-height: 1.6; font-size: 14px; }}
    h2.section {{ margin-top: 42px; font-size: 28px; }}
    @media (max-width: 820px) {{ .grid {{ grid-template-columns: 1fr; }} }}
    @media (max-width: 980px) {{ .research {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main class="wrap">
    <h1>V0.2.2 评论区抓取</h1>
    <p>这一版验证 YouTube / Bilibili 评论区抓取能力：产物包括标准化 <code>comments.json</code>、图片附件、单视频验收页，以及这个汇总页。评论数据后续会用于评论驱动选题、评论反应视频、争议点切片和创作者口吻文案生成。</p>
    <h2 class="section">公开项目调研</h2>
    <section class="research">{research}</section>
    <h2 class="section">本地验证结果</h2>
    <section class="grid">{cards}</section>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    return report


def render_comment_research() -> str:
    repos = [
        {
            "name": "yt-dlp/yt-dlp",
            "url": "https://github.com/yt-dlp/yt-dlp",
            "note": "已有 YouTube 评论导出能力，当前实现直接复用 --write-comments 进入 infojson，再归一化为 LogicCut comments.json。",
        },
        {
            "name": "Nemo2011/bilibili-api",
            "url": "https://github.com/Nemo2011/bilibili-api",
            "note": "高 Star 的 Python B 站 API 库，覆盖视频和评论等模块；因 GPL 和异步依赖较重，当前只参考接口形态，不直接引入依赖。",
        },
        {
            "name": "SocialSisterYi/bilibili-API-collect",
            "url": "https://github.com/SocialSisterYi/bilibili-API-collect",
            "note": "B 站 API 收集类项目，历史 Star 高，适合确认接口路径；仓库状态和平台合规风险要求我们保持最小公开数据抓取。",
        },
    ]
    return "\n".join(
        f"""<article class="repo">
  <b><a href="{html.escape(item["url"])}">{html.escape(item["name"])}</a></b>
  <span>{html.escape(item["note"])}</span>
</article>"""
        for item in repos
    )


def render_showcase_case(item: dict[str, Any]) -> str:
    sample_comments = item.get("comments", [])[:3]
    samples = "".join(
        f"<div><strong>{html.escape(str(comment.get('author') or '匿名'))}</strong>：{html.escape(str(comment.get('text') or ''))}</div>"
        for comment in sample_comments
    )
    report = item.get("report_path") or "comments_report.html"
    first_shot = (item.get("comment_screenshots") or [{}])[0].get("path")
    preview = f'<div class="preview"><img src="{html.escape(str(first_shot))}" alt="真实评论区截图"></div>' if first_shot else ""
    return f"""<article class="case">
  <h2>{html.escape(str(item.get("title") or item.get("video_id") or "Untitled"))}</h2>
  <div class="stat"><span>{html.escape(str(item.get("platform", "")))}</span><span>评论 {html.escape(str(item.get("comment_count", 0)))}</span><span>附件图 {html.escape(str(item.get("image_count", 0)))}</span><span>真实评论区截图 {html.escape(str(item.get("screenshot_count", 0)))}</span></div>
  <a href="{html.escape(str(report))}">打开单视频验收页</a>
  {preview}
  <div class="sample">{samples}</div>
</article>"""


def create_comment_freeze_video(
    comments_json: Path,
    output_dir: Path,
    *,
    layout: str = "landscape",
    max_frames: int = 10,
    frame_duration: float = 3.0,
    size: tuple[int, int] | None = None,
    log_file: Path | None = None,
) -> dict[str, Any]:
    data = _read_json(comments_json)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_size = size or _layout_size(layout)
    comments = data.get("comments") or []
    visual_items = _resolve_comment_visual_items(data, comments_json.parent)
    screenshots = _resolve_comment_screenshots(data, comments_json.parent)
    if not visual_items and not screenshots and not comments:
        raise ValueError("comment-freeze requires comment_visual_items, comment_screenshots, or comments in comments.json")

    frame_dir = output_dir / "comment_frames"
    segment_dir = output_dir / "segments"
    frame_dir.mkdir(parents=True, exist_ok=True)
    segment_dir.mkdir(parents=True, exist_ok=True)
    source_count = len(visual_items) or max(len(screenshots), len(comments), 1)
    frame_count = min(max(1, max_frames), source_count)
    frames: list[dict[str, Any]] = []
    segments: list[Path] = []
    for index in range(frame_count):
        visual_item = visual_items[index % len(visual_items)] if visual_items else None
        screenshot = (
            {"path_abs": visual_item.get("path_abs"), "path": visual_item.get("path")}
            if visual_item
            else screenshots[index % len(screenshots)]
            if screenshots
            else None
        )
        comment = _comment_from_visual_item(visual_item) if visual_item else comments[index % len(comments)] if comments else {}
        frame_path = frame_dir / f"{index + 1:03d}.png"
        render_comment_freeze_frame(
            screenshot.get("path_abs") if screenshot else None,
            frame_path,
            comment=comment,
            title=str(data.get("title") or "评论区定格"),
            platform="visual_item" if visual_item else str(data.get("platform") or ""),
            index=index + 1,
            total=frame_count,
            layout=layout,
            size=output_size,
        )
        segment_path = segment_dir / f"{index + 1:03d}.mp4"
        _render_still_image_segment(frame_path, segment_path, duration=frame_duration, size=output_size, log_file=log_file)
        frames.append(
            {
                "index": index + 1,
                "path": _relative_to(frame_path, output_dir),
                "source_screenshot": screenshot.get("path") if screenshot else "",
                "source_visual_item": visual_item.get("path", "") if visual_item else "",
                "visual_item_id": visual_item.get("id", "") if visual_item else "",
                "comment_id": comment.get("id", ""),
                "author": comment.get("author", ""),
                "text": comment.get("text", ""),
                "duration": frame_duration,
            }
        )
        segments.append(segment_path)

    output_video = output_dir / "comment_freeze_video.mp4"
    concat_videos_reencode(segments, output_video, log_file=log_file)
    manifest_path = output_dir / "comment_freeze_manifest.json"
    report_path = output_dir / "comment_freeze_report.html"
    result = {
        "schema_version": "logiccut.comment_freeze.v1",
        "layout": layout,
        "size": {"width": output_size[0], "height": output_size[1]},
        "source_comments": str(comments_json),
        "frame_count": len(frames),
        "frame_duration": frame_duration,
        "frames": frames,
        "output_video": str(output_video),
        "manifest_path": str(manifest_path),
        "report_path": str(report_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(_comment_freeze_report_html(result, data), encoding="utf-8")
    return result


def render_comment_freeze_frame(
    screenshot: Path | None,
    output_path: Path,
    *,
    comment: dict[str, Any],
    title: str,
    platform: str,
    index: int,
    total: int,
    layout: str,
    size: tuple[int, int],
) -> Path:
    from PIL import Image, ImageDraw, ImageFilter

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", size, "#070914")
    draw = ImageDraw.Draw(canvas)

    source = None
    if screenshot and screenshot.exists():
        source = Image.open(screenshot).convert("RGB")
        bg = _fit_cover(source, size).filter(ImageFilter.GaussianBlur(radius=18))
        canvas = Image.blend(canvas, bg, 0.18)
        draw = ImageDraw.Draw(canvas)

    source_crop = _comment_region_crop(source, platform=platform) if source else None
    _draw_screenshot_focus_frame(canvas, draw, source_crop, layout=layout)
    canvas.save(output_path)
    return output_path


def build_comment_narration_plan(
    comments_data: dict[str, Any],
    freeze_manifest: dict[str, Any],
    *,
    max_items: int = 6,
) -> dict[str, Any]:
    comments = comments_data.get("comments") or []
    visual_items = comments_data.get("comment_visual_items") or []
    visual_by_id = {str(item.get("id") or ""): item for item in visual_items if item.get("id")}
    frames = freeze_manifest.get("frames") or []
    count = min(max(1, max_items), max(len(frames), len(visual_items), len(comments), 1))
    first_source = _comment_from_visual_item(visual_items[0]) if visual_items else comments[0] if comments else {}
    primary_angle = _comment_summary_angle(normalize_display_text(str(first_source.get("text") or "")))
    story_title = sanitize_comment_display_text(comments_data.get("title") or "这条视频", max_chars=28)
    items: list[dict[str, Any]] = []
    for index in range(count):
        frame = frames[index % len(frames)] if frames else {}
        visual_item = visual_by_id.get(str(frame.get("visual_item_id") or "")) if frame else None
        if visual_item is None and visual_items:
            visual_item = visual_items[index % len(visual_items)]
        comment = _comment_from_visual_item(visual_item) if visual_item else comments[index % len(comments)] if comments else {}
        frame = frames[index % len(frames)] if frames else {}
        text = normalize_display_text(str(comment.get("text") or "这条评论适合作为视频里的观众反馈。"))
        why = _comment_story_reason(comment, index=index)
        narration = build_comment_story_narration(
            text,
            comment,
            index=index,
            total=count,
            title=story_title,
            primary_angle=primary_angle,
        )
        items.append(
            {
                "index": index + 1,
                "frame": frame.get("path") or "",
                "comment_id": comment.get("id", ""),
                "visual_item_id": frame.get("visual_item_id") or (visual_item or {}).get("id", ""),
                "author": comment.get("author") or "",
                "comment_text": text,
                "narration": narration,
                "why": why,
                "duration": max(float(frame.get("duration", 3.5) or 3.5), min(7.5, len(narration) / 7.5)),
            }
        )
    return {
        "schema_version": "logiccut.comment_narration.v1",
        "title": comments_data.get("title") or "评论区解说",
        "platform": comments_data.get("platform") or "",
        "source_comments": comments_data.get("url") or "",
        "story": "以原视频内容为主线，用多张评论截图串起观众对这个话题的不同理解。",
        "items": items,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def create_comment_narration_video(
    comments_json: Path,
    freeze_manifest_json: Path,
    output_dir: Path,
    *,
    max_items: int = 6,
    tts_engine: str | None = None,
    tts_ports: str | None = None,
    voice: str | None = None,
    ref_wav: Path | None = None,
    ref_text: str | None = None,
    allow_tts_fallback: bool = False,
    render: bool = True,
    log_file: Path | None = None,
) -> dict[str, Any]:
    comments_data = _read_json(comments_json)
    freeze_manifest = _read_json(freeze_manifest_json)
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = build_comment_narration_plan(comments_data, freeze_manifest, max_items=max_items)
    plan_path = output_dir / "comment_narration_plan.json"
    prompt_path = output_dir / "comment_narration_prompt.md"
    report_path = output_dir / "comment_narration_report.html"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prompt_path.write_text(_comment_narration_prompt(plan), encoding="utf-8")

    result: dict[str, Any] = {
        "schema_version": "logiccut.comment_narration_render.v1",
        "plan_path": str(plan_path),
        "prompt_path": str(prompt_path),
        "report_path": str(report_path),
        "item_count": len(plan["items"]),
        "output_video": "",
        "parts": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if render and plan["items"]:
        output_video, parts = _render_comment_narration_parts(
            plan,
            freeze_manifest_json.parent,
            output_dir,
            tts_engine=tts_engine,
            tts_ports=tts_ports,
            voice=voice,
            ref_wav=ref_wav,
            ref_text=ref_text,
            allow_tts_fallback=allow_tts_fallback,
            log_file=log_file,
        )
        result["output_video"] = str(output_video)
        result["parts"] = parts

    report_path.write_text(_comment_narration_report_html(result, plan), encoding="utf-8")
    result_path = output_dir / "comment_narration_render.json"
    result["result_path"] = str(result_path)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _render_comment_narration_parts(
    plan: dict[str, Any],
    freeze_root: Path,
    output_dir: Path,
    *,
    tts_engine: str | None,
    tts_ports: str | None,
    voice: str | None,
    ref_wav: Path | None,
    ref_text: str | None,
    allow_tts_fallback: bool,
    log_file: Path | None,
) -> tuple[Path, list[dict[str, Any]]]:
    audio_dir = output_dir / "audio"
    subtitle_dir = output_dir / "subtitles"
    segment_dir = output_dir / "segments"
    for path in (audio_dir, subtitle_dir, segment_dir):
        path.mkdir(parents=True, exist_ok=True)
    parts: list[dict[str, Any]] = []
    segment_paths: list[Path] = []
    for index, item in enumerate(plan.get("items") or [], start=1):
        frame = _resolve_asset(freeze_root, str(item.get("frame") or ""))
        if not frame.exists():
            continue
        text = normalize_display_text(str(item.get("narration") or ""))
        audio_path = audio_dir / f"{index:03d}.wav"
        tts_result = _synthesize_comment_audio(
            text,
            audio_path,
            engine=tts_engine,
            tts_ports=tts_ports,
            voice=voice,
            ref_wav=ref_wav,
            ref_text=ref_text,
            allow_tts_fallback=allow_tts_fallback,
            log_file=log_file,
        )
        duration = max(float(item.get("duration", 3.5) or 3.5), safe_audio_duration(audio_path, fallback=3.5))
        base_video = segment_dir / f"{index:03d}_base.mp4"
        narrated_video = segment_dir / f"{index:03d}.mp4"
        _render_still_image_segment(frame, base_video, duration=duration, size=_image_size(frame), log_file=log_file)
        subtitle_path = subtitle_dir / f"{index:03d}.srt"
        write_narration_srt(subtitle_path, text, duration=duration)
        mix_card_with_narration(base_video, audio_path, subtitle_path, narrated_video, log_file=log_file)
        segment_paths.append(narrated_video)
        parts.append(
            {
                "index": index,
                "frame": str(frame),
                "audio": str(audio_path),
                "subtitle": str(subtitle_path),
                "video": str(narrated_video),
                "duration": duration,
                "tts_backend": tts_result.get("backend", ""),
                "why": item.get("why", ""),
            }
        )
    if not segment_paths:
        raise ValueError("comment-narration could not find any frame from freeze manifest")
    output_video = output_dir / "comment_narration_video.mp4"
    concat_videos_reencode(segment_paths, output_video, log_file=log_file)
    return output_video, parts


def _synthesize_comment_audio(
    text: str,
    output_path: Path,
    *,
    engine: str | None,
    tts_ports: str | None,
    voice: str | None,
    ref_wav: Path | None,
    ref_text: str | None,
    allow_tts_fallback: bool,
    log_file: Path | None,
) -> dict[str, Any]:
    backend_options: dict[str, Any] = {"recipe": "comment-narration", "language": "zh-CN"}
    if ref_wav:
        backend_options["ref_wav"] = str(ref_wav.expanduser().resolve())
    if ref_text:
        backend_options["ref_text"] = ref_text
    try:
        return synthesize_narration_audio(
            text,
            output_path,
            engine=engine,
            voice=voice or "logiccut-comment-narrator",
            tts_ports=tts_ports,
            backend_options=backend_options,
            log_file=log_file,
        )
    except Exception:
        if not allow_tts_fallback:
            raise
        duration = max(2.2, min(8.0, len(text) / 7.2))
        run_command(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=380:sample_rate=44100",
                "-t",
                f"{duration:.3f}",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ],
            log_file=log_file,
        )
        return {"success": True, "backend": "ffmpeg-tone-fallback", "output_path": str(output_path)}


def _render_still_image_segment(
    image_path: Path,
    output_path: Path,
    *,
    duration: float,
    size: tuple[int, int],
    log_file: Path | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = size
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t",
            f"{duration:.3f}",
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
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
            str(output_path),
        ],
        log_file=log_file,
    )
    return output_path


def _draw_neon_background(draw: Any, size: tuple[int, int]) -> None:
    width, height = size
    draw.rectangle((0, 0, width, height), outline="#172554", width=max(2, width // 420))
    draw.line((0, int(height * 0.17), width, int(height * 0.17)), fill="#22d3ee", width=max(2, width // 360))
    draw.line((0, int(height * 0.83), width, int(height * 0.83)), fill="#a855f7", width=max(2, width // 360))
    for i in range(8):
        x = int(width * (0.08 + i * 0.13))
        draw.line((x, 0, x + int(width * 0.12), height), fill="#111c3a", width=1)


def _draw_screenshot_focus_frame(canvas: Any, draw: Any, source_crop: Any, *, layout: str) -> None:
    width, height = canvas.size
    margin = max(10, int(min(width, height) * (0.026 if layout == "portrait" else 0.022)))
    box = (margin, margin, width - margin, height - margin)
    if source_crop is None:
        _rounded(draw, box, fill="#0f172a", outline="#334155", radius=16, width=2)
        _draw_text(draw, "没有可用评论区截图", (box[0] + 28, box[1] + 28), _default_font(34), fill="#94a3b8")
        return
    target_size = (box[2] - box[0], box[3] - box[1])
    focused = _fit_contain(source_crop, target_size)
    paste_x = box[0] + (target_size[0] - focused.width) // 2
    paste_y = box[1] + (target_size[1] - focused.height) // 2
    canvas.paste(focused, (paste_x, paste_y))
    try:
        draw.rounded_rectangle(box, radius=12, outline="#22d3ee", width=max(2, width // 520))
    except TypeError:
        draw.rectangle(box, outline="#22d3ee", width=max(2, width // 520))


def _draw_landscape_comment_frame(
    canvas: Any,
    draw: Any,
    source_crop: Any,
    *,
    comment: dict[str, Any],
    title: str,
    platform: str,
    index: int,
    total: int,
    fonts: tuple[Any, Any, Any, Any],
) -> None:
    width, height = canvas.size
    title_font, body_font, small_font, label_font = fonts
    margin = int(width * 0.045)
    shot_box = (margin, int(height * 0.21), int(width * 0.66), int(height * 0.78))
    panel_box = (int(width * 0.69), int(height * 0.21), width - margin, int(height * 0.78))
    _paste_panel(canvas, draw, source_crop, shot_box)
    _rounded(draw, panel_box, fill="#071225", outline="#334155", radius=18, width=max(2, width // 620))
    _draw_badge(draw, (margin, int(height * 0.08)), "评论区高光", label_font)
    _draw_text(draw, sanitize_comment_display_text(title, max_chars=30), (margin, int(height * 0.12)), title_font, fill="#f8fafc", max_width=shot_box[2] - margin)
    _draw_text(draw, f"{platform or 'video'} · {index}/{total}", (panel_box[0] + 24, panel_box[1] + 26), small_font, fill="#67e8f9")
    _draw_text(draw, sanitize_comment_display_text(comment.get("author") or "匿名用户", max_chars=18), (panel_box[0] + 24, panel_box[1] + 66), label_font, fill="#f8fafc", max_width=panel_box[2] - panel_box[0] - 48)
    text = sanitize_comment_display_text(comment.get("text") or "这条评论适合做视频里的观众反馈。", max_chars=90)
    _draw_multiline(draw, text, (panel_box[0] + 24, panel_box[1] + 112), body_font, fill="#e2e8f0", max_width=panel_box[2] - panel_box[0] - 48, max_lines=8)
    likes = f"赞 {comment.get('like_count', 0)} · 回复 {comment.get('reply_count', 0)}"
    _draw_text(draw, likes, (panel_box[0] + 24, panel_box[3] - 52), small_font, fill="#94a3b8")


def _draw_portrait_comment_frame(
    canvas: Any,
    draw: Any,
    source_crop: Any,
    *,
    comment: dict[str, Any],
    title: str,
    platform: str,
    index: int,
    total: int,
    fonts: tuple[Any, Any, Any, Any],
) -> None:
    width, height = canvas.size
    title_font, body_font, small_font, label_font = fonts
    margin = int(width * 0.07)
    _draw_badge(draw, (margin, int(height * 0.055)), "评论区高光", label_font)
    _draw_text(draw, sanitize_comment_display_text(title, max_chars=28), (margin, int(height * 0.105)), title_font, fill="#f8fafc", max_width=width - margin * 2)
    shot_box = (margin, int(height * 0.23), width - margin, int(height * 0.62))
    panel_box = (margin, int(height * 0.66), width - margin, int(height * 0.91))
    _paste_panel(canvas, draw, source_crop, shot_box)
    _rounded(draw, panel_box, fill="#071225", outline="#334155", radius=20, width=max(2, width // 420))
    _draw_text(draw, f"{platform or 'video'} · {index}/{total}", (panel_box[0] + 24, panel_box[1] + 22), small_font, fill="#67e8f9")
    _draw_text(draw, sanitize_comment_display_text(comment.get("author") or "匿名用户", max_chars=18), (panel_box[0] + 24, panel_box[1] + 58), label_font, fill="#f8fafc")
    text = sanitize_comment_display_text(comment.get("text") or "这条评论适合做视频里的观众反馈。", max_chars=92)
    _draw_multiline(draw, text, (panel_box[0] + 24, panel_box[1] + 104), body_font, fill="#e2e8f0", max_width=panel_box[2] - panel_box[0] - 48, max_lines=6)


def _paste_panel(canvas: Any, draw: Any, image: Any, box: tuple[int, int, int, int]) -> None:
    _rounded(draw, box, fill="#0f172a", outline="#22d3ee", radius=18, width=3)
    inner = (box[0] + 8, box[1] + 8, box[2] - 8, box[3] - 8)
    if image is None:
        _draw_text(draw, "没有可用评论区截图", (inner[0] + 24, inner[1] + 24), _default_font(30), fill="#94a3b8")
        return
    fitted = _fit_contain(image, (inner[2] - inner[0], inner[3] - inner[1]))
    x = inner[0] + (inner[2] - inner[0] - fitted.width) // 2
    y = inner[1] + (inner[3] - inner[1] - fitted.height) // 2
    canvas.paste(fitted, (x, y))


def _comment_region_crop(image: Any, *, platform: str) -> Any:
    if platform == "visual_item":
        return image
    width, height = image.size
    if platform == "youtube":
        box = (int(width * 0.10), int(height * 0.10), int(width * 0.88), int(height * 0.94))
    elif platform == "bilibili":
        box = (int(width * 0.05), int(height * 0.08), int(width * 0.66), int(height * 0.94))
    else:
        box = (int(width * 0.06), int(height * 0.08), int(width * 0.86), int(height * 0.94))
    return image.crop(box)


def _fit_cover(image: Any, size: tuple[int, int]) -> Any:
    width, height = size
    scale = max(width / image.width, height / image.height)
    resized = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _fit_contain(image: Any, size: tuple[int, int]) -> Any:
    width, height = size
    scale = min(width / image.width, height / image.height)
    return image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))


def _load_font(image_font: Any, font_path: str, size: int) -> Any:
    try:
        return image_font.truetype(font_path, size=size)
    except Exception:
        return image_font.load_default()


def _default_font(size: int) -> Any:
    from PIL import ImageFont

    return _load_font(ImageFont, subtitle_font_file(), size)


def _draw_badge(draw: Any, xy: tuple[int, int], text: str, font: Any) -> None:
    x, y = xy
    bbox = draw.textbbox((x, y), text, font=font)
    pad_x = 16
    pad_y = 8
    _rounded(draw, (x, y, bbox[2] + pad_x * 2, bbox[3] + pad_y * 2), fill="#1d4ed8", outline="#22d3ee", radius=8, width=2)
    draw.text((x + pad_x, y + pad_y), text, font=font, fill="#ffffff")


def _draw_text(draw: Any, text: str, xy: tuple[int, int], font: Any, *, fill: str, max_width: int | None = None) -> None:
    if max_width is not None:
        text = _truncate_to_width(draw, text, font, max_width)
    draw.text(xy, text, font=font, fill=fill)


def _draw_multiline(
    draw: Any,
    text: str,
    xy: tuple[int, int],
    font: Any,
    *,
    fill: str,
    max_width: int,
    max_lines: int,
) -> None:
    lines = _wrap_by_width(draw, text, font, max_width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _truncate_to_width(draw, lines[-1] + "…", font, max_width)
    line_height = int((draw.textbbox((0, 0), "国", font=font)[3] - draw.textbbox((0, 0), "国", font=font)[1]) * 1.55)
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height


def _wrap_by_width(draw: Any, text: str, font: Any, max_width: int) -> list[str]:
    clean = normalize_display_text(text)
    raw_parts = textwrap.wrap(clean, width=22, break_long_words=True, replace_whitespace=False) or [clean]
    lines: list[str] = []
    for part in raw_parts:
        current = ""
        for char in part:
            candidate = current + char
            if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines or [""]


def _truncate_to_width(draw: Any, text: str, font: Any, max_width: int) -> str:
    clean = normalize_display_text(text)
    if draw.textbbox((0, 0), clean, font=font)[2] <= max_width:
        return clean
    result = clean
    while result and draw.textbbox((0, 0), result + "…", font=font)[2] > max_width:
        result = result[:-1]
    return result + "…" if result else "…"


def _rounded(draw: Any, box: tuple[int, int, int, int], *, fill: str, outline: str, radius: int, width: int) -> None:
    try:
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    except TypeError:
        draw.rectangle(box, fill=fill, outline=outline, width=width)


def _resolve_comment_screenshots(data: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in data.get("comment_screenshots") or []:
        rel = str(item.get("path") or "")
        path = _resolve_asset(root, rel)
        if path.exists():
            result.append({**item, "path_abs": path})
    return result


def _resolve_comment_visual_items(data: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in data.get("comment_visual_items") or []:
        rel = str(item.get("path") or item.get("screenshot") or "")
        path = _resolve_asset(root, rel)
        if path.exists():
            result.append({**item, "path": rel, "path_abs": path})
    return result


def _comment_from_visual_item(item: dict[str, Any] | None) -> dict[str, Any]:
    if not item:
        return {}
    platform = str(item.get("platform") or "")
    if not platform and str(item.get("id") or "").startswith("youtube"):
        platform = "youtube"
    text = _clean_visual_comment_text(item.get("visible_text") or item.get("text") or "", platform=platform)
    return {
        "id": item.get("id", ""),
        "platform": platform,
        "author": item.get("author", ""),
        "text": text,
        "like_count": int_or_none(item.get("like_count")) or 0,
        "reply_count": int_or_none(item.get("reply_count")) or 0,
    }


def _clean_visual_comment_text(value: object, *, platform: str) -> str:
    text = normalize_display_text(value, strict=False)
    if platform != "youtube":
        return text
    text = re.sub(r"^@\S+\s+", "", text).strip()
    text = re.sub(
        r"^\d+\s*(秒|分钟|小时|天|周|个月|年)前(?:（修改过）)?\s*",
        "",
        text,
    ).strip()
    text = re.sub(r"\s+\d+\s*回复(?:\s*\d+\s*条回复)?\s*$", "", text).strip()
    text = re.sub(r"\s+回复(?:\s*\d+\s*条回复)?\s*$", "", text).strip()
    text = re.sub(r"\s+\d+\s*$", "", text).strip()
    return text


def _resolve_asset(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _layout_size(layout: str) -> tuple[int, int]:
    if layout == "portrait":
        return (1080, 1920)
    if layout == "square":
        return (1080, 1080)
    return (1920, 1080)


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def _relative_to(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _limit_comment_text(text: str, limit: int) -> str:
    clean = normalize_display_text(text)
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def sanitize_comment_display_text(value: object, *, max_chars: int | None = None) -> str:
    text = normalize_display_text(value, strict=False)
    safe = "".join(char for char in text if _is_stable_display_char(char)).strip()
    if max_chars is not None and len(safe) > max_chars:
        return safe[: max_chars - 1].rstrip("…，。,. ") + "…"
    return safe


def _is_stable_display_char(char: str) -> bool:
    code = ord(char)
    if code > 0xFFFF:
        return False
    if 0x2600 <= code <= 0x27BF:
        return False
    if 0x2300 <= code <= 0x23FF:
        return False
    return True


def build_comment_summary_narration(text: str, comment: dict[str, Any] | None = None, *, index: int = 0) -> str:
    clean = sanitize_comment_display_text(text, max_chars=88)
    if not clean:
        return "评论区的反馈集中在一个核心看点上：观众正在用自己的语言，把视频里的冲突和反差讲出来。"
    angle = _comment_summary_angle(clean)
    takeaway = _comment_summary_takeaway(clean)
    heat = ""
    like_count = int_or_none((comment or {}).get("like_count")) or 0
    if like_count >= 100:
        heat = "这类高赞反馈说明，这个角度已经引发了观众共鸣。"
    elif index == 0:
        heat = "把它放在前面，能先把观众带进评论区最关心的话题。"
    else:
        heat = "它适合接在后面，继续放大这个话题里的讨论张力。"
    return f"评论区把讨论集中到{angle}：{takeaway}{heat}"


def build_comment_story_narration(
    text: str,
    comment: dict[str, Any] | None = None,
    *,
    index: int = 0,
    total: int = 1,
    title: str = "这条视频",
    primary_angle: str = "视频里的核心话题",
) -> str:
    clean = sanitize_comment_display_text(text, max_chars=120)
    quote = _comment_story_quote(clean)
    angle = _comment_summary_angle(clean)
    takeaway = _comment_summary_takeaway(clean).rstrip("。")
    like_count = int_or_none((comment or {}).get("like_count")) or 0
    heat = "这条评论能被顶上来，说明这个问题确实戳中了观众。" if like_count >= 100 else ""
    if index == 0:
        return (
            f"这条视频表面上是在讲《{title}》，但评论区真正接住的是{angle}。"
            f"有的人说，{quote}。这句话先把问题抛出来：{takeaway}。{heat}"
        ).strip()
    if index >= total - 1:
        return (
            f"最后，有的人说，{quote}。这不是简单反对，而是把话题拉回{angle}。"
            f"串起来看，大家不是只在看热闹，而是在顺着这条视频，从{primary_angle}一路讲到现实里的取舍。"
        )
    connector = "接着" if index == 1 else "再往后看"
    return (
        f"{connector}，有的人说，{quote}。"
        f"这条评论不是跑题，它是在补上{angle}这一层：{takeaway}。{heat}"
    ).strip()


def _comment_story_quote(text: str) -> str:
    lower = text.lower()
    english_rules = [
        (("great", "talk", "karpathy"), "大家认可这场长谈真正有信息量，不只是蹭 AI 热点"),
        (("two smart watches", "monitoring"), "连两个智能手表这种细节，都被观众拿来调侃他的高强度状态"),
        (("outsource your thinking", "outsource your understanding"), "思考可以外包，但理解不能外包"),
        (("linkedin", "read about it"), "这场讨论很快就会被搬到 LinkedIn 上继续发酵"),
        (("video release", "behind"), "视频刚发出来，观众就已经觉得自己落后了"),
        (("my agent", "learn"), "有人甚至开玩笑说，要让自己的 AI agent 先来学习这条视频"),
        (("vibe coding", "agentic"), "大家真正关心的是，vibe coding 怎么走向 agentic engineering"),
    ]
    for keywords, quote in english_rules:
        if all(keyword in lower for keyword in keywords):
            return quote
    rules = [
        (("限制", "枷锁"), "五常身份不只是地位，也可能是一种自我约束"),
        (("战争", "打仗", "冲突", "开战"), "退出五常并不等于一定要打仗，战争本身没有那么轻松"),
        (("五常", "联合国", "安理会", "约束", "合约", "条约"), "如果连五常和联合国身份都放下，那些规则约束还算不算数"),
        (("军事", "科技", "领先", "马斯克", "火箭", "芯片"), "军事和科技到底强到什么程度，还是要拿具体技术来比"),
        (("圆明园", "八国联军", "英法", "日本", "入侵"), "今天的讨论背后，其实还连着更长的历史记忆"),
        (("安全", "放心", "没人", "不怕"), "真正打动人的不是口号，而是现实里的安全感"),
        (("反差", "对比", "但是", "不是"), "这段内容最抓人的地方，是前后反差太明显"),
        (("争议", "问题", "为什么", "离谱"), "这个话题真正有意思的地方，是它把争议点摆出来了"),
    ]
    for keywords, quote in rules:
        if any(keyword in text for keyword in keywords):
            return quote
    clean = sanitize_comment_display_text(text, max_chars=46).strip()
    clean = clean.strip("，。,.？！!?；;：:")
    return clean or "这件事没有那么简单"


def _comment_summary_angle(text: str) -> str:
    lower = text.lower()
    english_rules = [
        (("great", "talk", "karpathy"), "长谈本身的信息密度"),
        (("two smart watches", "monitoring"), "技术圈观众对人物细节的调侃"),
        (("outsource your thinking", "outsource your understanding"), "关于 AI 时代里思考和理解的边界"),
        (("linkedin", "read about it"), "技术观点在社交平台上的二次传播"),
        (("video release", "behind"), "关于 AI 更新速度带来的追赶焦虑"),
        (("my agent", "learn"), "观众把 AI agent 当成学习代理的想象"),
        (("vibe coding", "agentic"), "从 vibe coding 到 agentic engineering 的转变"),
    ]
    for keywords, angle in english_rules:
        if all(keyword in lower for keyword in keywords):
            return angle
    rules = [
        (("五常", "联合国", "安理会", "约束"), "五常身份、国际规则和自我约束"),
        (("身份", "限制", "枷锁"), "身份、规则和自我约束"),
        (("军事", "科技", "领先", "马斯克", "火箭", "芯片"), "军事实力和前沿科技的对比"),
        (("圆明园", "八国联军", "英法", "日本", "侵入", "入侵"), "历史记忆带来的当下情绪"),
        (("战争", "打仗", "冲突", "开战"), "战争有没有必要这个核心疑问"),
        (("五常", "联合国", "安理会", "合法席位", "会员国"), "五常身份、国际规则和现实成本"),
        (("反差", "对比", "不是", "但是"), "这件事里的反差和对比"),
        (("争议", "问题", "为什么", "离谱"), "背后的争议点"),
        (("安全", "放心", "没人", "不怕"), "安全感和现实体验"),
        (("预算", "GDP", "钱", "人民币", "新台币"), "预算、现实压力和观众的调侃"),
        (("震撼", "厉害", "强", "技术"), "画面带来的震撼感"),
        (("回应", "回复", "等", "关注"), "大家真正等待的后续回应"),
    ]
    for keywords, angle in rules:
        if any(keyword in text for keyword in keywords):
            return angle
    return "观众真正想追问的核心问题"


def _comment_summary_takeaway(text: str) -> str:
    lower = text.lower()
    english_rules = [
        (("great", "talk", "karpathy"), "这条评论说明观众首先认可的是内容深度，长视频也能靠密度留住人。"),
        (("two smart watches", "monitoring"), "这条评论把严肃技术访谈变成了一个轻松记忆点，适合调节节奏。"),
        (("outsource your thinking", "outsource your understanding"), "这条评论把视频里最适合传播的金句提炼出来，点出了 AI 使用的边界。"),
        (("linkedin", "read about it"), "这条评论在调侃技术圈内容的传播路径：视频刚发，二次解读很快就会跟上。"),
        (("video release", "behind"), "这条评论把 AI 领域的速度焦虑说出来了，观众会立刻有代入感。"),
        (("my agent", "learn"), "这条评论把 agent 话题变成玩笑，但也说明观众已经在用 agent 视角理解内容。"),
        (("vibe coding", "agentic"), "这条评论抓住了视频标题里的核心转向：从随手生成代码，走到更系统的 agent 工程。"),
    ]
    for keywords, takeaway in english_rules:
        if all(keyword in lower for keyword in keywords):
            return takeaway
    rules = [
        (("身份", "限制", "枷锁", "约束"), "这条评论把身份和约束放在一起看，提出了一个很适合展开的二创角度。"),
        (("战争", "打仗", "冲突", "开战"), "这条评论把话题从立场拉回现实成本，提醒观众冲突本身并不轻松。"),
        (("五常", "联合国", "安理会", "合法席位", "会员国"), "观众关心的不是口号，而是退出规则体系之后会失去什么、换来什么。"),
        (("军事", "科技", "领先", "马斯克", "火箭", "芯片"), "这条评论在追问强大叙事和前沿技术之间的真实差距。"),
        (("圆明园", "八国联军", "英法", "日本", "入侵"), "观众把视频里的当下话题，直接接回了更长的历史记忆。"),
        (("安全", "放心", "没人", "不怕"), "评论里的安全感不是抽象评价，而是观众对现实体验的直接反馈。"),
        (("反差", "对比", "但是", "不是"), "评论区正在放大这段内容里最容易吸引人的反差。"),
        (("争议", "问题", "为什么", "离谱"), "这条评论把争议点摆到台前，适合带出下一段讨论。"),
        (("震撼", "厉害", "强"), "这条反馈说明画面的冲击力已经转化成了观众记忆点。"),
    ]
    for keywords, takeaway in rules:
        if any(keyword in text for keyword in keywords):
            return takeaway
    short = sanitize_comment_display_text(text, max_chars=34)
    return f"观众正在围绕“{short}”这个点继续发散。"


def _comment_story_reason(comment: dict[str, Any], *, index: int) -> str:
    text = normalize_display_text(str(comment.get("text") or ""))
    like_count = int_or_none(comment.get("like_count")) or 0
    if any(key in text for key in ("为什么", "但是", "问题", "争议", "离谱", "安全", "震撼")):
        return "它适合做转折，因为评论里已经带出了争议点和冲突点。"
    if index == 0:
        return "它适合放在开头，因为能快速把观众拉进这个话题。"
    if like_count >= 100:
        return "它适合做重点，因为点赞数高，说明这句话已经引发共鸣。"
    return "它适合做补充，因为能把普通观众的真实反应放进视频里。"


def _comment_freeze_report_html(result: dict[str, Any], source: dict[str, Any]) -> str:
    frames = "\n".join(
        f"""<figure><img src="{html.escape(item['path'])}" alt="评论定格帧 {item['index']}"><figcaption>{html.escape(str(item.get('author') or '匿名'))}：{html.escape(_limit_comment_text(str(item.get('text') or ''), 54))}</figcaption></figure>"""
        for item in result.get("frames") or []
    )
    video_rel = Path(str(result.get("output_video") or "")).name
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LogicCut 评论定格视频验收</title>
  <style>
    body {{ margin:0; background:#070914; color:#f8fafc; font-family: Inter, "Noto Sans SC", Arial, sans-serif; }}
    main {{ width:min(1180px, calc(100% - 40px)); margin:0 auto; padding:42px 0 68px; }}
    h1 {{ margin:0 0 10px; font-size:clamp(34px,5vw,58px); letter-spacing:0; }}
    p {{ color:#cbd5e1; line-height:1.7; }}
    video {{ width:100%; max-height:70vh; background:#000; border:1px solid rgba(148,163,184,.25); border-radius:8px; }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; margin-top:22px; }}
    figure {{ margin:0; border:1px solid rgba(148,163,184,.22); border-radius:8px; overflow:hidden; background:#0f172a; }}
    img {{ display:block; width:100%; }}
    figcaption {{ padding:12px 14px; color:#cbd5e1; line-height:1.55; }}
    code {{ color:#67e8f9; }}
    @media (max-width:820px) {{ .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <h1>评论截图定格视频</h1>
    <p>来源：{html.escape(str(source.get("title") or ""))}。本页验证 V0.2.2 第二层能力：把真实评论区截图裁剪成可直接放进视频的定格画面，并输出 MP4。</p>
    <p>视频：<code>{html.escape(video_rel)}</code> · 帧数：{html.escape(str(result.get("frame_count", 0)))} · 布局：{html.escape(str(result.get("layout", "")))}</p>
    <video src="{html.escape(video_rel)}" controls></video>
    <section class="grid">{frames}</section>
  </main>
</body>
</html>"""


def _comment_narration_prompt(plan: dict[str, Any]) -> str:
    return (
        "# LogicCut V0.2.2 评论解说改写任务\n\n"
        "你是视频二创编导。请阅读 `comment_narration_plan.json`，围绕评论区观点改写每个 `items[].narration`。\n\n"
        "要求：\n\n"
        "- 口吻像短视频旁白，简洁、有观点，但不要造谣。\n"
        "- 每条旁白控制在 1-2 句。\n"
        "- 保留 `frame`、`comment_id`、`duration` 字段，不要改路径。\n"
        "- `why` 要解释为什么这条评论适合放进视频。\n\n"
        "当前自动计划摘要：\n\n"
        + json.dumps(
            {
                "title": plan.get("title"),
                "story": plan.get("story"),
                "items": [
                    {
                        "index": item.get("index"),
                        "author": item.get("author"),
                        "comment_text": item.get("comment_text"),
                        "narration": item.get("narration"),
                        "why": item.get("why"),
                    }
                    for item in plan.get("items", [])
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def _comment_narration_report_html(result: dict[str, Any], plan: dict[str, Any]) -> str:
    video_name = Path(str(result.get("output_video") or "")).name if result.get("output_video") else ""
    items = "\n".join(
        f"""<article><b>{html.escape(str(item.get('index')))}. {html.escape(str(item.get('author')))}</b><p>{html.escape(str(item.get('narration')))}</p><span>{html.escape(str(item.get('why')))}</span></article>"""
        for item in plan.get("items") or []
    )
    video = f'<video src="{html.escape(video_name)}" controls></video>' if video_name else '<div class="empty">仅生成了解说计划，未渲染视频。</div>'
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LogicCut 评论 AI 解说验收</title>
  <style>
    body {{ margin:0; background:#070914; color:#f8fafc; font-family: Inter, "Noto Sans SC", Arial, sans-serif; }}
    main {{ width:min(1080px, calc(100% - 40px)); margin:0 auto; padding:42px 0 68px; }}
    h1 {{ margin:0 0 10px; font-size:clamp(34px,5vw,58px); letter-spacing:0; }}
    p {{ color:#cbd5e1; line-height:1.7; }}
    video {{ width:100%; max-height:72vh; background:#000; border:1px solid rgba(148,163,184,.25); border-radius:8px; }}
    .grid {{ display:grid; gap:12px; margin-top:22px; }}
    article {{ border:1px solid rgba(148,163,184,.22); border-radius:8px; background:#0f172a; padding:16px; }}
    article p {{ margin:8px 0; color:#f8fafc; }}
    article span {{ color:#94a3b8; line-height:1.55; }}
    .empty {{ padding:22px; border:1px solid rgba(148,163,184,.22); color:#94a3b8; }}
    code {{ color:#67e8f9; }}
  </style>
</head>
<body>
  <main>
    <h1>评论区 AI 解说视频</h1>
    <p>这一页验证 V0.2.2 第三层能力：读取评论定格帧，生成可由 Codex 改写的解说计划，并调用 TTS / fallback 音频渲染视频。</p>
    <p>计划文件：<code>{html.escape(Path(str(result.get("plan_path", "comment_narration_plan.json"))).name)}</code> · Prompt：<code>{html.escape(Path(str(result.get("prompt_path", "comment_narration_prompt.md"))).name)}</code></p>
    {video}
    <section class="grid">{items}</section>
  </main>
</body>
</html>"""


def download_comment_images(comments: list[dict[str, Any]], image_dir: Path) -> list[dict[str, Any]]:
    image_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    index = 1
    for comment in comments:
        for image in comment.get("images") or []:
            url = image.get("url")
            if not url:
                continue
            suffix = image_suffix(url)
            filename = f"comment-{index:03d}{suffix}"
            path = image_dir / filename
            try:
                download_url(url, path)
                image["local_path"] = f"images/{filename}"
            except (OSError, urllib.error.URLError, TimeoutError):
                image["local_path"] = ""
            downloaded.append(dict(image))
            index += 1
    return downloaded


def collect_comment_images(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    images = []
    for comment in comments:
        images.extend(dict(item) for item in comment.get("images") or [])
    return images


def download_url(url: str, path: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        path.write_bytes(response.read())


def http_json(url: str, *, referer: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": referer,
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def detect_comment_platform(url: str) -> str:
    lowered = url.lower()
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "youtube"
    if "bilibili.com" in lowered or "b23.tv" in lowered:
        return "bilibili"
    raise ValueError(f"Unsupported comment URL: {url}")


def extract_bvid(url: str) -> str | None:
    match = re.search(r"(BV[0-9A-Za-z]{8,})", url)
    return match.group(1) if match else None


def extract_aid(url: str) -> int | None:
    match = re.search(r"(?:av|aid=)(\d+)", url, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def normalize_protocol_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def image_suffix(url: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    suffix = Path(path).suffix
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return suffix
    return ".jpg"


def int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def iso_from_timestamp(value: Any) -> str:
    timestamp = int_or_none(value)
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
