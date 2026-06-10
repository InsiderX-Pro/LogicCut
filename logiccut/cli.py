from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .capabilities import build_capabilities, build_guide, supported_guide_tasks
from .comments import create_comment_freeze_video, create_comment_narration_video, scrape_comments
from .doctor import run_doctor
from .download import download_video
from .external_adapter_benchmark import run_external_adapter_pocs
from .manifest import load_manifest
from .media import ensure_sample_video
from .merge import merge_videos
from .reference_benchmark import default_reference_cases, write_benchmark_package
from .recipes import init_project, run_recipe
from .translation.pipeline import LocalTranslationConfig, run_local_translation
from .translation.setup import run_translation_setup
from .video_translate_refine import build_command, config_from_env, run_video_translate_refine
from .workflow import execute_workflow_plan, parse_tasks, write_workflow_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="logiccut")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("capabilities", help="Print Codex-facing LogicCut capabilities")

    guide = subparsers.add_parser("guide", help="Print task specific Codex usage guide")
    guide.add_argument("--task", required=True, choices=supported_guide_tasks())

    doctor = subparsers.add_parser("doctor", help="Check local LogicCut environment")
    doctor.add_argument("--profile", choices=["lite", "creator", "full"], default="lite")
    doctor.add_argument("--json", action="store_true", help="Print JSON output")

    setup = subparsers.add_parser("setup", help="Install or inspect LogicCut component dependencies")
    setup_subparsers = setup.add_subparsers(dest="setup_component", required=True)
    setup_translation = setup_subparsers.add_parser("translation", help="Prepare the local translation pipeline")
    setup_translation.add_argument("--profile", choices=["minimal", "asr", "full"], default="minimal")
    setup_translation.add_argument("--install", action="store_true", help="Install selected Python dependencies")
    setup_translation.add_argument("--dry-run", action="store_true", help="Only print the install/check plan")

    sample = subparsers.add_parser("sample", help="Generate a local sample video")
    sample.add_argument("--output", required=True, type=Path)
    sample.add_argument("--duration", type=float, default=6.0)

    download = subparsers.add_parser("download", help="Download a video URL with yt-dlp")
    download.add_argument("--url", required=True)
    download.add_argument("--output-dir", required=True, type=Path)
    download.add_argument("--prefix", help="Optional safe filename prefix")
    download.add_argument("--cookies", type=Path, help="Optional cookies.txt path for yt-dlp")

    comments = subparsers.add_parser("comments", help="Scrape YouTube / Bilibili video comments")
    comments.add_argument("--url", required=True)
    comments.add_argument("--output-dir", required=True, type=Path)
    comments.add_argument("--platform", choices=["auto", "youtube", "bilibili"], default="auto")
    comments.add_argument("--limit", type=int, default=50, help="Maximum number of comments to save")
    comments.add_argument("--cookies", type=Path, help="Optional cookies.txt path for YouTube yt-dlp")
    comments.add_argument("--no-download-images", action="store_true", help="Keep image URLs without downloading them")
    comments.add_argument("--capture-screenshots", dest="capture_screenshots", action="store_true", default=True)
    comments.add_argument("--no-capture-screenshots", dest="capture_screenshots", action="store_false")
    comments.add_argument("--screenshot-count", type=int, default=4, help="Number of real comment-section screenshots")
    comments.add_argument("--viewport-width", type=int, default=1280, help="Screenshot viewport width")
    comments.add_argument("--viewport-height", type=int, default=720, help="Screenshot viewport height")

    comment_freeze = subparsers.add_parser(
        "comment-freeze",
        help="Crop real comment-section screenshots and render freeze-frame video",
    )
    comment_freeze.add_argument("--comments-json", required=True, type=Path)
    comment_freeze.add_argument("--output-dir", required=True, type=Path)
    comment_freeze.add_argument("--layout", choices=["landscape", "portrait", "square"], default="landscape")
    comment_freeze.add_argument("--max-frames", type=int, default=10)
    comment_freeze.add_argument("--frame-duration", type=float, default=3.0)

    comment_narration = subparsers.add_parser(
        "comment-narration",
        help="Build comment narration plan and render a narrated comment video",
    )
    comment_narration.add_argument("--comments-json", required=True, type=Path)
    comment_narration.add_argument("--freeze-manifest", required=True, type=Path)
    comment_narration.add_argument("--output-dir", required=True, type=Path)
    comment_narration.add_argument("--max-items", type=int, default=6)
    comment_narration.add_argument("--tts-engine", default=None)
    comment_narration.add_argument("--tts-ports", default=None)
    comment_narration.add_argument("--voice", default=None)
    comment_narration.add_argument("--ref-wav", type=Path, default=None, help="Optional reference voice WAV for TTS")
    comment_narration.add_argument("--ref-text", default=None, help="Optional transcript for --ref-wav")
    comment_narration.add_argument("--allow-tts-fallback", action="store_true")
    comment_narration.add_argument("--no-render", dest="render", action="store_false", default=True)

    merge = subparsers.add_parser("merge", help="Merge multiple rendered videos into one remix")
    merge.add_argument("--inputs", nargs="+", required=True, type=Path)
    merge.add_argument("--output", required=True, type=Path)
    merge.add_argument("--manifest", type=Path, default=None)

    plan = subparsers.add_parser("plan", help="Write a Codex-reviewable V0.3 workflow plan")
    plan.add_argument("--url", default=None)
    plan.add_argument("--input", type=Path, default=None)
    plan.add_argument("--project-dir", required=True, type=Path)
    plan.add_argument("--tasks", default="download,comments,comment-freeze,merge")
    plan.add_argument("--target-lang", default="中文")
    plan.add_argument("--theme", default="auto")
    plan.add_argument("--highlight-duration", type=int, default=20)
    plan.add_argument("--comment-duration", type=int, default=20)
    plan.add_argument("--comment-count", type=int, default=30)
    plan.add_argument("--plan-path", type=Path, default=None)

    execute = subparsers.add_parser("execute", help="Execute a V0.3 workflow plan")
    execute.add_argument("--plan", required=True, type=Path)
    execute.add_argument("--dry-run", action="store_true")

    create = subparsers.add_parser("create", help="Plan and execute a V0.3 video remix workflow")
    create.add_argument("--url", default=None)
    create.add_argument("--input", type=Path, default=None)
    create.add_argument("--project-dir", required=True, type=Path)
    create.add_argument("--tasks", default="download,comments,comment-freeze,merge")
    create.add_argument("--target-lang", default="中文")
    create.add_argument("--theme", default="auto")
    create.add_argument("--highlight-duration", type=int, default=20)
    create.add_argument("--comment-duration", type=int, default=20)
    create.add_argument("--comment-count", type=int, default=30)
    create.add_argument("--dry-run", action="store_true")

    translate = subparsers.add_parser("translate-video", help="Translate a video with LogicCut local or external backend")
    translate.add_argument("--backend", choices=["video-translate-refine", "logiccut-local"], default="video-translate-refine")
    translate.add_argument("--input", required=True, type=Path)
    translate.add_argument("--output-dir", required=True, type=Path)
    translate.add_argument("--clip", type=int, default=None, help="Only process the first N seconds")
    translate.add_argument("--profile", default=None, help="video-translate-refine profile, defaults to v3")
    translate.add_argument("--src-lang", default=None, help="Source language override, e.g. en or zh-CN")
    translate.add_argument("--tgt-lang", default=None, help="Target language override, e.g. 中文 or English")
    translate.add_argument("--translate-backend", default=None, help="Translation backend, e.g. qwen35_plus or codex")
    translate.add_argument("--transcript-json", type=Path, default=None, help="Use an existing transcript JSON for logiccut-local")
    translate.add_argument("--translation-json", type=Path, default=None, help="Use Codex-authored translated segments JSON")
    translate.add_argument("--allow-fallback-transcript", action="store_true", help="Allow synthetic transcript only for local demos")
    translate.add_argument("--subtitle-path", type=Path, default=None, help="Optional SRT path for subtitle-direct dubbing")
    translate.add_argument("--speaker-backend", default=None, help="Speaker backend override")
    translate.add_argument("--asr-text-refine-backend", default=None, help="ASR text refinement backend override")
    translate.add_argument("--vocal-separation-backend", default=None, help="Vocal separation backend override")
    translate.add_argument(
        "--tts-engine",
        default=None,
        choices=["fishaudio", "indextts2", "omnivoice", "rgad-tts", "rgad-crosslingual-tts", "fish-speech-s2"],
        help="TTS engine preset",
    )
    translate.add_argument("--tts-backend", default=None, help="Advanced video-translate-refine TTS backend override")
    translate.add_argument("--tts-ports", default=None, help="TTS gateway ports")
    translate.add_argument("--fish-tts-adapter-url", default=None, help="Fish Speech S2 adapter URL")
    translate.add_argument("--dub-workers", type=int, default=None, help="Dubbing worker count")
    translate.add_argument("--min-speakers", type=int, default=None, help="Local diarization minimum speaker count")
    translate.add_argument("--num-speakers", type=int, default=None, help="Fixed local diarization speaker count")
    translate.add_argument("--max-speakers", type=int, default=None, help="Local diarization maximum speaker count")
    translate.add_argument("--enable-ref-bgm-filter", action="store_true", help="Enable ref-BGM filtering")
    translate.add_argument("--ref-bgm-tts-ref-strategy", default=None, help="TTS ref strategy, e.g. indextts2_decoupled")
    translate.add_argument("--write-subtitles", dest="write_subtitles", action="store_true", default=True)
    translate.add_argument("--no-write-subtitles", dest="write_subtitles", action="store_false")
    translate.add_argument(
        "--burn-subtitles",
        dest="burn_subtitles",
        action="store_true",
        default=None,
        help="Burn translated subtitles into the output video",
    )
    translate.add_argument("--no-burn-subtitles", dest="burn_subtitles", action="store_false")
    translate.add_argument("--timeout", type=int, default=None, help="Overall timeout in seconds")
    translate.add_argument("--dry-run", action="store_true", help="Print command without running")

    init = subparsers.add_parser("init", help="Create a LogicCut project")
    init.add_argument("--input", required=True, type=Path)
    init.add_argument("--project-dir", required=True, type=Path)
    init.add_argument("--title")

    run = subparsers.add_parser("run", help="Run one recipe or a recipe suite")
    run.add_argument("--project-dir", required=True, type=Path)
    run.add_argument(
        "--recipe",
        default="all",
        choices=[
            "all",
            "semantic-suite",
            "translate-remix",
            "highlight-first",
            "chapter-clips",
            "video-translation",
            "semantic-highlights",
            "creator-remix",
            "chapter-card-narration",
            "guided-highlights",
            "story-guided-highlights",
            "theme-opener",
            "personalized-highlights",
        ],
    )
    run.add_argument("--input", type=Path, help="Initialize the project if project.json does not exist")
    run.add_argument("--title")
    run.add_argument("--chapters", type=int, default=3)

    status = subparsers.add_parser("status", help="Print project manifest summary")
    status.add_argument("--project-dir", required=True, type=Path)

    benchmark = subparsers.add_parser("benchmark-references", help="Build reference reproduction benchmark pages")
    benchmark.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/reference-reproduction-benchmark"),
        help="Directory for benchmark HTML, JSON reports and copied baseline videos",
    )
    benchmark.add_argument("--no-blackdetect", action="store_true", help="Skip ffmpeg blackdetect checks")

    external = subparsers.add_parser("external-adapter-poc", help="Run external highlight adapter POCs")
    external.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/external-adapter-poc"),
        help="Directory for adapter outputs and showcase HTML",
    )
    external.add_argument("--limit", type=int, default=4, help="Highlights per source to render")
    external.add_argument("--no-render", action="store_true", help="Only rebuild reports from existing outputs")
    external.add_argument("--no-blackdetect", action="store_true", help="Skip ffmpeg blackdetect checks")

    args = parser.parse_args(argv)
    if args.command == "capabilities":
        return _print(build_capabilities())
    if args.command == "guide":
        return _print(build_guide(args.task))
    if args.command == "doctor":
        result = run_doctor(profile=args.profile)
        if args.json:
            return _print(result)
        return _print(result)
    if args.command == "setup":
        return _print(
            run_translation_setup(
                profile=args.profile,
                install=bool(args.install) and not bool(args.dry_run),
            )
        )
    if args.command == "sample":
        output = ensure_sample_video(args.output, duration=args.duration)
        return _print({"sample": str(output), "bytes": output.stat().st_size})
    if args.command == "download":
        result = download_video(args.url, args.output_dir, prefix=args.prefix, cookies=args.cookies)
        return _print(
            {
                "url": result.url,
                "path": str(result.path),
                "bytes": result.bytes,
                "metadata": {
                    "id": result.metadata.get("id"),
                    "title": result.metadata.get("title"),
                    "duration": result.metadata.get("duration"),
                    "extractor_key": result.metadata.get("extractor_key"),
                    "webpage_url": result.metadata.get("webpage_url"),
                },
            }
        )
    if args.command == "comments":
        result = scrape_comments(
            args.url,
            args.output_dir,
            platform=args.platform,
            max_comments=args.limit,
            cookies=args.cookies,
            download_images=not args.no_download_images,
            capture_screenshots=args.capture_screenshots,
            screenshot_count=args.screenshot_count,
            viewport_width=args.viewport_width,
            viewport_height=args.viewport_height,
        )
        return _print(
            {
                "platform": result["platform"],
                "url": result["url"],
                "video_id": result["video_id"],
                "title": result["title"],
                "comment_count": result["comment_count"],
                "image_count": result["image_count"],
                "screenshot_count": result.get("screenshot_count", 0),
                "comments_path": result["comments_path"],
                "report_path": result["report_path"],
            }
        )
    if args.command == "comment-freeze":
        result = create_comment_freeze_video(
            args.comments_json,
            args.output_dir,
            layout=args.layout,
            max_frames=args.max_frames,
            frame_duration=args.frame_duration,
        )
        return _print(
            {
                "output_video": result["output_video"],
                "manifest": result["manifest_path"],
                "report": result["report_path"],
                "frame_count": result.get("frame_count", 0),
                "layout": result.get("layout", args.layout),
            }
        )
    if args.command == "comment-narration":
        result = create_comment_narration_video(
            args.comments_json,
            args.freeze_manifest,
            args.output_dir,
            max_items=args.max_items,
            tts_engine=args.tts_engine,
            tts_ports=args.tts_ports,
            voice=args.voice,
            ref_wav=args.ref_wav,
            ref_text=args.ref_text,
            allow_tts_fallback=args.allow_tts_fallback,
            render=args.render,
        )
        return _print(
            {
                "output_video": result["output_video"],
                "plan": result["plan_path"],
                "prompt": result["prompt_path"],
                "report": result["report_path"],
                "item_count": result["item_count"],
            }
        )
    if args.command == "merge":
        return _print(merge_videos(args.inputs, args.output, manifest_path=args.manifest))
    if args.command == "plan":
        return _print(
            write_workflow_plan(
                project_dir=args.project_dir,
                tasks=parse_tasks(args.tasks),
                url=args.url,
                input_video=args.input,
                target_lang=args.target_lang,
                theme=args.theme,
                highlight_duration=args.highlight_duration,
                comment_duration=args.comment_duration,
                comment_count=args.comment_count,
                plan_path=args.plan_path,
            )
        )
    if args.command == "execute":
        return _print(execute_workflow_plan(args.plan, dry_run=args.dry_run))
    if args.command == "create":
        plan_result = write_workflow_plan(
            project_dir=args.project_dir,
            tasks=parse_tasks(args.tasks),
            url=args.url,
            input_video=args.input,
            target_lang=args.target_lang,
            theme=args.theme,
            highlight_duration=args.highlight_duration,
            comment_duration=args.comment_duration,
            comment_count=args.comment_count,
        )
        execute_result = execute_workflow_plan(Path(plan_result["plan"]), dry_run=args.dry_run)
        return _print({"plan": plan_result, "execution": execute_result})
    if args.command == "translate-video":
        if args.backend == "logiccut-local":
            result = run_local_translation(
                LocalTranslationConfig(
                    input_video=args.input,
                    output_dir=args.output_dir,
                    target_language=args.tgt_lang or "中文",
                    source_language=args.src_lang,
                    clip_seconds=args.clip,
                    transcript_json=args.transcript_json,
                    translation_json=args.translation_json,
                    allow_fallback_transcript=args.allow_fallback_transcript,
                    burn_subtitles=True if args.burn_subtitles is None else bool(args.burn_subtitles),
                )
            )
            return _print(
                {
                    "backend": "logiccut-local",
                    "status": result.status,
                    "output_dir": str(result.output_dir),
                    "manifest": str(result.manifest_path),
                    "prompt": str(result.prompt_path),
                    "transcript": str(result.transcript_path),
                    "todo_translation": str(result.todo_translation_path),
                    "translation_json": str(result.translation_path) if result.translation_path else None,
                    "subtitle": str(result.subtitle_path) if result.subtitle_path else None,
                    "output_video": str(result.output_video) if result.output_video else None,
                }
            )
        config = config_from_env(
            video=args.input,
            output_dir=args.output_dir,
            clip_seconds=args.clip,
            src_lang=args.src_lang,
            tgt_lang=args.tgt_lang,
            profile=args.profile,
            translate_backend=args.translate_backend,
            subtitle_path=args.subtitle_path,
            tts_engine=args.tts_engine,
        )
        if args.timeout is not None:
            config = config.__class__(**{**config.__dict__, "timeout_s": args.timeout})
        overrides = {
            "speaker_backend": args.speaker_backend,
            "asr_text_refine_backend": args.asr_text_refine_backend,
            "vocal_separation_backend": args.vocal_separation_backend,
            "tts_backend": args.tts_backend,
            "tts_ports": args.tts_ports,
            "fish_tts_adapter_url": args.fish_tts_adapter_url,
            "dub_workers": args.dub_workers,
            "min_speakers": args.min_speakers,
            "num_speakers": args.num_speakers,
            "max_speakers": args.max_speakers,
            "ref_bgm_tts_ref_strategy": args.ref_bgm_tts_ref_strategy,
        }
        if any(value is not None for value in overrides.values()):
            config = config.__class__(**{**config.__dict__, **{k: v for k, v in overrides.items() if v is not None}})
        config = config.__class__(
                **{
                    **config.__dict__,
                    "ref_bgm_filter_enabled": bool(args.enable_ref_bgm_filter) or config.ref_bgm_filter_enabled,
                    "write_subtitles": bool(args.write_subtitles),
                    "burn_subtitles": bool(args.burn_subtitles),
                }
        )
        if args.dry_run:
            command, env = build_command(config)
            return _print(
                {
                    "backend": "video-translate-refine",
                    "tts_engine": config.tts_engine,
                    "speaker_backend": config.speaker_backend,
                    "write_subtitles": config.write_subtitles,
                    "burn_subtitles": config.burn_subtitles,
                    "command": command,
                    "cwd": str(config.source_root),
                    "env": {
                        "PYTHONPATH": env.get("PYTHONPATH", ""),
                        "PYTHONNOUSERSITE": env.get("PYTHONNOUSERSITE", ""),
                        "LOGICCUT_CREATIVE_DRIVER": env.get("LOGICCUT_CREATIVE_DRIVER", "codex"),
                    },
                }
            )
        result = run_video_translate_refine(config)
        return _print(
            {
                "backend": "video-translate-refine",
                "output_video": str(result.output_video),
                "source_output_video": str(result.source_output_video),
                "run_dir": str(result.run_dir),
                "manifest": str(result.manifest_path),
                "log": str(result.log_path),
                "subtitle": str(result.subtitle_path) if result.subtitle_path else None,
                "subtitled_video": str(result.subtitled_video) if result.subtitled_video else None,
            }
        )
    if args.command == "init":
        manifest = init_project(args.input, args.project_dir, title=args.title)
        return _print({"project_dir": str(args.project_dir), "manifest": manifest})
    if args.command == "run":
        manifest_file = args.project_dir / "project.json"
        if not manifest_file.exists():
            if not args.input:
                raise SystemExit("--input is required when project.json does not exist")
            init_project(args.input, args.project_dir, title=args.title)
        manifest = run_recipe(args.project_dir, args.recipe, chapters=args.chapters)
        return _print(_summary(args.project_dir, manifest))
    if args.command == "status":
        return _print(_summary(args.project_dir, load_manifest(args.project_dir)))
    if args.command == "benchmark-references":
        repo_root = Path(__file__).resolve().parents[1]
        result = write_benchmark_package(
            repo_root=repo_root,
            output_dir=args.output_dir,
            cases=default_reference_cases(repo_root),
            run_blackdetect=not args.no_blackdetect,
        )
        return _print(result)
    if args.command == "external-adapter-poc":
        repo_root = Path(__file__).resolve().parents[1]
        result = run_external_adapter_pocs(
            repo_root=repo_root,
            output_dir=args.output_dir,
            limit=args.limit,
            render=not args.no_render,
            run_blackdetect=not args.no_blackdetect,
        )
        return _print(result)
    raise AssertionError(args.command)


def _summary(project_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_dir": str(project_dir),
        "schema_version": manifest.get("schema_version"),
        "recipes": manifest.get("recipes", []),
        "clips": manifest.get("clips", []),
        "renders": manifest.get("renders", []),
    }


def _print(data: dict[str, Any]) -> int:
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
