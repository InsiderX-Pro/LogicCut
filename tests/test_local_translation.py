from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from logiccut.translation.pipeline import (
    LocalTranslationConfig,
    build_codex_translation_prompt,
    run_local_translation,
)
from logiccut.translation.setup import build_translation_setup_plan


class LocalTranslationPipelineTest(unittest.TestCase):
    def test_first_run_writes_codex_prompt_and_waits_for_translation_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            transcript = root / "transcript.json"
            output_dir = root / "translation"
            source.write_bytes(b"video")
            transcript.write_text(
                json.dumps(
                    {
                        "duration": 12.0,
                        "segments": [
                            {"start": 0.0, "end": 4.0, "text": "hello world"},
                            {"start": 4.0, "end": 8.0, "text": "this is LogicCut"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = run_local_translation(
                LocalTranslationConfig(
                    input_video=source,
                    output_dir=output_dir,
                    transcript_json=transcript,
                    target_language="中文",
                )
            )

            self.assertEqual("needs_codex_translation", result.status)
            self.assertTrue((output_dir / "source_transcript.json").exists())
            self.assertTrue((output_dir / "codex_translation_prompt.md").exists())
            self.assertTrue((output_dir / "translated_segments.todo.json").exists())
            self.assertIn("translated_segments.json", (output_dir / "codex_translation_prompt.md").read_text(encoding="utf-8"))
            manifest = json.loads((output_dir / "translation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("logiccut-local", manifest["backend"])
            self.assertEqual("needs_codex_translation", manifest["status"])

    def test_second_run_burns_subtitles_from_codex_translation_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            transcript = root / "transcript.json"
            translated = root / "translated_segments.json"
            output_dir = root / "translation"
            source.write_bytes(b"video")
            transcript.write_text(
                json.dumps(
                    {
                        "duration": 8.0,
                        "segments": [
                            {"start": 0.0, "end": 4.0, "text": "hello world"},
                            {"start": 4.0, "end": 8.0, "text": "this is LogicCut"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            translated.write_text(
                json.dumps(
                    {
                        "target_language": "中文",
                        "segments": [
                            {"start": 0.0, "end": 4.0, "text": "你好，世界。"},
                            {"start": 4.0, "end": 8.0, "text": "这是 LogicCut。"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("logiccut.translation.pipeline.burn_subtitles", return_value=output_dir / "output_video_subtitled.mp4") as burn_mock:
                result = run_local_translation(
                    LocalTranslationConfig(
                        input_video=source,
                        output_dir=output_dir,
                        transcript_json=transcript,
                        translation_json=translated,
                        burn_subtitles=True,
                    )
                )

            self.assertEqual("ok", result.status)
            burn_mock.assert_called_once()
            subtitle = (output_dir / "translated_subtitles.srt").read_text(encoding="utf-8")
            self.assertIn("你好，世界。", subtitle)
            self.assertIn("这是 LogicCut。", subtitle)
            manifest = json.loads((output_dir / "translation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("output_video_subtitled.mp4", Path(manifest["output_video"]).name)
            self.assertEqual("codex-file", manifest["translation_driver"])

    def test_codex_prompt_instructs_file_based_translation_without_runtime_llm_key(self) -> None:
        prompt = build_codex_translation_prompt(
            {
                "segments": [
                    {"start": 0.0, "end": 3.5, "text": "Keep the timing."},
                ]
            },
            target_language="中文",
            output_filename="translated_segments.json",
        )

        self.assertIn("不要调用 OpenAI/Gemini/Claude API", prompt)
        self.assertIn("translated_segments.json", prompt)
        self.assertIn("Keep the timing.", prompt)

    def test_translation_setup_plan_lists_minimal_and_optional_dependencies(self) -> None:
        plan = build_translation_setup_plan(profile="minimal", install=False)

        self.assertEqual("translation", plan["component"])
        self.assertFalse(plan["install"])
        self.assertIn("ffmpeg", plan["system_dependencies"])
        self.assertIn("faster-whisper", " ".join(plan["optional_python_packages"]))
        self.assertTrue(any("huggingface.co/Systran/faster-whisper-base" in str(item) for item in plan["model_sources"]))
        self.assertTrue(any("logiccut translate-video --backend logiccut-local" in command for command in plan["smoke_commands"]))


if __name__ == "__main__":
    unittest.main()
