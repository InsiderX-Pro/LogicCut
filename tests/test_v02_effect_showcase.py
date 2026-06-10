from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


class V02EffectShowcaseTest(unittest.TestCase):
    def test_build_showcase_html_documents_v01_and_v02_outputs(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "build_v02_effect_showcase.py"
        spec = importlib.util.spec_from_file_location("build_v02_effect_showcase", script)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        html = module.build_showcase_html(
            {
                "template_gallery": "template-gallery/index.html",
                "template_research": "docs/template-reuse-research.html",
                "v01_video": "project/renders/chapter_card_narration/chapter_card_narration.mp4",
                "v02_video": "project/renders/guided_highlights/guided_highlights.mp4",
                "v02_card_html": "project/assets/guided_highlights/guided_card_01.html",
                "v02_card_image": "project/assets/guided_highlights/guided_card_01.png",
                "v02_subtitle": "project/assets/guided_highlights/guided_card_01_narration.srt",
                "v02_manifest": "project/project.json",
            }
        )

        self.assertIn("v0.1", html)
        self.assertIn("v0.2", html)
        self.assertIn("章节卡片旁白", html)
        self.assertIn("导览高光成片", html)
        self.assertIn("template-gallery/index.html", html)
        self.assertIn("guided_highlights.mp4", html)
        self.assertIn("guided_card_01.html", html)


if __name__ == "__main__":
    unittest.main()
