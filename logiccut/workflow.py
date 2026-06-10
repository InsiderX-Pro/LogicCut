from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .comments import create_comment_freeze_video, create_comment_narration_video, scrape_comments
from .download import download_video
from .merge import merge_videos
from .recipes import init_project, run_recipe
from .video_translate_refine import config_from_env, run_video_translate_refine


DEFAULT_TASKS = ["download", "comments", "comment-freeze", "merge"]


def parse_tasks(raw: str | None) -> list[str]:
    if not raw:
        return list(DEFAULT_TASKS)
    tasks = [item.strip() for item in raw.split(",") if item.strip()]
    if not tasks:
        return list(DEFAULT_TASKS)
    return tasks


def write_workflow_plan(
    *,
    project_dir: Path,
    tasks: list[str],
    url: str | None = None,
    input_video: Path | None = None,
    target_lang: str = "中文",
    theme: str = "auto",
    highlight_duration: int = 20,
    comment_duration: int = 20,
    comment_count: int = 30,
    plan_path: Path | None = None,
) -> dict[str, Any]:
    if not url and not input_video:
        raise ValueError("plan requires either --url or --input")
    project_dir.mkdir(parents=True, exist_ok=True)
    normalized_tasks = list(tasks)
    steps = _build_steps(
        project_dir=project_dir,
        tasks=normalized_tasks,
        url=url,
        input_video=input_video,
        target_lang=target_lang,
        theme=theme,
        highlight_duration=highlight_duration,
        comment_duration=comment_duration,
        comment_count=comment_count,
    )
    output = plan_path or project_dir / "logiccut_plan.json"
    plan = {
        "version": "0.3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_dir": str(project_dir),
        "source": {"url": url, "input": str(input_video) if input_video else None},
        "tasks": normalized_tasks,
        "options": {
            "target_lang": target_lang,
            "theme": theme,
            "highlight_duration": highlight_duration,
            "comment_duration": comment_duration,
            "comment_count": comment_count,
        },
        "steps": steps,
        "codex_notes": [
            "Review this plan before execution.",
            "For theme-opener, Codex may need to write theme_opener_plan.json after reading the generated prompt.",
            "Do not commit .env.local, cookies, API keys, model weights, or generated videos.",
        ],
    }
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"plan": str(output), "step_count": len(steps), "tasks": normalized_tasks}


def execute_workflow_plan(plan_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    project_dir = Path(plan["project_dir"])
    steps = plan.get("steps", [])
    if dry_run:
        return {
            "version": "0.3",
            "dry_run": True,
            "plan": str(plan_path),
            "steps": [{"id": step.get("id"), "command": step.get("command"), "args": step.get("args", {})} for step in steps],
        }

    context: dict[str, Any] = {"project_dir": str(project_dir)}
    results: list[dict[str, Any]] = []
    for step in steps:
        result = _execute_step(project_dir, step, context)
        context[step["id"]] = result
        results.append({"id": step["id"], "command": step["command"], "result": result})
    output = {
        "version": "0.3",
        "dry_run": False,
        "plan": str(plan_path),
        "results": results,
        "context": context,
    }
    execution_path = project_dir / "logiccut_execution.json"
    execution_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output["execution"] = str(execution_path)
    return output


def _build_steps(
    *,
    project_dir: Path,
    tasks: list[str],
    url: str | None,
    input_video: Path | None,
    target_lang: str,
    theme: str,
    highlight_duration: int,
    comment_duration: int,
    comment_count: int,
) -> list[dict[str, Any]]:
    source_ref = "${download.path}" if "download" in tasks and url else str(input_video) if input_video else "${download.path}"
    steps: list[dict[str, Any]] = []
    if "download" in tasks:
        if not url:
            raise ValueError("download task requires --url")
        steps.append(
            {
                "id": "download",
                "command": "download",
                "args": {"url": url, "output_dir": str(project_dir / "download"), "prefix": "source"},
            }
        )
    if "translate" in tasks or "translate-video" in tasks:
        steps.append(
            {
                "id": "translate",
                "command": "translate-video",
                "args": {
                    "input": source_ref,
                    "output_dir": str(project_dir / "translation"),
                    "tgt_lang": target_lang,
                    "burn_subtitles": True,
                },
            }
        )
    if "highlight" in tasks or "theme-opener" in tasks:
        steps.append(
            {
                "id": "init",
                "command": "init",
                "args": {"input": source_ref, "project_dir": str(project_dir / "project"), "title": "LogicCut V0.3 project"},
            }
        )
        steps.append(
            {
                "id": "theme-opener",
                "command": "run",
                "args": {
                    "project_dir": str(project_dir / "project"),
                    "recipe": "theme-opener",
                    "theme": theme,
                    "target_duration": highlight_duration,
                },
            }
        )
    if "comments" in tasks:
        if not url:
            raise ValueError("comments task requires --url")
        steps.append(
            {
                "id": "comments",
                "command": "comments",
                "args": {
                    "url": url,
                    "output_dir": str(project_dir / "comments"),
                    "limit": comment_count,
                    "screenshot_count": 8,
                },
            }
        )
    if "comment-freeze" in tasks:
        frame_duration = max(comment_duration / 8, 1.0)
        steps.append(
            {
                "id": "comment-freeze",
                "command": "comment-freeze",
                "args": {
                    "comments_json": str(project_dir / "comments" / "comments.json"),
                    "output_dir": str(project_dir / "comments" / "fast-cut-20s"),
                    "max_frames": 8,
                    "frame_duration": frame_duration,
                },
            }
        )
    if "comment-narration" in tasks:
        steps.append(
            {
                "id": "comment-narration",
                "command": "comment-narration",
                "args": {
                    "comments_json": str(project_dir / "comments" / "comments.json"),
                    "freeze_manifest": str(project_dir / "comments" / "fast-cut-20s" / "comment_freeze_manifest.json"),
                    "output_dir": str(project_dir / "comments" / "narration"),
                    "max_items": 5,
                },
            }
        )
    if "merge" in tasks:
        merge_inputs = _default_merge_inputs(project_dir, tasks)
        steps.append(
            {
                "id": "merge",
                "command": "merge",
                "args": {"inputs": merge_inputs, "output": str(project_dir / "final" / "final_remix.mp4")},
            }
        )
    return steps


def _default_merge_inputs(project_dir: Path, tasks: list[str]) -> list[str]:
    inputs: list[str] = []
    if "highlight" in tasks or "theme-opener" in tasks:
        inputs.append(str(project_dir / "project" / "renders" / "theme_opener" / "theme_opener.mp4"))
    if "comment-freeze" in tasks:
        inputs.append(str(project_dir / "comments" / "fast-cut-20s" / "comment_freeze_video.mp4"))
    if "comment-narration" in tasks:
        inputs.append(str(project_dir / "comments" / "narration" / "comment_narration_video.mp4"))
    if "translate" in tasks or "translate-video" in tasks:
        inputs.append(str(project_dir / "translation" / "final.mp4"))
    return inputs


def _execute_step(project_dir: Path, step: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    command = step["command"]
    args = _resolve_args(step.get("args", {}), context)
    if command == "download":
        result = download_video(args["url"], Path(args["output_dir"]), prefix=args.get("prefix"), cookies=_optional_path(args.get("cookies")))
        return {"path": str(result.path), "metadata": result.metadata}
    if command == "comments":
        return scrape_comments(
            args["url"],
            Path(args["output_dir"]),
            max_comments=int(args.get("limit", 50)),
            screenshot_count=int(args.get("screenshot_count", 4)),
        )
    if command == "comment-freeze":
        return create_comment_freeze_video(
            Path(args["comments_json"]),
            Path(args["output_dir"]),
            max_frames=int(args.get("max_frames", 8)),
            frame_duration=float(args.get("frame_duration", 2.5)),
        )
    if command == "comment-narration":
        return create_comment_narration_video(
            Path(args["comments_json"]),
            Path(args["freeze_manifest"]),
            Path(args["output_dir"]),
            max_items=int(args.get("max_items", 5)),
            allow_tts_fallback=bool(args.get("allow_tts_fallback", False)),
        )
    if command == "init":
        return init_project(Path(args["input"]), Path(args["project_dir"]), title=args.get("title"))
    if command == "run":
        return run_recipe(Path(args["project_dir"]), args["recipe"])
    if command == "translate-video":
        result = run_video_translate_refine(
            config_from_env(
                video=Path(args["input"]),
                output_dir=Path(args["output_dir"]),
                tgt_lang=args.get("tgt_lang"),
            )
        )
        return {
            "output_video": str(result.output_video),
            "manifest": str(result.manifest_path),
            "log": str(result.log_path),
        }
    if command == "merge":
        return merge_videos([Path(item) for item in args.get("inputs", [])], Path(args["output"]))
    raise ValueError(f"unknown workflow command: {command}")


def _resolve_args(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_args(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_args(item, context) for item in value]
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return _lookup_context(value[2:-1], context)
    return value


def _lookup_context(path: str, context: dict[str, Any]) -> Any:
    current: Any = context
    for part in path.split("."):
        current = current[part]
    return current


def _optional_path(value: str | None) -> Path | None:
    return Path(value) if value else None
