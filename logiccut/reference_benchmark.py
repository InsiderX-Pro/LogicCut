from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ReferencePattern:
    id: str
    summary: str
    required_elements: tuple[str, ...]
    shot_length_range: tuple[float, float]
    black_frames_allowed: bool
    narration_mode: str
    original_audio_ratio: float
    caption_style: str
    breakdown: tuple[str, ...]


@dataclass(frozen=True)
class ReferenceCase:
    id: str
    title: str
    category: str
    reference_title: str
    reference_url: str
    reference_channel: str
    source_label: str
    source_path: Path
    reproduction_path: Path
    pattern: ReferencePattern


def default_reference_cases(repo_root: Path) -> list[ReferenceCase]:
    root = Path(repo_root)
    return [
        ReferenceCase(
            id="movie_recap_drama",
            title="剧情解说复现",
            category="movie_recap",
            reference_title="Movie Recaps - Vertical Prison Where You Have 2 Minutes to Eat",
            reference_url="https://www.youtube.com/watch?v=l9HK8hHtQtE",
            reference_channel="Movie Recaps",
            source_label="公共交通暖心剧情素材",
            source_path=root / "output/effect-eval/drama-feeling-through/source_full_720p.mp4",
            reproduction_path=root / "output/effect-eval/story-guided-review/videos/drama-story-guided.mp4",
            pattern=ReferencePattern(
                id="movie_recap",
                summary="连续旁白推动剧情，画面始终承接旁白信息，原声只作为少量证据出现。",
                required_elements=(
                    "hook",
                    "continuous_voiceover",
                    "plot_order",
                    "evidence_clip",
                    "large_readable_captions",
                    "no_black_frames",
                ),
                shot_length_range=(1.2, 5.0),
                black_frames_allowed=False,
                narration_mode="continuous_voiceover_with_story_beats",
                original_audio_ratio=0.15,
                caption_style="large bottom captions with concise Chinese explanation",
                breakdown=(
                    "0-3s：用一句冲突问题或反常识信息做 hook，画面必须是人物/动作特写。",
                    "3-15s：旁白连续解释人物处境，画面按剧情因果顺序推进。",
                    "15-35s：插入 1-2 个原声证据片段，保留关键台词并加中文字幕。",
                    "35s+：旁白给出情绪落点，避免只堆片段没有故事。",
                ),
            ),
        ),
        ReferenceCase(
            id="food_micro_montage",
            title="探店美食复现",
            category="food_montage",
            reference_title="Food Promo Video - Manual Mode Productions",
            reference_url="https://www.youtube.com/watch?v=kRCH8kD1GD0",
            reference_channel="Manual Mode Productions",
            source_label="西安长探店素材",
            source_path=root / "output/effect-eval/travel-food-tour/downloads/xian-food-tour.mp4",
            reproduction_path=root / "output/effect-eval/travel-food-tour/project/renders/micro_food_highlights_subtitled.mp4",
            pattern=ReferencePattern(
                id="food_micro_montage",
                summary="用高频食物特写和动作镜头建立食欲，不依赖长旁白，字幕只服务信息理解。",
                required_elements=(
                    "visual_hook",
                    "food_closeups",
                    "fast_micro_cuts",
                    "texture_motion",
                    "short_captions",
                    "no_black_frames",
                ),
                shot_length_range=(0.8, 3.2),
                black_frames_allowed=False,
                narration_mode="minimal_or_none",
                original_audio_ratio=0.65,
                caption_style="short bottom Chinese captions, no paragraph blocks",
                breakdown=(
                    "0-2s：直接上最有冲击力的食物特写，避免开场解释。",
                    "2-18s：连续切 6-10 个微镜头，每个镜头只承担一个感官点。",
                    "18-35s：把制作动作、咀嚼反应、环境氛围交替穿插。",
                    "结尾：用最强视觉画面收束，而不是用黑底字幕总结。",
                ),
            ),
        ),
    ]


def build_case_report(
    case: ReferenceCase,
    *,
    repo_root: Path,
    run_blackdetect: bool = False,
) -> dict[str, Any]:
    source = _resolve_path(case.source_path, repo_root)
    reproduction = _resolve_path(case.reproduction_path, repo_root)
    media = probe_media(reproduction) if reproduction.exists() else {}
    black_segments = detect_black_segments(reproduction) if run_blackdetect and reproduction.exists() else []
    has_video = bool(media.get("video"))
    has_audio = bool(media.get("audio"))
    no_black_frames = bool(case.pattern.black_frames_allowed or not black_segments)
    checks = {
        "source_exists": _check(source.exists(), f"source: {_safe_relpath(source, repo_root)}"),
        "reproduction_exists": _check(reproduction.exists(), f"reproduction: {_safe_relpath(reproduction, repo_root)}"),
        "has_video_stream": _check(has_video, "final video has a video stream"),
        "has_audio_stream": _check(has_audio, "final video has an audio stream"),
        "no_black_frames": _check(no_black_frames, f"black segments detected: {len(black_segments)}"),
    }
    checks["machine_ready"] = _check(
        all(item["pass"] for key, item in checks.items() if key != "machine_ready"),
        "source, reproduction, streams and black-frame policy are all satisfied",
    )

    return {
        "id": case.id,
        "title": case.title,
        "category": case.category,
        "reference": {
            "title": case.reference_title,
            "url": case.reference_url,
            "embed_url": youtube_embed_url(case.reference_url),
            "channel": case.reference_channel,
        },
        "source": {
            "label": case.source_label,
            "path": _safe_relpath(source, repo_root),
            "exists": source.exists(),
        },
        "reproduction": {
            "path": _safe_relpath(reproduction, repo_root),
            "package_path": f"videos/{case.id}.mp4",
            "exists": reproduction.exists(),
        },
        "pattern": pattern_to_dict(case.pattern),
        "checks": checks,
        "media": media,
        "black_segments": black_segments,
        "tasks": build_reproduction_tasks(case),
    }


def build_reproduction_tasks(case: ReferenceCase) -> list[dict[str, str]]:
    if case.category == "movie_recap":
        return [
            {"stage": "reference_breakdown", "task": "逐秒拆解参考视频的 hook、旁白、证据片段和字幕位置。"},
            {"stage": "shot_selection", "task": "从剧情素材中按因果顺序选择人物动作画面，旁白段不得使用黑屏或无信息画面。"},
            {"stage": "voiceover", "task": "生成连续中文解说，原声只保留关键台词证据，混音时自动 ducking。"},
            {"stage": "comparison", "task": "在对比页标注：开场冲突、剧情递进、字幕可读性、黑屏检测是否接近参考。"},
        ]
    return [
        {"stage": "reference_breakdown", "task": "拆解参考美食短片的镜头长度、食物特写密度、音乐/环境声比例。"},
        {"stage": "shot_selection", "task": "从长探店视频中选择高频食物微镜头，优先质感、动作、反应，不先讲道理。"},
        {"stage": "captioning", "task": "字幕只保留短句信息点，避免段落字幕遮挡食物画面。"},
        {"stage": "comparison", "task": "在对比页标注：首帧冲击力、微镜头数量、节奏、黑屏检测是否接近参考。"},
    ]


def pattern_to_dict(pattern: ReferencePattern) -> dict[str, Any]:
    return {
        "id": pattern.id,
        "summary": pattern.summary,
        "required_elements": list(pattern.required_elements),
        "shot_length_range": list(pattern.shot_length_range),
        "black_frames_allowed": pattern.black_frames_allowed,
        "narration_mode": pattern.narration_mode,
        "original_audio_ratio": pattern.original_audio_ratio,
        "caption_style": pattern.caption_style,
        "breakdown": list(pattern.breakdown),
    }


def write_benchmark_package(
    *,
    repo_root: Path,
    output_dir: Path,
    cases: Iterable[ReferenceCase] | None = None,
    run_blackdetect: bool = True,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "videos").mkdir(exist_ok=True)
    (output_dir / "cases").mkdir(exist_ok=True)
    reports: list[dict[str, Any]] = []
    for case in cases or default_reference_cases(repo_root):
        report = build_case_report(case, repo_root=repo_root, run_blackdetect=run_blackdetect)
        reports.append(report)
        case_dir = output_dir / "cases" / case.id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "reference_pattern.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (case_dir / "reference_analysis.html").write_text(
            build_reference_analysis_html(case, report),
            encoding="utf-8",
        )
        source_video = _resolve_path(case.reproduction_path, repo_root)
        if source_video.exists():
            shutil.copy2(source_video, output_dir / "videos" / f"{case.id}.mp4")
    (output_dir / "benchmark_report.json").write_text(
        json.dumps({"cases": reports}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "index.html").write_text(build_benchmark_html(reports), encoding="utf-8")
    return {"index": str(output_dir / "index.html"), "cases": reports}


def build_reference_analysis_html(case: ReferenceCase, report: dict[str, Any]) -> str:
    pattern = report["pattern"]
    breakdown = "".join(f"<li>{html.escape(item)}</li>" for item in pattern["breakdown"])
    tasks = "".join(
        f"<tr><td>{html.escape(item['stage'])}</td><td>{html.escape(item['task'])}</td></tr>"
        for item in report["tasks"]
    )
    checks = "".join(
        f"<tr><td>{html.escape(key)}</td><td>{'PASS' if value['pass'] else 'FAIL'}</td><td>{html.escape(value['note'])}</td></tr>"
        for key, value in report["checks"].items()
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(case.title)} · Reference Analysis</title>
  <style>{_base_css()}</style>
</head>
<body>
  <main>
    <header class="hero small">
      <p class="eyebrow">Reference Reproduction Case</p>
      <h1>{html.escape(case.title)}</h1>
      <p class="lead">目标不是自由发挥，而是拆解参考成品，再用 LogicCut 的素材和模块复现同一种剪辑结构。</p>
    </header>
    <section class="grid two">
      <article class="panel">
        <h2>参考视频</h2>
        <p><strong>{html.escape(case.reference_title)}</strong></p>
        <p class="muted">Channel：{html.escape(case.reference_channel)}</p>
        <p><a href="{html.escape(case.reference_url)}">{html.escape(case.reference_url)}</a></p>
      </article>
      <article class="panel">
        <h2>复现素材</h2>
        <p><strong>{html.escape(case.source_label)}</strong></p>
        <p class="muted">{html.escape(report["source"]["path"])}</p>
        <p class="muted">当前复现输出：{html.escape(report["reproduction"]["path"])}</p>
      </article>
    </section>
    <section class="panel">
      <h2>目标模式</h2>
      <p>{html.escape(pattern["summary"])}</p>
      <ul>{breakdown}</ul>
    </section>
    <section class="panel">
      <h2>复现任务</h2>
      <table><tbody>{tasks}</tbody></table>
    </section>
    <section class="panel">
      <h2>机器检查</h2>
      <table><tbody>{checks}</tbody></table>
    </section>
  </main>
</body>
</html>
"""


def build_benchmark_html(reports: list[dict[str, Any]]) -> str:
    cards = "\n".join(_case_card(report) for report in reports)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LogicCut Reference Reproduction Benchmark</title>
  <style>{_base_css()}</style>
</head>
<body>
  <main>
    <header class="hero">
      <p class="eyebrow">LogicCut Benchmark</p>
      <h1>先复现别人做好的视频，再扩展自己的剪辑能力</h1>
      <p class="lead">这个页面固定 reference video、源素材、复现任务和机器检查项。当前复现输出先作为 baseline，用来暴露差距；后续每次优化都必须回到这里对照。</p>
      <div class="metrics">
        <div><strong>{len(reports)}</strong><span>具体复现 case</span></div>
        <div><strong>0</strong><span>允许黑屏数量</span></div>
        <div><strong>2</strong><span>必须对照的维度：结构与视觉</span></div>
      </div>
    </header>
    {cards}
  </main>
</body>
</html>
"""


def _case_card(report: dict[str, Any]) -> str:
    embed = html.escape(report["reference"]["embed_url"])
    title = html.escape(report["title"])
    case_id = html.escape(report["id"])
    video = html.escape(report["reproduction"]["package_path"])
    tasks = "".join(f"<li>{html.escape(item['task'])}</li>" for item in report["tasks"])
    checks = "".join(
        f"<span class=\"check {'ok' if value['pass'] else 'bad'}\">{html.escape(key)}: {'PASS' if value['pass'] else 'FAIL'}</span>"
        for key, value in report["checks"].items()
    )
    return f"""
    <section class="case">
      <div class="case-head">
        <div>
          <h2>{title}</h2>
          <p>{html.escape(report["pattern"]["summary"])}</p>
        </div>
        <a class="button" href="cases/{case_id}/reference_analysis.html">reference_analysis.html</a>
      </div>
      <div class="compare">
        <article>
          <h3>参考成品</h3>
          <iframe src="{embed}" title="{html.escape(report['reference']['title'])}" allowfullscreen></iframe>
          <p class="muted">{html.escape(report["reference"]["title"])} · {html.escape(report["reference"]["channel"])}</p>
        </article>
        <article>
          <h3>LogicCut 当前复现 baseline</h3>
          <video controls preload="metadata" src="{video}"></video>
          <p class="muted">{html.escape(report["reproduction"]["path"])}</p>
        </article>
      </div>
      <div class="grid two">
        <article class="panel">
          <h3>复现任务</h3>
          <ul>{tasks}</ul>
        </article>
        <article class="panel">
          <h3>机器检查</h3>
          <div class="checks">{checks}</div>
        </article>
      </div>
    </section>
"""


def youtube_embed_url(url: str) -> str:
    match = re.search(r"(?:v=|shorts/|youtu\.be/)([A-Za-z0-9_-]{6,})", url)
    video_id = match.group(1) if match else url.rstrip("/").rsplit("/", 1)[-1]
    return f"https://www.youtube.com/embed/{video_id}"


def parse_blackdetect_output(text: str) -> list[dict[str, float]]:
    segments: list[dict[str, float]] = []
    pattern = re.compile(
        r"black_start:(?P<start>[0-9.]+)\s+black_end:(?P<end>[0-9.]+)\s+black_duration:(?P<duration>[0-9.]+)"
    )
    for match in pattern.finditer(text):
        segments.append(
            {
                "start": float(match.group("start")),
                "end": float(match.group("end")),
                "duration": float(match.group("duration")),
            }
        )
    return segments


def detect_black_segments(path: Path, *, min_duration: float = 0.45, pixel_threshold: float = 0.10) -> list[dict[str, float]]:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vf",
            f"blackdetect=d={min_duration}:pix_th={pixel_threshold}",
            "-an",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return parse_blackdetect_output(proc.stderr + "\n" + proc.stdout)


def probe_media(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()}
    raw = json.loads(proc.stdout)
    streams = raw.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    return {
        "duration": float(raw.get("format", {}).get("duration", 0.0) or 0.0),
        "size": int(raw.get("format", {}).get("size", 0) or 0),
        "video": {
            "codec": video.get("codec_name"),
            "width": video.get("width"),
            "height": video.get("height"),
        }
        if video
        else None,
        "audio": {
            "codec": audio.get("codec_name"),
            "channels": audio.get("channels"),
            "sample_rate": audio.get("sample_rate"),
        }
        if audio
        else None,
    }


def _resolve_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _safe_relpath(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _check(pass_value: bool, note: str) -> dict[str, Any]:
    return {"pass": bool(pass_value), "note": note}


def _base_css() -> str:
    return """
    :root {
      color-scheme: dark;
      --bg: #070910;
      --panel: rgba(18, 24, 43, 0.92);
      --line: rgba(126, 214, 255, 0.22);
      --cyan: #38e8ff;
      --blue: #326dff;
      --violet: #9b5cff;
      --text: #f4f7ff;
      --muted: #aab7d4;
      --bad: #ff7d7d;
      --ok: #73f4ad;
      font-family: Inter, "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background:
        radial-gradient(circle at 15% 5%, rgba(155, 92, 255, .24), transparent 27%),
        radial-gradient(circle at 85% 8%, rgba(50, 109, 255, .22), transparent 30%),
        linear-gradient(180deg, #05060b 0%, var(--bg) 100%);
      color: var(--text);
    }
    main { width: min(1240px, calc(100% - 40px)); margin: 0 auto; padding: 44px 0 72px; }
    .hero { min-height: 420px; display: grid; align-content: center; border-bottom: 1px solid var(--line); }
    .hero.small { min-height: 260px; }
    .eyebrow { margin: 0 0 14px; color: var(--cyan); font-weight: 850; }
    h1 { margin: 0; max-width: 980px; font-size: clamp(40px, 6vw, 76px); line-height: 1.02; letter-spacing: 0; }
    h2 { margin: 0; font-size: clamp(24px, 3vw, 34px); letter-spacing: 0; }
    h3 { margin: 0 0 10px; font-size: 17px; letter-spacing: 0; }
    p { margin: 0; line-height: 1.68; }
    a { color: var(--cyan); text-decoration: none; }
    .lead { max-width: 860px; margin-top: 18px; color: var(--muted); font-size: 18px; }
    .metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 28px; }
    .metrics div, .panel, .case { border: 1px solid var(--line); background: var(--panel); }
    .metrics div { padding: 16px; min-height: 102px; }
    .metrics strong { display: block; font-size: 28px; }
    .metrics span, .muted { color: var(--muted); }
    .case { margin-top: 34px; overflow: hidden; }
    .case-head { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 18px; align-items: center; padding: 22px; border-bottom: 1px solid var(--line); background: linear-gradient(90deg, rgba(56,232,255,.10), transparent); }
    .case-head p { margin-top: 8px; color: var(--muted); }
    .button { display: inline-flex; align-items: center; min-height: 40px; padding: 0 14px; background: linear-gradient(90deg, var(--blue), var(--violet)); color: white; font-weight: 850; }
    .compare { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0; }
    .compare article { padding: 20px; }
    .compare article + article { border-left: 1px solid var(--line); }
    iframe, video { display: block; width: 100%; aspect-ratio: 16/9; border: 1px solid rgba(255,255,255,.11); background: #02040a; }
    .grid.two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }
    .panel { padding: 18px; }
    ul { margin: 12px 0 0; padding-left: 20px; color: var(--muted); line-height: 1.65; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    td { border-top: 1px solid var(--line); padding: 10px 8px; color: var(--muted); vertical-align: top; }
    .checks { display: flex; flex-wrap: wrap; gap: 8px; }
    .check { display: inline-flex; min-height: 30px; align-items: center; padding: 4px 9px; border: 1px solid var(--line); color: var(--muted); }
    .check.ok { color: var(--ok); border-color: rgba(115,244,173,.34); }
    .check.bad { color: var(--bad); border-color: rgba(255,125,125,.34); }
    @media (max-width: 900px) {
      .metrics, .compare, .grid.two, .case-head { grid-template-columns: 1fr; }
      .compare article + article { border-left: 0; border-top: 1px solid var(--line); }
    }
    """
