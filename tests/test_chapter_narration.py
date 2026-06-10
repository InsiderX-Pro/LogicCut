from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from logiccut.chapter_narration import (
    build_narration_text,
    mix_card_with_narration,
    prepare_narration_reference,
    synthesize_narration_audio,
    write_narration_srt,
)
from logiccut.html_cards import HighlightCard


class ChapterNarrationTest(unittest.TestCase):
    def test_build_narration_text_includes_title_hook_and_reason(self) -> None:
        card = HighlightCard(
            index=1,
            title="模型能力的真正分水岭",
            reason="语义密度高，观点完整。",
            hook="这一段解释了 Agent 为什么会变得不一样。",
            score=92,
            start=1.0,
            end=9.0,
            keywords=("模型", "Agent"),
        )

        text = build_narration_text(card)

        self.assertIn("模型能力的真正分水岭", text)
        self.assertIn("Agent", text)
        self.assertIn("语义密度高", text)
        self.assertLessEqual(len(text), 90)

    def test_build_narration_text_normalizes_simplified_chinese(self) -> None:
        card = HighlightCard(
            index=1,
            title="這個轉折很關鍵",
            reason="這一段適合放在開頭。",
            hook="讓觀眾先看到衝突。",
            score=90,
            start=0,
            end=8,
            keywords=(),
        )

        text = build_narration_text(card)

        self.assertIn("这个转折很关键", text)
        self.assertIn("让观众先看到冲突", text)
        self.assertNotIn("這", text)

    def test_prepare_narration_reference_extracts_source_voice_clip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            output = root / "ref.wav"
            source.write_bytes(b"video")
            calls: list[list[str]] = []

            def fake_run_command(cmd: list[str], log_file=None) -> None:
                calls.append(cmd)
                output.write_bytes(b"wav")

            with patch("logiccut.chapter_narration.run_command", side_effect=fake_run_command):
                result = prepare_narration_reference(source, output, start=12.0, end=14.0)

            self.assertEqual(output, result)
            self.assertTrue(output.exists())
            command = calls[0]
            self.assertIn("-ss", command)
            self.assertIn("12.000", command)
            self.assertIn("-t", command)
            self.assertIn("4.000", command)
            self.assertIn("-ar", command)
            self.assertIn("24000", command)

    def test_write_narration_srt_splits_long_text_into_timed_cues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "narration.srt"
            text = (
                "这一章先看：AI的愚蠢时刻：开车去洗车，它叫我走路去。"
                "重点是，这个荒谬又好笑的例子，生动地解释了AI锯齿状智能的悖论。"
                "我把它放在这里，是因为这个故事极易传播，并引发人们对AI本质的讨论。"
            )

            write_narration_srt(path, text, duration=9.0)

            blocks = path.read_text(encoding="utf-8").strip().split("\n\n")
            self.assertGreater(len(blocks), 1)
            self.assertIn("00:00:00,000 -->", blocks[0])
            self.assertIn("--> 00:00:09,000", blocks[-1])
            for block in blocks:
                lines = block.splitlines()
                subtitle_lines = lines[2:]
                self.assertLessEqual(len(subtitle_lines), 2, block)
                self.assertTrue(all(len(line) <= 24 for line in subtitle_lines), block)
            self.assertNotIn("领\n域", path.read_text(encoding="utf-8"))

    def test_write_narration_srt_forces_simplified_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "narration.srt"

            write_narration_srt(path, "這一段會引發後續討論，適合放在開頭。", duration=4.0)

            content = path.read_text(encoding="utf-8")
            self.assertIn("这一段会引发后续讨论", content)
            self.assertNotIn("這", content)

    def test_write_narration_srt_prefers_chinese_breakpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "narration.srt"
            text = "生动地解释了AI『锯齿状智能』的悖论——在某些领域是天才，在另一些领域却像个傻瓜。"

            write_narration_srt(path, text, duration=5.0)

            content = path.read_text(encoding="utf-8")
            self.assertNotIn("领\n域", content)
            self.assertIn("悖论——\n在某些领域", content)

    def test_write_narration_srt_uses_short_cues_for_card_intro(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "narration.srt"
            text = (
                "这一章先看：AI的愚蠢时刻：开车去洗车，它叫我走路去。"
                "重点是，这个荒谬又好笑的例子，生动地解释了AI『锯齿状智能』的悖论——"
                "在某些领域是天才，在另一些领域却像个傻瓜。"
            )

            write_narration_srt(path, text, duration=14.0)

            blocks = path.read_text(encoding="utf-8").strip().split("\n\n")
            self.assertGreaterEqual(len(blocks), 3)
            content = path.read_text(encoding="utf-8")
            self.assertIn("在某些领域是天才", content)
            self.assertIn("在另一些领域却像个傻瓜", content)

    def test_mix_card_with_narration_uses_subcap_ass_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            card = root / "card.mp4"
            audio = root / "narration.wav"
            srt = root / "narration.srt"
            output = root / "out.mp4"
            card.write_bytes(b"video")
            audio.write_bytes(b"audio")
            srt.write_text("1\n00:00:00,000 --> 00:00:02,000\n这一章先看模型能力。\n", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run_command(cmd: list[str], log_file=None) -> None:
                calls.append(cmd)
                output.write_bytes(b"mixed")

            with (
                patch("logiccut.chapter_narration.ffprobe_video_size", return_value=(1920, 1080)),
                patch("logiccut.chapter_narration.subtitle_font_name", return_value="Noto Sans CJK SC"),
                patch("logiccut.chapter_narration.run_command", side_effect=fake_run_command),
            ):
                mix_card_with_narration(card, audio, srt, output)

            self.assertTrue(srt.with_suffix(".ass").exists())
            video_filter = calls[0][calls[0].index("-vf") + 1]
            self.assertTrue(video_filter.startswith("ass="), video_filter)
            self.assertNotIn("force_style", video_filter)
            ass_content = srt.with_suffix(".ass").read_text(encoding="utf-8")
            self.assertIn("Style: Default,Noto Sans CJK SC,44", ass_content)
            self.assertIn(",1,3,1,2,48,48,28,1", ass_content)
            self.assertNotIn(",3,14,0,2,100,100,50,1", ass_content)

    def test_synthesize_narration_audio_posts_compatible_tts_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "narration.wav"
            ref_wav = Path(tmp) / "ref.wav"
            ref_wav.write_bytes(b"ref")
            calls: list[dict] = []

            def fake_post(url: str, payload: dict, *, timeout_s: int) -> dict:
                output.write_bytes(b"wav")
                calls.append({"url": url, "payload": payload, "timeout_s": timeout_s})
                return {"success": True, "output_path": str(output), "backend": "indextts2"}

            with patch("logiccut.chapter_narration._post_json", side_effect=fake_post):
                result = synthesize_narration_audio(
                    "这一章先看模型能力。",
                    output,
                    engine="indextts2",
                    voice="logiccut-narrator",
                    tts_ports="8304",
                    backend_options={
                        "ref_wav": str(ref_wav),
                        "ref_text": "参考音频文本。",
                        "language": "zh-CN",
                    },
                )

            self.assertEqual("indextts2", result["engine"])
            self.assertEqual("logiccut-narrator", result["voice"])
            self.assertEqual("http://127.0.0.1:8304/tts", calls[0]["url"])
            payload = calls[0]["payload"]
            self.assertEqual("这一章先看模型能力。", payload["text"])
            self.assertEqual(str(output), payload["output_path"])
            self.assertEqual(str(ref_wav), payload["ref_wav"])
            self.assertEqual("参考音频文本。", payload["ref_text"])
            self.assertEqual("zh-CN", payload["language"])
            self.assertEqual("logiccut-narrator", payload["voice_role"])
            self.assertEqual("chapter_card_narration", payload["backend_options"]["purpose"])

    def test_synthesize_narration_audio_sends_absolute_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = Path("relative-narration.wav")
            calls: list[dict] = []

            def fake_post(_url: str, payload: dict, *, timeout_s: int) -> dict:
                Path(payload["output_path"]).write_bytes(b"wav")
                calls.append(payload)
                return {"success": True, "output_path": payload["output_path"], "backend": "indextts2"}

            with patch("logiccut.chapter_narration._post_json", side_effect=fake_post):
                cwd = Path.cwd()
                try:
                    import os

                    os.chdir(root)
                    synthesize_narration_audio("测试旁白", output, engine="indextts2", tts_ports="8304")
                finally:
                    os.chdir(cwd)

            self.assertTrue(Path(calls[0]["output_path"]).is_absolute())


if __name__ == "__main__":
    unittest.main()
