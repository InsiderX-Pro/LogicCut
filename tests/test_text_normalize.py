from __future__ import annotations

import unittest

from logiccut.text_normalize import assert_simplified_text, contains_traditional, normalize_display_text


class TextNormalizeTest(unittest.TestCase):
    def test_normalize_display_text_forces_simplified_chinese(self) -> None:
        text = normalize_display_text("這個案例會引發後續討論，並推動內容發展。")

        self.assertEqual("这个案例会引发后续讨论，并推动内容发展。", text)
        self.assertFalse(contains_traditional(text))

    def test_assert_simplified_text_rejects_residual_traditional_characters(self) -> None:
        with self.assertRaisesRegex(ValueError, "traditional Chinese"):
            assert_simplified_text("这个文本仍然有發字。")


if __name__ == "__main__":
    unittest.main()
