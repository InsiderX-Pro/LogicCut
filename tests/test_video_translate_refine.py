from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from logiccut.video_translate_refine import (
    VideoTranslateRefineConfig,
    build_command,
    parse_output_video,
    redact_secrets,
    run_video_translate_refine,
    write_translated_srt_from_timings,
)


class VideoTranslateRefineAdapterTest(unittest.TestCase):
    def test_build_command_uses_profile_wrapper_and_clip(self) -> None:
        root = Path("/opt/video-translate-refine")
        config = VideoTranslateRefineConfig(
            video=Path("/tmp/in.mp4"),
            output_dir=Path("/tmp/out"),
            source_root=root,
            python=Path("/opt/python"),
            profile="v3",
            clip_seconds=60,
            src_lang="en",
            tgt_lang="中文",
            translate_backend="qwen35_plus",
            tts_engine="fishaudio",
            timeout_s=120,
        )

        command, env = build_command(config)

        self.assertEqual("/opt/python", command[0])
        self.assertEqual(str(root / "scripts" / "run_pipeline_profile.py"), command[1])
        self.assertIn("--profile", command)
        self.assertIn("v3", command)
        self.assertIn("--clip", command)
        self.assertIn("60", command)
        self.assertIn("--src-lang", command)
        self.assertIn("en", command)
        self.assertIn("--tgt-lang", command)
        self.assertIn("中文", command)
        self.assertIn("--translate-backend", command)
        self.assertIn("qwen35_plus", command)
        self.assertIn("--speaker-backend", command)
        self.assertIn("pyannote_local", command)
        self.assertIn("--tts-ports", command)
        self.assertIn("8321", command)
        self.assertIn("--extra-cli-arg", command)
        self.assertIn("--tts-backend legacy_router", command)
        self.assertTrue(env["PYTHONPATH"].startswith(str(root / "src")))

    def test_build_command_supports_subtitle_path_and_omnivoice_tts_engine(self) -> None:
        config = VideoTranslateRefineConfig(
            video=Path("/tmp/in.mp4"),
            output_dir=Path("/tmp/out"),
            source_root=Path("/opt/video-translate-refine"),
            python=Path("/opt/python"),
            subtitle_path=Path("/tmp/input.srt"),
            tts_engine="omnivoice",
        )

        command, _env = build_command(config)

        self.assertIn("--tts-ports", command)
        self.assertIn("8391", command)
        self.assertIn("--extra-cli-arg", command)
        self.assertIn("--subtitle-path /tmp/input.srt", command)

    def test_build_command_resolves_relative_video_path_for_upstream_cwd(self) -> None:
        config = VideoTranslateRefineConfig(
            video=Path("relative/input.mp4"),
            output_dir=Path("/tmp/out"),
            source_root=Path("/opt/video-translate-refine"),
            python=Path("/opt/python"),
        )

        command, _env = build_command(config)

        self.assertEqual(str(Path("relative/input.mp4").resolve()), command[2])

    def test_parse_output_video_uses_last_existing_mp4_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "old.mp4"
            final = Path(tmp) / "output_video.mp4"
            first.write_bytes(b"old")
            final.write_bytes(b"new")
            stdout = f"profile=v3\n{first}\nnoise\n{final}\n"

            self.assertEqual(final, parse_output_video(stdout))

    def test_write_translated_srt_from_timings_sorts_utterances_by_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timings = root / "timings.json"
            output = root / "translated.srt"
            timings.write_text(
                """
                {
                  "utterances": [
                    {
                      "start_ms": 2000,
                      "end_ms": 3000,
                      "text": "second",
                      "attempts": [{"translated_text": "第二句"}]
                    },
                    {
                      "start_ms": 0,
                      "end_ms": 1000,
                      "text": "first",
                      "attempts": [{"translated_text": "第一句"}]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            write_translated_srt_from_timings(timings, output)

            content = output.read_text(encoding="utf-8")
            self.assertIn("00:00:00,000 --> 00:00:01,000\n第一句", content)
            self.assertIn("00:00:02,000 --> 00:00:03,000\n第二句", content)
            self.assertLess(content.index("第一句"), content.index("第二句"))

    def test_redact_secrets_removes_key_values(self) -> None:
        text = "DASHSCOPE_API_KEY=fake-secret-token\nOPENAI_API_KEY=abc\nnormal=value"

        redacted = redact_secrets(text)

        self.assertNotIn("fake-secret-token", redacted)
        self.assertNotIn("abc", redacted)
        self.assertIn("DASHSCOPE_API_KEY=<redacted>", redacted)
        self.assertIn("OPENAI_API_KEY=<redacted>", redacted)
        self.assertIn("normal=value", redacted)

    def test_run_video_translate_refine_copies_output_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "vtr"
            (source_root / "scripts").mkdir(parents=True)
            (source_root / "src").mkdir()
            output_dir = root / "logiccut-output"
            produced = root / "vtr-run" / "output_video.mp4"
            produced.parent.mkdir()
            produced.write_bytes(b"video")

            completed = Mock(returncode=0, stdout=f"{produced}\n", stderr="DASHSCOPE_API_KEY=secret")
            runner = Mock(return_value=completed)
            config = VideoTranslateRefineConfig(
                video=root / "input.mp4",
                output_dir=output_dir,
                source_root=source_root,
                python=Path("/usr/bin/python"),
                profile="v3",
                clip_seconds=60,
                src_lang="en",
                tgt_lang="中文",
                write_subtitles=True,
            )

            with patch.dict(os.environ, {}, clear=True):
                result = run_video_translate_refine(config, runner=runner)

            self.assertEqual(output_dir / "output_video.mp4", result.output_video)
            self.assertTrue(result.output_video.exists())
            self.assertTrue(result.manifest_path.exists())
            self.assertTrue(result.log_path.exists())
            self.assertIsNone(result.subtitle_path)
            self.assertNotIn("secret", result.log_path.read_text(encoding="utf-8"))
            self.assertIn("DASHSCOPE_API_KEY=<redacted>", result.log_path.read_text(encoding="utf-8"))
            runner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
