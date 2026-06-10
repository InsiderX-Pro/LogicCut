from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from logiccut.media import burn_subtitles
from logiccut.media import render_clip
from logiccut.subtitles import write_ass_from_srt


class SubtitleRenderingTest(unittest.TestCase):
    def test_write_ass_from_srt_uses_captioner_clean_style_without_black_box(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srt = root / "subtitle.srt"
            ass = root / "subtitle.ass"
            srt.write_text(
                "\n".join(
                    [
                        "1",
                        "00:00:00,000 --> 00:00:03,000",
                        "笔记本、手机、相机放在这里，我敢说没有人会碰。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            write_ass_from_srt(
                srt,
                ass,
                width=852,
                height=480,
                preset="captioner",
                font_name="Noto Sans CJK SC",
            )

            content = ass.read_text(encoding="utf-8")
            self.assertIn("Style: Default,Noto Sans CJK SC,34", content)
            self.assertIn(",1,3,1,2,48,48,28,1", content)
            self.assertNotIn("&H50000000", content)

    def test_write_ass_from_srt_uses_subcap_modern_style_and_cjk_wrapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srt = root / "subtitle.srt"
            ass = root / "subtitle.ass"
            srt.write_text(
                "\n".join(
                    [
                        "1",
                        "00:00:00,000 --> 00:00:03,000",
                        "这一段中文字幕应该自动断行，不要再挤成一坨显示在画面底部。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            write_ass_from_srt(
                srt,
                ass,
                width=1920,
                height=1080,
                preset="modern",
                font_name="Noto Sans CJK SC",
                max_chars=14,
            )

            content = ass.read_text(encoding="utf-8")
            self.assertIn("PlayResX: 1920", content)
            self.assertIn("PlayResY: 1080", content)
            self.assertIn("Style: Default,Noto Sans CJK SC,56", content)
            self.assertIn(",3,14,0,2,100,100,50,1", content)
            self.assertIn("\\N", content)
            self.assertIn("Dialogue: 0,0:00:00.00,0:00:03.00,Default", content)

    def test_burn_subtitles_generates_ass_and_uses_libass_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            output = root / "output.mp4"
            srt = root / "subtitle.srt"
            source.write_bytes(b"video")
            srt.write_text("1\n00:00:00,000 --> 00:00:02,000\n你好世界\n", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run_command(cmd: list[str], log_file=None) -> None:
                calls.append(cmd)
                output.write_bytes(b"out")

            with (
                patch("logiccut.media.ffprobe_video_size", return_value=(1080, 1920)),
                patch("logiccut.media.subtitle_font_name", return_value="Noto Sans CJK SC"),
                patch("logiccut.media.run_command", side_effect=fake_run_command),
            ):
                burn_subtitles(source, srt, output)

            self.assertTrue(srt.with_suffix(".ass").exists())
            command = calls[0]
            video_filter = command[command.index("-vf") + 1]
            self.assertTrue(video_filter.startswith("ass="), video_filter)
            self.assertNotIn("force_style", video_filter)

    def test_render_clip_accurate_places_seek_after_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            output = root / "clip.mp4"
            source.write_bytes(b"video")
            calls: list[list[str]] = []

            def fake_run_command(cmd: list[str], log_file=None) -> None:
                calls.append(cmd)
                output.write_bytes(b"out")

            with patch("logiccut.media.run_command", side_effect=fake_run_command):
                render_clip(source, output, 12.3, 4.5, accurate=True)

            command = calls[0]
            self.assertLess(command.index("-i"), command.index("-ss"))
            self.assertEqual("12.300", command[command.index("-ss") + 1])

    def test_burn_subtitles_can_style_for_portrait_embedded_video_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            output = root / "output.mp4"
            srt = root / "subtitle.srt"
            source.write_bytes(b"video")
            srt.write_text("1\n00:00:00,000 --> 00:00:02,000\n竖屏嵌入视频字幕需要更大。\n", encoding="utf-8")

            def fake_run_command(_cmd: list[str], log_file=None) -> None:
                output.write_bytes(b"out")

            with (
                patch("logiccut.media.ffprobe_video_size", return_value=(1920, 1080)),
                patch("logiccut.media.subtitle_font_name", return_value="Noto Sans CJK SC"),
                patch("logiccut.media.run_command", side_effect=fake_run_command),
            ):
                burn_subtitles(source, srt, output, style_size=(1080, 608))

            ass = srt.with_suffix(".ass").read_text(encoding="utf-8")
            self.assertIn("PlayResX: 1080", ass)
            self.assertIn("PlayResY: 608", ass)


if __name__ == "__main__":
    unittest.main()
