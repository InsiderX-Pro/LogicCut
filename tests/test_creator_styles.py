from __future__ import annotations

import unittest

from logiccut.creator_styles import (
    build_personalized_narration,
    get_creator_style,
    parse_catchphrases,
    parse_style_ids,
)
from logiccut.html_cards import HighlightCard


class CreatorStylesTest(unittest.TestCase):
    def test_parse_style_ids_defaults_to_four_creator_tones(self) -> None:
        self.assertEqual(("calm", "sharp", "science", "entertainment"), parse_style_ids(""))
        self.assertEqual(("calm", "sharp"), parse_style_ids("冷静, 犀利"))
        self.assertEqual(("science", "entertainment"), parse_style_ids("science, entertainment"))

    def test_parse_catchphrases_normalizes_and_filters_empty_items(self) -> None:
        self.assertEqual(("注意看", "说人话"), parse_catchphrases("注意看，說人話,, "))

    def test_build_personalized_narration_uses_style_and_catchphrase(self) -> None:
        card = HighlightCard(
            index=1,
            title="模型能力的真正分水岭",
            reason="语义密度高，观点完整，适合作为章节高光。",
            hook="这一段解释了 Agent 为什么会变得不一样。",
            score=92,
            start=1,
            end=9,
            keywords=("模型", "Agent"),
        )

        text = build_personalized_narration(
            card,
            get_creator_style("sharp"),
            catchphrases=("注意看",),
        )

        self.assertIn("注意看", text)
        self.assertIn("这段先别温吞", text)
        self.assertIn("Agent", text)
        self.assertLessEqual(len(text), 118)


if __name__ == "__main__":
    unittest.main()
