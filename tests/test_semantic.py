from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from logiccut.semantic import build_semantic_creation_plan, transcribe_media, translate_transcript_segments


class SemanticPlanTest(unittest.TestCase):
    def test_transcribe_media_requires_real_adapter_unless_demo_fallback_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "demo.mp4"
            source.write_bytes(b"not-a-real-video")

            with (
                patch.dict(os.environ, {"LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK": ""}, clear=False),
                patch.dict("sys.modules", {"shorts_generator.local.transcriber": None}),
            ):
                with self.assertRaisesRegex(RuntimeError, "LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK"):
                    transcribe_media(source)

    def test_transcribe_media_demo_fallback_creates_synthetic_segments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "demo.mp4"
            source.write_bytes(b"not-a-real-video")

            with (
                patch.dict(os.environ, {"LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK": "1"}, clear=False),
                patch.dict("sys.modules", {"shorts_generator.local.transcriber": None}),
            ):
                transcript = transcribe_media(source)

        self.assertEqual("logiccut-fallback-transcript", transcript["adapter"])
        self.assertEqual(30.0, transcript["duration"])
        self.assertGreaterEqual(len(transcript["segments"]), 3)

    def test_build_plan_uses_llm_timing_and_records_backend(self) -> None:
        calls: list[str] = []
        transcript = {
            "duration": 110.0,
            "segments": [
                {"start": 0.0, "end": 8.0, "text": "plain intro"},
                {"start": 32.0, "end": 48.0, "text": "the surprising reveal happens here"},
                {"start": 74.0, "end": 94.0, "text": "the conclusion explains the trick"},
            ],
        }

        def fake_llm(prompt: str) -> str:
            calls.append(prompt)
            return json.dumps(
                {
                    "summary": "A merchant story with a reveal and a practical ending.",
                    "translated_segments": [
                        {"start": 0.0, "end": 8.0, "text": "Plain intro."},
                        {"start": 32.0, "end": 48.0, "text": "The reveal happens here."},
                    ],
                    "highlights": [
                        {
                            "title": "The reveal",
                            "start_time": 32.0,
                            "end_time": 48.0,
                            "score": 94,
                            "hook_sentence": "The reveal happens here.",
                            "virality_reason": "It changes the meaning of the setup.",
                        }
                    ],
                    "chapters": [
                        {
                            "title": "Setup",
                            "start_time": 0.0,
                            "end_time": 30.0,
                            "summary": "The setup frames the story.",
                            "insert_strategy": "Use a short title card before the translated segment.",
                        },
                        {
                            "title": "Reveal",
                            "start_time": 30.0,
                            "end_time": 70.0,
                            "summary": "The core reveal makes the clip worth watching.",
                            "insert_strategy": "Open with the reveal as a hook before returning to context.",
                        },
                    ],
                    "remix": {
                        "opening_summary": "Start with the reveal, then explain how the story got there.",
                        "closing_summary": "End by restating the practical takeaway.",
                    },
                }
            )

        plan = build_semantic_creation_plan(
            transcript,
            llm_fn=fake_llm,
            backend_name="fake-gemini",
            target_language="English",
            highlight_count=2,
            chapter_count=2,
        )

        self.assertEqual(len(calls), 1)
        self.assertIn("viral highlight", calls[0])
        self.assertEqual(plan["analysis_meta"]["backend"], "fake-gemini")
        self.assertEqual(plan["highlights"][0]["start_time"], 32.0)
        self.assertEqual(plan["highlights"][0]["score"], 94)
        self.assertEqual(plan["chapters"][1]["title"], "Reveal")
        self.assertIn("opening_summary", plan["remix"])

    def test_build_plan_forces_simplified_chinese_display_text(self) -> None:
        transcript = {
            "duration": 20.0,
            "segments": [{"start": 0.0, "end": 12.0, "text": "traditional output"}],
        }

        def fake_llm(prompt: str) -> str:
            return json.dumps(
                {
                    "summary": "這段會引發後續討論。",
                    "highlights": [
                        {
                            "title": "內容發展",
                            "start_time": 0.0,
                            "end_time": 12.0,
                            "score": 90,
                            "hook_sentence": "這會引發關注。",
                            "virality_reason": "後續討論價值高。",
                        }
                    ],
                    "chapters": [
                        {
                            "title": "開場觀點",
                            "start_time": 0.0,
                            "end_time": 12.0,
                            "summary": "這裡先鋪墊。",
                            "insert_strategy": "補一張總結卡。",
                        }
                    ],
                    "remix": {
                        "opening_summary": "先放總結。",
                        "closing_summary": "最後收束觀點。",
                    },
                },
                ensure_ascii=False,
            )

        plan = build_semantic_creation_plan(
            transcript,
            llm_fn=fake_llm,
            backend_name="fake-gemini",
            target_language="中文",
        )

        self.assertEqual("这段会引发后续讨论。", plan["summary"])
        self.assertEqual("内容发展", plan["highlights"][0]["title"])
        self.assertEqual("这会引发关注。", plan["highlights"][0]["hook_sentence"])
        self.assertEqual("开场观点", plan["chapters"][0]["title"])
        self.assertEqual("先放总结。", plan["remix"]["opening_summary"])

    def test_translate_transcript_segments_chunks_and_preserves_timeline(self) -> None:
        calls: list[str] = []
        transcript = {
            "duration": 40.0,
            "segments": [
                {"start": 0.0, "end": 4.0, "text": "hello world"},
                {"start": 4.0, "end": 8.0, "text": "agentic engineering"},
                {"start": 8.0, "end": 12.0, "text": "final thought"},
            ],
        }

        def fake_llm(prompt: str) -> str:
            calls.append(prompt)
            payload = json.loads(prompt.split("SEGMENTS_JSON:", 1)[1].strip())
            return json.dumps(
                {
                    "translations": [
                        {"index": item["index"], "text": f"中文：{item['text']}"}
                        for item in payload["segments"]
                    ]
                },
                ensure_ascii=False,
            )

        translated = translate_transcript_segments(
            transcript,
            llm_fn=fake_llm,
            target_language="中文",
            max_segments_per_chunk=2,
        )

        self.assertEqual(2, len(calls))
        self.assertEqual(3, len(translated))
        self.assertEqual({"start": 4.0, "end": 8.0, "text": "中文：agentic engineering"}, translated[1])
        self.assertIn("Translate each segment", calls[0])

    def test_translate_transcript_segments_forces_simplified_chinese(self) -> None:
        transcript = {
            "duration": 4.0,
            "segments": [{"start": 0.0, "end": 4.0, "text": "plain"}],
        }

        def fake_llm(prompt: str) -> str:
            return json.dumps(
                {"translations": [{"index": 0, "text": "這會引發後續討論。"}]},
                ensure_ascii=False,
            )

        translated = translate_transcript_segments(transcript, llm_fn=fake_llm, target_language="中文")

        self.assertEqual("这会引发后续讨论。", translated[0]["text"])

    def test_translate_transcript_segments_splits_bad_json_chunk(self) -> None:
        transcript = {
            "duration": 20.0,
            "segments": [
                {"start": 0.0, "end": 2.0, "text": "first"},
                {"start": 2.0, "end": 4.0, "text": "second"},
            ],
        }

        def flaky_llm(prompt: str) -> str:
            payload = json.loads(prompt.split("SEGMENTS_JSON:", 1)[1].strip())
            if len(payload["segments"]) > 1:
                return '{"translations": [{"index": 0, "text": "broken"'
            return json.dumps(
                {
                    "translations": [
                        {
                            "index": payload["segments"][0]["index"],
                            "text": f"中文：{payload['segments'][0]['text']}",
                        }
                    ]
                },
                ensure_ascii=False,
            )

        translated = translate_transcript_segments(
            transcript,
            llm_fn=flaky_llm,
            target_language="中文",
            max_segments_per_chunk=2,
        )

        self.assertEqual(["中文：first", "中文：second"], [item["text"] for item in translated])


if __name__ == "__main__":
    unittest.main()
