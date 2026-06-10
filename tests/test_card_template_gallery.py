from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from logiccut.card_templates import list_card_templates


class CardTemplateGalleryTest(unittest.TestCase):
    def test_build_gallery_html_lists_all_templates(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "render_card_template_gallery.py"
        spec = importlib.util.spec_from_file_location("render_card_template_gallery", script)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        html = module.build_gallery_html(
            [
                {
                    "id": template.id,
                    "name": template.name,
                    "description": template.description,
                    "image": f"{template.id}.png",
                    "aspect": "9:16" if template.id == "vertical-hook" else "16:9",
                }
                for template in list_card_templates()
            ]
        )

        for template in list_card_templates():
            self.assertIn(template.id, html)
            self.assertIn(template.name, html)
            self.assertIn(f"{template.id}.png", html)

    def test_build_gallery_records_includes_each_supported_aspect_and_origin(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "render_card_template_gallery.py"
        spec = importlib.util.spec_from_file_location("render_card_template_gallery", script)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        records = module.build_gallery_records(render=False)
        record_keys = {(item["id"], item["aspect"]) for item in records}

        for template in list_card_templates():
            for aspect in template.aspect_ratios:
                self.assertIn((template.id, aspect), record_keys)
            matched = [item for item in records if item["id"] == template.id]
            self.assertTrue(all(item["origin_repo"] for item in matched))
            self.assertTrue(all(item["origin_license"] for item in matched))
            self.assertTrue(all(item["template_pack"] for item in matched))

    def test_build_gallery_records_can_filter_by_template_pack(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "render_card_template_gallery.py"
        spec = importlib.util.spec_from_file_location("render_card_template_gallery", script)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        records = module.build_gallery_records(render=False, template_pack="tech-news-neon")

        self.assertTrue(records)
        self.assertTrue(all(item["template_pack"] == "tech-news-neon" for item in records))
        self.assertEqual({"tech-flash", "chip-keynote", "neon-corridor", "vertical-tech-news", "hologram-brief", "cyber-lower-third"}, {item["id"] for item in records})


if __name__ == "__main__":
    unittest.main()
