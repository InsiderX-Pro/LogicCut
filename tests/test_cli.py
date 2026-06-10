from __future__ import annotations

import tempfile
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from logiccut.cli import main


class CliTest(unittest.TestCase):
    def test_module_entrypoint_creates_sample_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "sample.mp4"

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "logiccut.cli",
                    "sample",
                    "--output",
                    str(output),
                    "--duration",
                    "1",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 0)

    def test_translate_video_dry_run_prints_video_translate_refine_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_video = root / "input.mp4"
            input_video.write_bytes(b"video")

            with patch("builtins.print") as print_mock:
                exit_code = main(
                    [
                        "translate-video",
                        "--input",
                        str(input_video),
                        "--output-dir",
                        str(root / "out"),
                        "--clip",
                        "60",
                        "--src-lang",
                        "en",
                        "--tgt-lang",
                        "中文",
                        "--tts-engine",
                        "indextts2",
                        "--subtitle-path",
                        str(root / "input.srt"),
                        "--burn-subtitles",
                        "--dry-run",
                    ]
                )

            self.assertEqual(0, exit_code)
            payload = print_mock.call_args.args[0]
            self.assertIn("run_pipeline_profile.py", payload)
            self.assertIn("--clip", payload)
            self.assertIn("60", payload)
            self.assertIn("--tgt-lang", payload)
            self.assertIn("中文", payload)
            self.assertIn("--speaker-backend", payload)
            self.assertIn("pyannote_local", payload)
            self.assertIn("--tts-ports", payload)
            self.assertIn("8304", payload)
            self.assertIn("--subtitle-path", payload)
            self.assertIn("PYTHONNOUSERSITE", payload)
            self.assertIn('"1"', payload)
            self.assertIn("burn_subtitles", payload)
            self.assertIn("true", payload.lower())

    def test_translate_video_accepts_rgad_tts_preset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_video = root / "input.mp4"
            input_video.write_bytes(b"video")

            with patch("builtins.print") as print_mock:
                exit_code = main(
                    [
                        "translate-video",
                        "--input",
                        str(input_video),
                        "--output-dir",
                        str(root / "out"),
                        "--tts-engine",
                        "rgad-tts",
                        "--dry-run",
                    ]
                )

            self.assertEqual(0, exit_code)
            payload = print_mock.call_args.args[0]
            self.assertIn("--tts-ports", payload)
            self.assertIn("8393", payload)
            self.assertIn("run_pipeline_profile.py", payload)

    def test_translate_video_logiccut_local_backend_uses_minimal_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_video = root / "input.mp4"
            transcript = root / "transcript.json"
            output_dir = root / "out"
            input_video.write_bytes(b"video")
            transcript.write_text('{"segments": []}', encoding="utf-8")

            with (
                patch(
                    "logiccut.cli.run_local_translation",
                    return_value=type(
                        "Result",
                        (),
                        {
                            "status": "needs_codex_translation",
                            "output_dir": output_dir,
                            "manifest_path": output_dir / "translation_manifest.json",
                            "prompt_path": output_dir / "codex_translation_prompt.md",
                            "transcript_path": output_dir / "source_transcript.json",
                            "todo_translation_path": output_dir / "translated_segments.todo.json",
                            "translation_path": output_dir / "translated_segments.json",
                            "subtitle_path": None,
                            "output_video": None,
                        },
                    )(),
                ) as translate_mock,
                patch("builtins.print") as print_mock,
            ):
                exit_code = main(
                    [
                        "translate-video",
                        "--backend",
                        "logiccut-local",
                        "--input",
                        str(input_video),
                        "--output-dir",
                        str(output_dir),
                        "--transcript-json",
                        str(transcript),
                        "--tgt-lang",
                        "中文",
                    ]
                )

            self.assertEqual(0, exit_code)
            translate_mock.assert_called_once()
            config = translate_mock.call_args.args[0]
            self.assertEqual(input_video, config.input_video)
            self.assertEqual(transcript, config.transcript_json)
            self.assertEqual("中文", config.target_language)
            payload = print_mock.call_args.args[0]
            self.assertIn("logiccut-local", payload)
            self.assertIn("needs_codex_translation", payload)

    def test_setup_translation_prints_install_plan(self) -> None:
        with patch("builtins.print") as print_mock:
            exit_code = main(["setup", "translation", "--profile", "minimal", "--dry-run"])

        self.assertEqual(0, exit_code)
        payload = print_mock.call_args.args[0]
        self.assertIn('"component": "translation"', payload)
        self.assertIn("logiccut translate-video --backend logiccut-local", payload)

    def test_setup_translation_defaults_to_asr_profile(self) -> None:
        with patch("builtins.print") as print_mock:
            exit_code = main(["setup", "translation", "--dry-run"])

        self.assertEqual(0, exit_code)
        payload = print_mock.call_args.args[0]
        self.assertIn('"profile": "asr"', payload)
        self.assertIn("faster-whisper", payload)

    def test_run_accepts_guided_highlights_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            (project / "project.json").write_text("{}", encoding="utf-8")

            with (
                patch("logiccut.cli.run_recipe", return_value={"schema_version": "0.2", "recipes": [], "clips": [], "renders": []}) as run_mock,
                patch("builtins.print"),
            ):
                exit_code = main(["run", "--project-dir", str(project), "--recipe", "guided-highlights"])

            self.assertEqual(0, exit_code)
            run_mock.assert_called_once()
            self.assertEqual("guided-highlights", run_mock.call_args.args[1])

    def test_run_accepts_theme_opener_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            (project / "project.json").write_text("{}", encoding="utf-8")

            with (
                patch("logiccut.cli.run_recipe", return_value={"schema_version": "0.2", "recipes": [], "clips": [], "renders": []}) as run_mock,
                patch("builtins.print"),
            ):
                exit_code = main(["run", "--project-dir", str(project), "--recipe", "theme-opener"])

            self.assertEqual(0, exit_code)
            run_mock.assert_called_once()
            self.assertEqual("theme-opener", run_mock.call_args.args[1])

    def test_comments_command_scrapes_video_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "comments"

            with (
                patch(
                    "logiccut.cli.scrape_comments",
                    return_value={
                        "platform": "youtube",
                        "url": "https://www.youtube.com/watch?v=abc123",
                        "video_id": "abc123",
                        "title": "Demo",
                        "comment_count": 3,
                        "image_count": 0,
                        "comments_path": str(output_dir / "comments.json"),
                        "report_path": str(output_dir / "comments_report.html"),
                    },
                ) as scrape_mock,
                patch("builtins.print") as print_mock,
            ):
                exit_code = main(
                    [
                        "comments",
                        "--url",
                        "https://www.youtube.com/watch?v=abc123",
                        "--output-dir",
                        str(output_dir),
                        "--platform",
                        "youtube",
                        "--limit",
                        "3",
                        "--no-download-images",
                        "--no-capture-screenshots",
                    ]
                )

            self.assertEqual(0, exit_code)
            scrape_mock.assert_called_once()
            self.assertEqual("youtube", scrape_mock.call_args.kwargs["platform"])
            self.assertEqual(3, scrape_mock.call_args.kwargs["max_comments"])
            self.assertFalse(scrape_mock.call_args.kwargs["download_images"])
            self.assertFalse(scrape_mock.call_args.kwargs["capture_screenshots"])
            self.assertIn("comments_report.html", print_mock.call_args.args[0])

    def test_comments_command_captures_real_comment_screenshots_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "comments"

            with (
                patch(
                    "logiccut.cli.scrape_comments",
                    return_value={
                        "platform": "bilibili",
                        "url": "https://www.bilibili.com/video/BVxx/",
                        "video_id": "BVxx",
                        "title": "Demo",
                        "comment_count": 3,
                        "image_count": 0,
                        "screenshot_count": 2,
                        "comments_path": str(output_dir / "comments.json"),
                        "report_path": str(output_dir / "comments_report.html"),
                    },
                ) as scrape_mock,
                patch("builtins.print") as print_mock,
            ):
                exit_code = main(
                    [
                        "comments",
                        "--url",
                        "https://www.bilibili.com/video/BVxx/",
                        "--output-dir",
                        str(output_dir),
                        "--limit",
                        "3",
                        "--screenshot-count",
                        "2",
                    ]
                )

            self.assertEqual(0, exit_code)
            self.assertTrue(scrape_mock.call_args.kwargs["capture_screenshots"])
            self.assertEqual(2, scrape_mock.call_args.kwargs["screenshot_count"])
            self.assertIn("screenshot_count", print_mock.call_args.args[0])

    def test_comment_freeze_command_builds_video_from_comment_screenshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            comments_json = root / "comments.json"
            comments_json.write_text("{}", encoding="utf-8")

            with (
                patch(
                    "logiccut.cli.create_comment_freeze_video",
                    return_value={
                        "output_video": str(root / "comment_freeze_video.mp4"),
                        "manifest_path": str(root / "comment_freeze_manifest.json"),
                        "report_path": str(root / "comment_freeze_report.html"),
                        "frame_count": 3,
                    },
                ) as freeze_mock,
                patch("builtins.print") as print_mock,
            ):
                exit_code = main(
                    [
                        "comment-freeze",
                        "--comments-json",
                        str(comments_json),
                        "--output-dir",
                        str(root / "freeze"),
                        "--layout",
                        "portrait",
                        "--max-frames",
                        "3",
                    ]
                )

            self.assertEqual(0, exit_code)
            freeze_mock.assert_called_once()
            self.assertEqual("portrait", freeze_mock.call_args.kwargs["layout"])
            self.assertEqual(3, freeze_mock.call_args.kwargs["max_frames"])
            self.assertIn("comment_freeze_video.mp4", print_mock.call_args.args[0])

    def test_comment_narration_command_builds_plan_and_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            comments_json = root / "comments.json"
            freeze_manifest = root / "comment_freeze_manifest.json"
            comments_json.write_text("{}", encoding="utf-8")
            freeze_manifest.write_text("{}", encoding="utf-8")

            with (
                patch(
                    "logiccut.cli.create_comment_narration_video",
                    return_value={
                        "output_video": str(root / "comment_narration_video.mp4"),
                        "plan_path": str(root / "comment_narration_plan.json"),
                        "prompt_path": str(root / "comment_narration_prompt.md"),
                        "report_path": str(root / "comment_narration_report.html"),
                        "item_count": 2,
                    },
                ) as narration_mock,
                patch("builtins.print") as print_mock,
            ):
                exit_code = main(
                    [
                        "comment-narration",
                        "--comments-json",
                        str(comments_json),
                        "--freeze-manifest",
                        str(freeze_manifest),
                        "--output-dir",
                        str(root / "narration"),
                        "--allow-tts-fallback",
                        "--ref-wav",
                        str(root / "voice.wav"),
                        "--ref-text",
                        "参考声音",
                        "--max-items",
                        "2",
                    ]
                )

            self.assertEqual(0, exit_code)
            narration_mock.assert_called_once()
            self.assertTrue(narration_mock.call_args.kwargs["allow_tts_fallback"])
            self.assertEqual(2, narration_mock.call_args.kwargs["max_items"])
            self.assertEqual(root / "voice.wav", narration_mock.call_args.kwargs["ref_wav"])
            self.assertEqual("参考声音", narration_mock.call_args.kwargs["ref_text"])
            self.assertIn("comment_narration_plan.json", print_mock.call_args.args[0])

    def test_benchmark_references_command_builds_reference_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "benchmark"

            with (
                patch("logiccut.cli.write_benchmark_package", return_value={"index": str(output_dir / "index.html"), "cases": []}) as build_mock,
                patch("builtins.print") as print_mock,
            ):
                exit_code = main(["benchmark-references", "--output-dir", str(output_dir), "--no-blackdetect"])

            self.assertEqual(0, exit_code)
            build_mock.assert_called_once()
            self.assertEqual(output_dir, build_mock.call_args.kwargs["output_dir"])
            self.assertFalse(build_mock.call_args.kwargs["run_blackdetect"])
            self.assertIn("index.html", print_mock.call_args.args[0])

    def test_external_adapter_poc_command_runs_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "external"

            with (
                patch(
                    "logiccut.cli.run_external_adapter_pocs",
                    return_value={"index": str(output_dir / "index.html"), "adapters": []},
                ) as run_mock,
                patch("builtins.print") as print_mock,
            ):
                exit_code = main(
                    [
                        "external-adapter-poc",
                        "--output-dir",
                        str(output_dir),
                        "--limit",
                        "2",
                        "--no-render",
                        "--no-blackdetect",
                    ]
                )

            self.assertEqual(0, exit_code)
            run_mock.assert_called_once()
            self.assertEqual(output_dir, run_mock.call_args.kwargs["output_dir"])
            self.assertEqual(2, run_mock.call_args.kwargs["limit"])
            self.assertFalse(run_mock.call_args.kwargs["render"])
            self.assertFalse(run_mock.call_args.kwargs["run_blackdetect"])
            self.assertIn("external", print_mock.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
