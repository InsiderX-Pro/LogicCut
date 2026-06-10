from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from logiccut import html_cards
from logiccut.html_cards import build_highlight_card, list_card_templates, render_card_html, render_html_card_video


EXPECTED_TEMPLATE_IDS = {
    "news-hook",
    "data-insight",
    "timeline-chapter",
    "quote-focus",
    "conflict-card",
    "vertical-hook",
    "tech-flash",
    "chip-keynote",
    "neon-corridor",
    "vertical-tech-news",
    "hologram-brief",
    "cyber-lower-third",
}


class HtmlCardsTest(unittest.TestCase):
    def test_build_highlight_card_extracts_story_fields(self) -> None:
        card = build_highlight_card(
            {
                "title": "AI 大神也怕落后",
                "start_time": 35.78,
                "end_time": 42.78,
                "score": 95,
                "hook_sentence": "never felt more behind as a programmer",
                "virality_reason": "来自 OpenAI 共同创办人的惊人言论，创造反差和共鸣。",
            },
            index=2,
        )

        self.assertEqual(2, card.index)
        self.assertEqual(95, card.score)
        self.assertEqual(35.78, card.start)
        self.assertIn("OpenAI", card.keywords)

    def test_build_highlight_card_normalizes_simplified_chinese(self) -> None:
        card = build_highlight_card(
            {
                "title": "AI的愚蠢時刻：開車去洗車，它叫我走路去",
                "start_time": 1,
                "end_time": 8,
                "hook_sentence": "讓觀眾先看到轉折。",
                "virality_reason": "這個荒謬又好笑的例子，生動地解釋了AI『鋸齒狀智能』的悖論，並引發人們對AI本質的討論。",
            },
            index=1,
        )

        self.assertIn("AI的愚蠢时刻：开车去洗车", card.title)
        self.assertIn("让观众先看到转折", card.hook)
        self.assertNotIn("這", card.reason)
        self.assertNotIn("鋸齒狀", card.reason)
        self.assertIn("锯齿状智能", card.reason)

    def test_build_highlight_card_uses_chinese_reason_when_hook_is_english(self) -> None:
        card = build_highlight_card(
            {
                "title": "AI大神也怕落后",
                "start_time": 35.78,
                "end_time": 42.78,
                "hook_sentence": "he said something even more startling that he's never felt more behind as a programmer.",
                "virality_reason": "来自 OpenAI 共同创办人的惊人言论，创造了巨大的反差和共鸣。",
            },
            index=2,
        )

        self.assertNotIn("he said", card.hook)
        self.assertIn("OpenAI", card.hook)

    def test_render_html_card_video_prefers_browser_rendered_hyperframes_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            card = build_highlight_card(
                {
                    "title": "先看最有争议的判断",
                    "start_time": 3,
                    "end_time": 12,
                    "score": 91,
                    "hook_sentence": "这一句能直接抓住观众。",
                    "virality_reason": "观点冲突强，适合作为章节开场。",
                },
                index=1,
            )

            with (
                patch.object(html_cards, "_extract_poster"),
                patch.object(html_cards, "_render_html_snapshot", return_value=True) as snapshot,
                patch.object(html_cards, "_paint_card") as paint,
                patch.object(html_cards, "_image_to_video") as image_to_video,
            ):
                render_html_card_video(
                    card=card,
                    source_video=source,
                    output_html=root / "card.html",
                    output_image=root / "card.png",
                    output_video=root / "card.mp4",
                    duration=5,
                    size=(1280, 720),
                )

            html = (root / "card.html").read_text(encoding="utf-8")
            self.assertIn('data-composition-id="logiccut-chapter-card"', html)
            self.assertIn("template-news-hook", html)
            snapshot.assert_called_once()
            paint.assert_not_called()
            image_to_video.assert_called_once()

    def test_render_html_snapshot_returns_false_when_browser_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html_path = root / "card.html"
            html_path.write_text("<html></html>", encoding="utf-8")

            with patch("logiccut.html_cards.subprocess.run", side_effect=OSError("node missing")):
                rendered = html_cards._render_html_snapshot(html_path, root / "card.png", size=(1280, 720))

            self.assertFalse(rendered)

    def test_card_template_registry_exposes_expected_templates(self) -> None:
        templates = list_card_templates()
        template_ids = {item.id for item in templates}

        self.assertTrue(EXPECTED_TEMPLATE_IDS.issubset(template_ids))
        for template in templates:
            self.assertTrue(template.template_path.exists())
            self.assertIn("16:9", template.aspect_ratios)
            self.assertGreater(template.max_title_chars, 0)
            self.assertTrue(template.template_pack)
            self.assertTrue(template.source_type)
            self.assertTrue(template.origin_license)
            self.assertTrue(template.origin_repo)
            self.assertTrue(template.adaptation_notes)

    def test_render_card_html_uses_selected_template_and_normalized_data(self) -> None:
        card = build_highlight_card(
            {
                "title": "這個案例會引發後續討論",
                "start_time": 10,
                "end_time": 20,
                "score": 88,
                "hook_sentence": "這一段適合放到開頭。",
                "virality_reason": "它能推動內容發展。",
            },
            index=3,
        )

        for template_id in EXPECTED_TEMPLATE_IDS:
            html = render_card_html(card, "poster.jpg", size=(1280, 720), template_id=template_id)
            self.assertIn('data-composition-id="logiccut-chapter-card"', html)
            self.assertIn(f"template-{template_id}", html)
            self.assertIn("这个案例会引发后续讨论", html)
            self.assertNotIn("{{", html)
            self.assertNotIn("發", html)

    def test_render_card_html_embeds_clean_poster_fallback(self) -> None:
        card = build_highlight_card(
            {
                "title": "卡片预览",
                "start_time": 0,
                "end_time": 6,
                "hook_sentence": "没有源帧时也要展示干净占位。",
                "virality_reason": "模板 registry 需要支持独立预览。",
            },
            index=1,
        )

        html_with_poster = render_card_html(card, "missing-poster.jpg", size=(1280, 720), template_id="news-hook")
        html_without_poster = render_card_html(card, "", size=(1280, 720), template_id="news-hook")

        self.assertIn("onerror=", html_with_poster)
        self.assertIn('class="workflow" hidden', html_with_poster)
        self.assertIn('class="workflow"', html_without_poster)
        self.assertNotIn('class="workflow" hidden', html_without_poster)


if __name__ == "__main__":
    unittest.main()
