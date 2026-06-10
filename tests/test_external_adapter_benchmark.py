from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from logiccut.external_adapter_benchmark import (
    AdapterPOC,
    OpenAICompatibleSettings,
    build_adapter_showcase_html,
    call_ai_shorts_highlight_selector,
    extract_chat_completion_text,
    load_highlights,
    load_openai_compatible_settings,
    normalize_highlight,
    repair_highlight_timestamps,
    summarize_adapter_poc,
)


class ExternalAdapterBenchmarkTest(unittest.TestCase):
    def test_normalize_highlight_accepts_start_end_or_start_time_end_time(self) -> None:
        self.assertEqual(
            {
                "title": "A",
                "start_time": 1.2,
                "end_time": 4.5,
                "score": 9,
                "hook_sentence": "hook",
                "virality_reason": "reason",
            },
            normalize_highlight(
                {
                    "title": "A",
                    "start": 1.2,
                    "end": 4.5,
                    "score": 9,
                    "hook_sentence": "hook",
                    "virality_reason": "reason",
                }
            ),
        )

    def test_load_highlights_reads_dict_items_and_limits_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "highlights.json"
            path.write_text(
                json.dumps(
                    {
                        "items": [
                            {"title": "A", "start": 1, "end": 2},
                            {"title": "B", "start_time": 3, "end_time": 4},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            highlights = load_highlights(path, limit=1)

        self.assertEqual(1, len(highlights))
        self.assertEqual("A", highlights[0]["title"])
        self.assertEqual(1.0, highlights[0]["start_time"])

    def test_summarize_adapter_poc_marks_missing_output(self) -> None:
        poc = AdapterPOC(
            id="demo",
            adapter="AI-Youtube-Shorts-Generator",
            repo_path=Path("third_party/demo"),
            source_path=Path("source.mp4"),
            highlights_path=Path("highlights.json"),
            output_video=Path("missing.mp4"),
            capability="smart vertical crop",
            integration_notes=("uses cropper",),
        )

        report = summarize_adapter_poc(poc, repo_root=Path("/repo"))

        self.assertEqual("demo", report["id"])
        self.assertFalse(report["checks"]["output_exists"]["pass"])
        self.assertIn("smart vertical crop", report["capability"])

    def test_build_adapter_showcase_html_links_reports_and_videos(self) -> None:
        report = {
            "id": "food",
            "adapter": "AI-Youtube-Shorts-Generator",
            "capability": "smart vertical crop",
            "output": {"package_path": "videos/food.mp4", "path": "out.mp4"},
            "checks": {
                "output_exists": {"pass": True, "note": "ok"},
                "has_video_stream": {"pass": True, "note": "ok"},
                "has_audio_stream": {"pass": True, "note": "ok"},
                "no_black_frames": {"pass": True, "note": "ok"},
            },
            "integration_notes": ["cropper only"],
            "media": {"duration": 12.0, "video": {"width": 1080, "height": 1920}},
        }

        html = build_adapter_showcase_html([report])

        self.assertIn("AI-Youtube-Shorts-Generator", html)
        self.assertIn("videos/food.mp4", html)
        self.assertIn("cropper only", html)

    def test_load_openai_compatible_settings_reads_codex_third_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env.third"
            env_file.write_text(
                "\n".join(
                    [
                        "OPENAI_API_KEY=secret-value",
                        "CODEX_THIRD_BASE_URL=https://chatgpt.example/v1",
                        "CODEX_THIRD_MODEL=gpt-test",
                    ]
                ),
                encoding="utf-8",
            )

            settings = load_openai_compatible_settings(env={}, env_file=env_file)

        self.assertEqual("https://chatgpt.example/v1", settings.base_url)
        self.assertEqual("gpt-test", settings.model)
        self.assertEqual("secret-value", settings.api_key)

    def test_call_ai_shorts_highlight_selector_normalizes_and_writes_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "selected.json"
            transcript = {
                "duration": 120.0,
                "segments": [
                    {"start": 0.0, "end": 10.0, "text": "setup"},
                    {"start": 10.0, "end": 70.0, "text": "the surprising story"},
                ],
            }

            result = call_ai_shorts_highlight_selector(
                transcript,
                num_clips=1,
                output_path=output,
                llm_fn=lambda _prompt: (
                    '{"highlights":[{"title":"Surprise","start_time":10,"end_time":70,'
                    '"score":91,"hook_sentence":"wait for it","virality_reason":"clear payoff"}]}'
                ),
                repo_root=Path.cwd(),
            )

            self.assertTrue(output.exists())
            self.assertEqual("Surprise", result["top_highlights"][0]["title"])
            self.assertEqual(91, result["top_highlights"][0]["score"])
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("ai-youtube-shorts-generator", saved["selector"])

    def test_openai_compatible_settings_redacts_secret(self) -> None:
        settings = OpenAICompatibleSettings(api_key="secret-value", base_url="https://example/v1", model="gpt-test")

        self.assertNotIn("secret-value", repr(settings))
        self.assertIn("***REDACTED***", repr(settings))

    def test_extract_chat_completion_text_accepts_string_and_dict_shapes(self) -> None:
        self.assertEqual("plain json", extract_chat_completion_text("plain json"))
        self.assertEqual(
            "dict json",
            extract_chat_completion_text({"choices": [{"message": {"content": "dict json"}}]}),
        )

    def test_repair_highlight_timestamps_removes_duplicate_long_video_chunk_offset(self) -> None:
        repaired = repair_highlight_timestamps(
            [
                {
                    "title": "A",
                    "start_time": 5077.1,
                    "end_time": 5134.8,
                    "score": 95,
                    "hook_sentence": "hook",
                    "virality_reason": "reason",
                }
            ],
            duration=3310.42,
        )

        self.assertAlmostEqual(2797.1, repaired[0]["start_time"])
        self.assertAlmostEqual(2854.8, repaired[0]["end_time"])

    def test_summarize_adapter_poc_fails_when_fewer_clips_than_selected_highlights(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "third_party/demo"
            source = root / "source.mp4"
            selected = root / "selected.json"
            output = root / "out/montage.mp4"
            clips = output.parent / "clips"
            repo.mkdir(parents=True)
            clips.mkdir(parents=True)
            source.write_bytes(b"source")
            output.write_bytes(b"video")
            (clips / "short_01.mp4").write_bytes(b"clip")
            selected.write_text(
                json.dumps(
                    {
                        "top_highlights": [
                            {"title": "A", "start_time": 1, "end_time": 2},
                            {"title": "B", "start_time": 3, "end_time": 4},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            poc = AdapterPOC(
                id="demo",
                adapter="AI-Youtube-Shorts-Generator",
                repo_path=repo,
                source_path=source,
                highlights_path=selected,
                output_video=output,
                capability="selector",
                integration_notes=(),
                use_llm_selector=True,
            )

            report = summarize_adapter_poc(poc, repo_root=root, run_blackdetect=False)

        self.assertFalse(report["checks"]["rendered_all_selected_clips"]["pass"])


if __name__ == "__main__":
    unittest.main()
