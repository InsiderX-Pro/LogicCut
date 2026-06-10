from __future__ import annotations

import html
import json
import os
import shutil
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from .media import concat_videos_reencode
from .reference_benchmark import detect_black_segments, probe_media


LLMFn = Callable[[str], str]


@dataclass(frozen=True)
class AdapterPOC:
    id: str
    adapter: str
    repo_path: Path
    source_path: Path
    highlights_path: Path
    output_video: Path
    capability: str
    integration_notes: tuple[str, ...]
    transcript_path: Path | None = None
    selector_output: Path | None = None
    use_llm_selector: bool = False


@dataclass(frozen=True, repr=False)
class OpenAICompatibleSettings:
    api_key: str
    base_url: str | None
    model: str

    def __repr__(self) -> str:
        return (
            "OpenAICompatibleSettings("
            "api_key='***REDACTED***', "
            f"base_url={self.base_url!r}, "
            f"model={self.model!r})"
        )


def default_adapter_pocs(repo_root: Path, output_dir: Path) -> list[AdapterPOC]:
    ai_shorts_repo = repo_root / "third_party" / "AI-Youtube-Shorts-Generator"
    return [
        AdapterPOC(
            id="ai_shorts_llm_food_vertical",
            adapter="AI-Youtube-Shorts-Generator",
            repo_path=ai_shorts_repo,
            source_path=repo_root / "output/effect-eval/travel-food-tour/downloads/xian-food-tour.mp4",
            highlights_path=output_dir / "ai_shorts_llm_food_vertical" / "selected_highlights.json",
            output_video=output_dir / "ai_shorts_llm_food_vertical" / "montage.mp4",
            capability="AI-Youtube-Shorts LLM virality selector + OpenCV face-aware 9:16 crop",
            integration_notes=(
                "实际调用 third_party/AI-Youtube-Shorts-Generator/shorts_generator/highlights.py 的 get_highlights 选段逻辑。",
                "LLM 后端由 LogicCut 适配到本地 ChatGPT/OpenAI-compatible API；key 只从本机 env 文件读取，不写入仓库。",
                "裁切仍调用 third_party/AI-Youtube-Shorts-Generator/shorts_generator/local/clipper.py，方便单独评估选段和裁切质量。",
            ),
            transcript_path=repo_root / "output/effect-eval/travel-food-tour/project/assets/source_transcript.json",
            selector_output=output_dir / "ai_shorts_llm_food_vertical" / "selected_highlights.json",
            use_llm_selector=True,
        ),
        AdapterPOC(
            id="ai_shorts_llm_podcast_vertical",
            adapter="AI-Youtube-Shorts-Generator",
            repo_path=ai_shorts_repo,
            source_path=repo_root / "output/effect-eval/podcast-karpathy/source_full_720p.mp4",
            highlights_path=output_dir / "ai_shorts_llm_podcast_vertical" / "selected_highlights.json",
            output_video=output_dir / "ai_shorts_llm_podcast_vertical" / "montage.mp4",
            capability="AI-Youtube-Shorts LLM virality selector + OpenCV face-aware 9:16 crop",
            integration_notes=(
                "实际调用 third_party/AI-Youtube-Shorts-Generator/shorts_generator/highlights.py 的 get_highlights 选段逻辑。",
                "这个 case 用来验证人物访谈/播客素材中 LLM 是否会选择更强 hook，而不是固定复用 LogicCut 旧高光。",
                "如果 LLM 选段改善明显，下一步把 selector 抽成 HighlightSelectorAdapter；如果裁切仍差，再替换 cropper。",
            ),
            transcript_path=repo_root / "output/effect-eval/podcast-karpathy/project/assets/source_transcript.json",
            selector_output=output_dir / "ai_shorts_llm_podcast_vertical" / "selected_highlights.json",
            use_llm_selector=True,
        ),
    ]


def run_external_adapter_pocs(
    *,
    repo_root: Path,
    output_dir: Path,
    limit: int = 4,
    render: bool = True,
    run_blackdetect: bool = True,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pocs = default_adapter_pocs(repo_root, output_dir)
    if render:
        for poc in pocs:
            if poc.use_llm_selector:
                render_ai_shorts_llm_selector_poc(poc, limit=limit, repo_root=repo_root)
            else:
                render_ai_shorts_cropper_poc(poc, limit=limit)
    reports = [summarize_adapter_poc(poc, repo_root=repo_root, run_blackdetect=run_blackdetect) for poc in pocs]
    index = write_adapter_showcase(reports, output_dir=output_dir, repo_root=repo_root)
    return {"index": str(index), "adapters": reports}


def render_ai_shorts_cropper_poc(poc: AdapterPOC, *, limit: int) -> Path:
    if str(poc.repo_path) not in sys.path:
        sys.path.insert(0, str(poc.repo_path))
    _ensure_dotenv_importable()
    from shorts_generator.local.clipper import crop_highlights_local  # type: ignore

    out_dir = poc.output_video.parent
    clips_dir = out_dir / "clips"
    _prepare_clean_clips_dir(clips_dir)
    os.environ["LOCAL_OUTPUT_DIR"] = str(clips_dir)

    highlights = load_highlights(poc.highlights_path, limit=limit)
    crop_highlights_local(str(poc.source_path), highlights, aspect_ratio="9:16", out_dir=str(clips_dir))
    clips = sorted(path for path in clips_dir.glob("short_*.mp4") if path.stat().st_size > 0)
    if not clips:
        raise RuntimeError(f"{poc.id}: external cropper produced no clips")
    concat_videos_reencode(clips, poc.output_video)
    return poc.output_video


def render_ai_shorts_llm_selector_poc(poc: AdapterPOC, *, limit: int, repo_root: Path) -> Path:
    if poc.transcript_path is None or poc.selector_output is None:
        raise RuntimeError(f"{poc.id}: transcript_path and selector_output are required for LLM selector mode")
    transcript = json.loads(poc.transcript_path.read_text(encoding="utf-8"))
    selection = call_ai_shorts_highlight_selector(
        transcript,
        num_clips=limit,
        output_path=poc.selector_output,
        repo_root=repo_root,
    )
    selected = selection["top_highlights"]
    if not selected:
        raise RuntimeError(f"{poc.id}: LLM selector produced no highlights")

    out_dir = poc.output_video.parent
    clips_dir = out_dir / "clips"
    _prepare_clean_clips_dir(clips_dir)
    if str(poc.repo_path) not in sys.path:
        sys.path.insert(0, str(poc.repo_path))
    _ensure_dotenv_importable()
    from shorts_generator.local.clipper import crop_highlights_local  # type: ignore

    os.environ["LOCAL_OUTPUT_DIR"] = str(clips_dir)
    crop_highlights_local(str(poc.source_path), selected, aspect_ratio="9:16", out_dir=str(clips_dir))
    clips = sorted(path for path in clips_dir.glob("short_*.mp4") if path.stat().st_size > 0)
    if not clips:
        raise RuntimeError(f"{poc.id}: external cropper produced no clips")
    concat_videos_reencode(clips, poc.output_video)
    return poc.output_video


def call_ai_shorts_highlight_selector(
    transcript: dict[str, Any],
    *,
    num_clips: int,
    output_path: Path,
    repo_root: Path,
    llm_fn: LLMFn | None = None,
) -> dict[str, Any]:
    third_party = repo_root / "third_party" / "AI-Youtube-Shorts-Generator"
    if str(third_party) not in sys.path:
        sys.path.insert(0, str(third_party))
    _ensure_dotenv_importable()
    try:
        from shorts_generator.highlights import get_highlights  # type: ignore

        result = get_highlights(transcript, num_clips=num_clips, llm_fn=llm_fn or call_openai_compatible_llm)
    except ModuleNotFoundError:
        if llm_fn is None:
            raise RuntimeError(
                "AI-Youtube-Shorts-Generator is not installed. Clone it into "
                "third_party/AI-Youtube-Shorts-Generator or pass llm_fn for the local selector fallback."
            )
        result = _fallback_highlight_selector(transcript, num_clips=num_clips, llm_fn=llm_fn)
    all_highlights = repair_highlight_timestamps(
        [normalize_highlight(item) for item in result.get("highlights", []) if isinstance(item, dict)],
        duration=float(transcript.get("duration") or 0.0),
    )
    top_highlights = sorted(all_highlights, key=lambda item: int(item.get("score", 0)), reverse=True)[: max(1, num_clips)]
    payload = {
        "selector": "ai-youtube-shorts-generator",
        "num_clips": num_clips,
        "all_highlights": all_highlights,
        "top_highlights": top_highlights,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _fallback_highlight_selector(transcript: dict[str, Any], *, num_clips: int, llm_fn: LLMFn) -> dict[str, Any]:
    prompt = json.dumps(
        {
            "task": "Select short-video highlights from the transcript.",
            "num_clips": num_clips,
            "transcript": transcript,
            "required_json": {
                "highlights": [
                    {
                        "title": "string",
                        "start_time": 0,
                        "end_time": 10,
                        "score": 90,
                        "hook_sentence": "string",
                        "virality_reason": "string",
                    }
                ]
            },
        },
        ensure_ascii=False,
    )
    raw = llm_fn(prompt)
    try:
        data = json.loads(_extract_json_object(raw))
    except Exception as exc:
        raise RuntimeError("local highlight selector fallback returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise RuntimeError("local highlight selector fallback must return a JSON object")
    return data


def _extract_json_object(raw: str) -> str:
    text = extract_chat_completion_text(raw).strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    raise ValueError("no JSON object found")


def repair_highlight_timestamps(highlights: list[dict[str, Any]], *, duration: float) -> list[dict[str, Any]]:
    """Repair AI-Youtube-Shorts long-video highlights that receive a duplicate chunk offset."""
    if duration <= 0:
        return highlights
    repaired: list[dict[str, Any]] = []
    chunk_step_seconds = 1140.0
    for item in highlights:
        start = float(item.get("start_time", 0.0))
        end = float(item.get("end_time", start))
        while start >= duration and end > duration and start - chunk_step_seconds >= 0:
            start -= chunk_step_seconds
            end -= chunk_step_seconds
        if end > duration and start < duration:
            end = duration
        if start < 0 or end <= start or start >= duration:
            continue
        fixed = dict(item)
        fixed["start_time"] = round(start, 3)
        fixed["end_time"] = round(end, 3)
        repaired.append(fixed)
    return repaired


def call_openai_compatible_llm(prompt: str, settings: OpenAICompatibleSettings | None = None) -> str:
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise RuntimeError("openai is required for ChatGPT-compatible highlight selection") from exc

    settings = settings or load_openai_compatible_settings()
    kwargs: dict[str, Any] = {"api_key": settings.api_key}
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    client = OpenAI(**kwargs)
    response = client.chat.completions.create(
        model=settings.model,
        messages=[{"role": "user", "content": prompt}],
    )
    return extract_chat_completion_text(response)


def extract_chat_completion_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return message["content"]
                if isinstance(first.get("text"), str):
                    return first["text"]
        for key in ("content", "text", "output"):
            if isinstance(response.get(key), str):
                return response[key]
    choices = getattr(response, "choices", None)
    if choices:
        first = choices[0]
        message = getattr(first, "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
        text = getattr(first, "text", None)
        if isinstance(text, str):
            return text
    return str(response)


def load_openai_compatible_settings(
    *,
    env: dict[str, str] | None = None,
    env_file: Path | None = None,
) -> OpenAICompatibleSettings:
    runtime_env = dict(os.environ if env is None else env)
    values: dict[str, str] = {}
    for candidate in _openai_env_candidates(runtime_env, env_file):
        if candidate.exists():
            values.update(_read_env_file(candidate))
            break
    values.update({key: value for key, value in runtime_env.items() if value})

    api_key = _first_env(values, "LOGICCUT_OPENAI_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY")
    base_url = _first_env(values, "LOGICCUT_OPENAI_BASE_URL", "OPENAI_BASE_URL", "CODEX_THIRD_BASE_URL")
    model = _first_env(values, "LOGICCUT_OPENAI_MODEL", "OPENAI_MODEL", "CODEX_THIRD_MODEL", "AZURE_OPENAI_MODEL")
    if not api_key:
        raise RuntimeError(
            "OpenAI-compatible API key not found. Set OPENAI_API_KEY or LOGICCUT_OPENAI_API_KEY, "
            "or point LOGICCUT_LLM_ENV_FILE to a local env file."
        )
    return OpenAICompatibleSettings(
        api_key=api_key,
        base_url=base_url or None,
        model=model or "gpt-4o-mini",
    )


def normalize_highlight(raw: dict[str, Any]) -> dict[str, Any]:
    start = raw.get("start_time", raw.get("start"))
    end = raw.get("end_time", raw.get("end"))
    if start is None or end is None:
        raise ValueError(f"highlight missing start/end: {raw}")
    return {
        "title": str(raw.get("title") or "Untitled highlight"),
        "start_time": float(start),
        "end_time": float(end),
        "score": int(raw.get("score", 0) or 0),
        "hook_sentence": str(raw.get("hook_sentence") or raw.get("title") or ""),
        "virality_reason": str(raw.get("virality_reason") or raw.get("reason") or ""),
    }


def load_highlights(path: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("items") or data.get("highlights") or data.get("expanded_highlights") or []
        if isinstance(items, dict):
            items = items.get("items") or []
    else:
        items = []
    if not isinstance(items, list):
        raise ValueError(f"unsupported highlights shape in {path}")
    normalized = [normalize_highlight(item) for item in items if isinstance(item, dict)]
    return normalized[: max(1, limit)]


def summarize_adapter_poc(
    poc: AdapterPOC,
    *,
    repo_root: Path,
    run_blackdetect: bool = True,
) -> dict[str, Any]:
    output = _resolve_path(poc.output_video, repo_root)
    source = _resolve_path(poc.source_path, repo_root)
    repo = _resolve_path(poc.repo_path, repo_root)
    highlights = _resolve_path(poc.highlights_path, repo_root)
    transcript = _resolve_path(poc.transcript_path, repo_root) if poc.transcript_path else None
    selected_highlights = _read_selected_highlights(highlights)
    media = probe_media(output) if output.exists() else {}
    black_segments = detect_black_segments(output) if run_blackdetect and output.exists() else []
    checks = {
        "repo_exists": _check(repo.exists(), f"repo: {_safe_relpath(repo, repo_root)}"),
        "source_exists": _check(source.exists(), f"source: {_safe_relpath(source, repo_root)}"),
        "highlights_exists": _check(highlights.exists(), f"highlights: {_safe_relpath(highlights, repo_root)}"),
        "output_exists": _check(output.exists(), f"output: {_safe_relpath(output, repo_root)}"),
        "has_video_stream": _check(bool(media.get("video")), "output has a video stream"),
        "has_audio_stream": _check(bool(media.get("audio")), "output has an audio stream"),
        "no_black_frames": _check(not black_segments, f"black segments detected: {len(black_segments)}"),
    }
    if transcript is not None:
        checks["transcript_exists"] = _check(transcript.exists(), f"transcript: {_safe_relpath(transcript, repo_root)}")
    if poc.use_llm_selector:
        checks["has_llm_selected_highlights"] = _check(bool(selected_highlights), f"selected highlights: {len(selected_highlights)}")
        rendered_clip_count = _rendered_clip_count(output.parent / "clips")
        checks["rendered_all_selected_clips"] = _check(
            rendered_clip_count >= len(selected_highlights),
            f"rendered clips: {rendered_clip_count}/{len(selected_highlights)}",
        )
    checks["machine_ready"] = _check(
        all(item["pass"] for key, item in checks.items() if key != "machine_ready"),
        "repo, source, highlights, output and media checks are satisfied",
    )
    return {
        "id": poc.id,
        "adapter": poc.adapter,
        "repo": _safe_relpath(repo, repo_root),
        "source": _safe_relpath(source, repo_root),
        "highlights": _safe_relpath(highlights, repo_root),
        "capability": poc.capability,
        "integration_notes": list(poc.integration_notes),
        "output": {
            "path": _safe_relpath(output, repo_root),
            "package_path": f"videos/{poc.id}.mp4",
            "exists": output.exists(),
        },
        "checks": checks,
        "media": media,
        "black_segments": black_segments,
        "selected_highlights": selected_highlights,
    }


def write_adapter_showcase(
    reports: Iterable[dict[str, Any]],
    *,
    output_dir: Path,
    repo_root: Path,
) -> Path:
    reports = list(reports)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "videos").mkdir(exist_ok=True)
    for report in reports:
        source = repo_root / report["output"]["path"]
        if source.exists():
            shutil.copy2(source, output_dir / report["output"]["package_path"])
    (output_dir / "adapter_poc_report.json").write_text(
        json.dumps({"adapters": reports}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    index = output_dir / "index.html"
    index.write_text(build_adapter_showcase_html(reports), encoding="utf-8")
    return index


def build_adapter_showcase_html(reports: list[dict[str, Any]]) -> str:
    cards = "\n".join(_report_card(report) for report in reports)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LogicCut 外部高光仓库 POC</title>
  <style>{_css()}</style>
</head>
<body>
  <main>
    <header class="hero">
      <p class="eyebrow">External Adapter POC</p>
      <h1>先跑通别人做好的高光能力，再决定怎么融入 LogicCut</h1>
      <p class="lead">本页记录每个外部仓库在 LogicCut 素材上的真实输出、使用的能力边界、机器检查结果和后续融合建议。</p>
    </header>
    {cards}
  </main>
</body>
</html>
"""


def _report_card(report: dict[str, Any]) -> str:
    checks = "".join(
        f"<span class=\"check {'ok' if item['pass'] else 'bad'}\">{html.escape(key)}: {'PASS' if item['pass'] else 'FAIL'}</span>"
        for key, item in report.get("checks", {}).items()
    )
    notes = "".join(f"<li>{html.escape(note)}</li>" for note in report.get("integration_notes", []))
    highlights = "".join(
        (
            "<li>"
            f"<strong>{html.escape(str(item.get('score', '')))}</strong> "
            f"{html.escape(str(item.get('title', '')))} "
            f"<span>{html.escape(_format_range(item))}</span>"
            f"<em>{html.escape(str(item.get('virality_reason', '')))}</em>"
            "</li>"
        )
        for item in report.get("selected_highlights", [])[:8]
    )
    media = report.get("media") or {}
    video = media.get("video") or {}
    dimensions = ""
    if video:
        dimensions = f"{video.get('width')}x{video.get('height')} · {media.get('duration', 0):.1f}s"
    return f"""
    <section class="card">
      <div class="head">
        <div>
          <h2>{html.escape(report['id'])}</h2>
          <p>{html.escape(report['adapter'])} · {html.escape(report['capability'])}</p>
        </div>
        <strong>{html.escape(dimensions)}</strong>
      </div>
      <div class="grid">
        <div>
          <video controls preload="metadata" src="{html.escape(report['output']['package_path'])}"></video>
          <p class="muted">{html.escape(report['output']['path'])}</p>
        </div>
        <div class="panel">
          <h3>融合记录</h3>
          <ul>{notes}</ul>
          <h3>LLM 选段</h3>
          <ol class="highlights">{highlights or '<li>暂无选段报告</li>'}</ol>
          <h3>机器检查</h3>
          <div class="checks">{checks}</div>
        </div>
      </div>
    </section>
"""


def _resolve_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _safe_relpath(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _check(pass_value: bool, note: str) -> dict[str, Any]:
    return {"pass": bool(pass_value), "note": note}


def _read_selected_highlights(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = data.get("top_highlights") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _format_range(item: dict[str, Any]) -> str:
    try:
        return f"{float(item.get('start_time', 0.0)):.1f}s-{float(item.get('end_time', 0.0)):.1f}s"
    except Exception:
        return ""


def _prepare_clean_clips_dir(clips_dir: Path) -> None:
    clips_dir.mkdir(parents=True, exist_ok=True)
    for pattern in ("short_*.mp4", "short_*.mp4.cut.mp4"):
        for path in clips_dir.glob(pattern):
            path.unlink(missing_ok=True)


def _rendered_clip_count(clips_dir: Path) -> int:
    if not clips_dir.exists():
        return 0
    return len([path for path in clips_dir.glob("short_*.mp4") if path.stat().st_size > 0])


def _openai_env_candidates(runtime_env: dict[str, str], env_file: Path | None) -> list[Path]:
    candidates: list[Path] = []
    if env_file is not None:
        candidates.append(env_file)
    configured = runtime_env.get("LOGICCUT_LLM_ENV_FILE")
    if configured:
        candidates.append(Path(configured).expanduser())
    return candidates


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = _unquote_env_value(value.strip())
    return values


def _unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _first_env(values: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = str(values.get(key) or "").strip()
        if value:
            return value
    return ""


def _ensure_dotenv_importable() -> None:
    try:
        import dotenv  # noqa: F401
    except ImportError:
        fallback = types.ModuleType("dotenv")
        fallback.load_dotenv = lambda *args, **kwargs: False  # type: ignore[attr-defined]
        sys.modules.setdefault("dotenv", fallback)


def _css() -> str:
    return """
    :root { color-scheme: dark; --bg:#070910; --panel:#111827; --line:rgba(120,220,255,.24); --text:#f6f8ff; --muted:#a9b5d0; --cyan:#38e8ff; --ok:#77f0ae; --bad:#ff7d7d; font-family: Inter, "PingFang SC", "Microsoft YaHei", Arial, sans-serif; }
    * { box-sizing: border-box; }
    body { margin:0; background: radial-gradient(circle at 12% 4%, rgba(70,115,255,.24), transparent 28%), linear-gradient(180deg,#05060b,var(--bg)); color:var(--text); }
    main { width:min(1220px, calc(100% - 40px)); margin:0 auto; padding:44px 0 70px; }
    .hero { min-height:340px; display:grid; align-content:center; border-bottom:1px solid var(--line); }
    .eyebrow { color:var(--cyan); font-weight:850; }
    h1 { margin:0; max-width:980px; font-size:clamp(38px,5.7vw,72px); line-height:1.03; letter-spacing:0; }
    .lead { max-width:850px; margin-top:16px; color:var(--muted); font-size:18px; line-height:1.7; }
    .card { margin-top:30px; border:1px solid var(--line); background:rgba(17,24,39,.88); }
    .head { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:20px; align-items:end; padding:22px; border-bottom:1px solid var(--line); }
    .head h2 { margin:0; font-size:30px; letter-spacing:0; }
    .head p, .muted { color:var(--muted); }
    .grid { display:grid; grid-template-columns:minmax(0,1.15fr) minmax(320px,.85fr); gap:0; }
    .grid > div { padding:20px; }
    .panel { border-left:1px solid var(--line); }
    video { display:block; width:100%; aspect-ratio:9/16; max-height:720px; background:#02040a; border:1px solid rgba(255,255,255,.1); object-fit:contain; }
    h3 { margin:0 0 10px; font-size:16px; color:var(--cyan); }
    ul { margin:0 0 22px; padding-left:20px; color:var(--muted); line-height:1.65; }
    ol.highlights { margin:0 0 22px; padding-left:22px; color:var(--text); line-height:1.5; }
    ol.highlights li { margin-bottom:10px; }
    ol.highlights strong { color:var(--ok); margin-right:8px; }
    ol.highlights span { display:block; color:var(--cyan); font-size:12px; margin-top:2px; }
    ol.highlights em { display:block; color:var(--muted); font-style:normal; margin-top:3px; }
    .checks { display:flex; flex-wrap:wrap; gap:8px; }
    .check { display:inline-flex; min-height:30px; align-items:center; padding:4px 9px; border:1px solid var(--line); color:var(--muted); }
    .check.ok { color:var(--ok); border-color:rgba(119,240,174,.34); }
    .check.bad { color:var(--bad); border-color:rgba(255,125,125,.34); }
    @media (max-width: 900px) { .head,.grid { grid-template-columns:1fr; } .panel { border-left:0; border-top:1px solid var(--line); } }
    """
