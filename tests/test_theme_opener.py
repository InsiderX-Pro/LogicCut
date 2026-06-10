from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from logiccut.theme_opener import (
    build_codex_prompt,
    load_theme_opener_plan,
    write_theme_opener_codex_prompt,
)


class ThemeOpenerTest(unittest.TestCase):
    def test_build_codex_prompt_describes_no_runtime_llm_and_json_schema(self) -> None:
        transcript = {
            "duration": 60.0,
            "segments": [
                {"start": 0.0, "end": 4.0, "text": "I feel safe walking here at night."},
                {"start": 10.0, "end": 13.0, "text": "The streets are still busy and relaxed."},
            ],
        }

        prompt = build_codex_prompt(
            transcript,
            source_name="bilibili-demo.mp4",
            theme="中国安全",
            target_seconds=20,
        )

        self.assertIn("Codex", prompt)
        self.assertIn("不要调用 OpenAI/Gemini/Claude API", prompt)
        self.assertIn("theme_opener_plan.json", prompt)
        self.assertIn('"clips"', prompt)
        self.assertIn("中国安全", prompt)
        self.assertIn("[0.00-4.00]", prompt)

    def test_write_theme_opener_codex_prompt_creates_prompt_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "codex_prompt.md"

            write_theme_opener_codex_prompt(
                output,
                {"duration": 5.0, "segments": [{"start": 0.0, "end": 5.0, "text": "demo"}]},
                source_name="source.mp4",
                theme="中国安全",
            )

            self.assertTrue(output.exists())
            self.assertIn("source.mp4", output.read_text(encoding="utf-8"))

    def test_load_theme_opener_plan_validates_duration_and_simplifies_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "theme_opener_plan.json"
            path.write_text(
                json.dumps(
                    {
                        "theme": "中國安全",
                        "opening_hook": "外國人發現中國夜晚很安全。",
                        "clips": [
                            {
                                "start": 1.0,
                                "end": 7.0,
                                "subtitle": "晚上也很安心。",
                                "reason": "直接證明安全感。",
                                "visual_role": "建立主題",
                            },
                            {
                                "start": 12.0,
                                "end": 18.0,
                                "subtitle": "街上還有很多人。",
                                "reason": "補充環境證據。",
                                "visual_role": "增加可信度",
                            },
                            {
                                "start": 25.0,
                                "end": 32.0,
                                "subtitle": "這裡讓人放鬆。",
                                "reason": "收束主題。",
                                "visual_role": "情緒收尾",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            plan = load_theme_opener_plan(path, source_duration=80.0)

        self.assertEqual("中国安全", plan["theme"])
        self.assertEqual("外国人发现中国夜晚很安全。", plan["opening_hook"])
        self.assertEqual(19.0, plan["total_duration"])
        self.assertEqual("直接证明安全感。", plan["clips"][0]["reason"])
        self.assertEqual("建立主题", plan["clips"][0]["visual_role"])

    def test_load_theme_opener_plan_rejects_out_of_range_total_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "theme_opener_plan.json"
            path.write_text(
                json.dumps(
                    {
                        "theme": "中国安全",
                        "opening_hook": "demo",
                        "clips": [
                            {"start": 1.0, "end": 3.0, "subtitle": "a", "reason": "r", "visual_role": "v"},
                            {"start": 4.0, "end": 6.0, "subtitle": "b", "reason": "r", "visual_role": "v"},
                            {"start": 7.0, "end": 9.0, "subtitle": "c", "reason": "r", "visual_role": "v"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "15-30 seconds"):
                load_theme_opener_plan(path, source_duration=80.0)

    def test_load_theme_opener_plan_snaps_clip_end_to_transcript_sentence_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "theme_opener_plan.json"
            path.write_text(
                json.dumps(
                    {
                        "theme": "中国安全",
                        "opening_hook": "demo",
                        "clips": [
                            {"start": 0.0, "end": 5.0, "subtitle": "a", "reason": "r", "visual_role": "v"},
                            {"start": 10.0, "end": 15.2, "subtitle": "b", "reason": "r", "visual_role": "v"},
                            {"start": 20.0, "end": 25.08, "subtitle": "c", "reason": "r", "visual_role": "v"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            transcript = {
                "segments": [
                    {"start": 20.0, "end": 25.02, "text": "This is the selected sentence."},
                    {"start": 25.03, "end": 28.0, "text": "This sentence should not leak into the cut."},
                ]
            }

            plan = load_theme_opener_plan(path, source_duration=80.0, transcript=transcript)

        self.assertEqual(24.94, plan["clips"][2]["end"])
        self.assertEqual(4.94, plan["clips"][2]["duration"])
        self.assertEqual(15.14, plan["total_duration"])


if __name__ == "__main__":
    unittest.main()
