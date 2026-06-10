from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from logiccut.story_render import render_story_timeline


class StoryRenderTest(unittest.TestCase):
    def test_render_story_timeline_routes_ost_segments_to_expected_renderers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            source = root / "source.mp4"
            source.write_bytes(b"source")
            timeline = {
                "items": [
                    {
                        "_id": 1,
                        "type": "narration",
                        "start": 1.0,
                        "end": 4.0,
                        "narration": "先用旁白铺垫。",
                        "OST": 0,
                        "why": "建立期待。",
                    },
                    {
                        "_id": 2,
                        "type": "original",
                        "start": 6.0,
                        "end": 9.0,
                        "narration": "播放原片2",
                        "OST": 1,
                        "why": "保留反应。",
                    },
                ]
            }
            translated_segments = [{"start": 6.0, "end": 8.0, "text": "中文字幕"}]
            calls: list[tuple[str, float, float]] = []

            def fake_render_clip(_source: Path, output: Path, start: float, duration: float, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(f"clip:{start}:{duration}".encode())
                calls.append(("clip", start, duration))
                return output

            def fake_synthesize(_text: str, output_path: Path, **_kwargs) -> dict:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"voice")
                return {"success": True, "backend": "fake"}

            def fake_mix(source_clip: Path, _audio: Path, _subtitle: Path, output: Path, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(source_clip.read_bytes() + b"+mixed")
                return output

            def fake_burn(raw: Path, _subtitle: Path, output: Path, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(raw.read_bytes() + b"+sub")
                return output

            def fake_concat(inputs: list[Path], output: Path, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"".join(path.read_bytes() for path in inputs))
                return output

            with (
                patch("logiccut.story_render.render_clip", side_effect=fake_render_clip),
                patch("logiccut.story_render.prepare_narration_reference", return_value=root / "ref.wav"),
                patch("logiccut.story_render.synthesize_narration_audio", side_effect=fake_synthesize),
                patch("logiccut.story_render.mix_narration_over_source", side_effect=fake_mix),
                patch("logiccut.story_render.burn_subtitles", side_effect=fake_burn),
                patch("logiccut.story_render.concat_videos_reencode", side_effect=fake_concat),
            ):
                result = render_story_timeline(
                    project,
                    source=source,
                    timeline=timeline,
                    translated_segments=translated_segments,
                )

            self.assertTrue(result["output"].exists())
            self.assertEqual([("clip", 1.0, 3.0), ("clip", 6.0, 3.0)], calls)
            self.assertEqual(2, len(result["parts"]))
            self.assertEqual("narration", result["parts"][0]["type"])
            self.assertEqual("original", result["parts"][1]["type"])


if __name__ == "__main__":
    unittest.main()
