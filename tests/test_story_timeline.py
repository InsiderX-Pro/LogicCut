from __future__ import annotations

import unittest

from logiccut.story_timeline import normalize_story_timeline, parse_story_timestamp


class StoryTimelineTest(unittest.TestCase):
    def test_parse_story_timestamp_supports_narratoai_range_format(self) -> None:
        start, end = parse_story_timestamp("00:01:12,000-00:01:18,250")

        self.assertEqual(72.0, start)
        self.assertEqual(78.25, end)

    def test_normalize_story_timeline_validates_ost_and_simplifies_text(self) -> None:
        timeline = normalize_story_timeline(
            {
                "story_arc": "這是一段探店開場。",
                "items": [
                    {
                        "_id": 1,
                        "timestamp": "00:00:01,000-00:00:04,000",
                        "picture": "店門與招牌",
                        "narration": "這家店先看招牌。",
                        "OST": 0,
                        "why": "建立地點。",
                    },
                    {
                        "_id": 2,
                        "timestamp": "00:00:05,000-00:00:08,000",
                        "picture": "主持人試吃",
                        "narration": "播放原片2",
                        "OST": 1,
                        "why": "保留真實反應。",
                    },
                ],
            },
            duration=12.0,
        )

        self.assertEqual("这是一段探店开场。", timeline["story_arc"])
        self.assertEqual("narration", timeline["items"][0]["type"])
        self.assertEqual("original", timeline["items"][1]["type"])
        self.assertEqual("店门与招牌", timeline["items"][0]["picture"])
        self.assertEqual(5.0, timeline["items"][1]["start"])
        self.assertEqual(8.0, timeline["items"][1]["end"])

    def test_normalize_story_timeline_rejects_overlapping_source_ranges(self) -> None:
        with self.assertRaisesRegex(ValueError, "overlap"):
            normalize_story_timeline(
                {
                    "items": [
                        {"_id": 1, "timestamp": "00:00:01,000-00:00:05,000", "narration": "a", "OST": 0},
                        {"_id": 2, "timestamp": "00:00:04,500-00:00:07,000", "narration": "b", "OST": 1},
                    ]
                },
                duration=10.0,
            )

    def test_normalize_story_timeline_rejects_unknown_ost(self) -> None:
        with self.assertRaisesRegex(ValueError, "OST"):
            normalize_story_timeline(
                {
                    "items": [
                        {"_id": 1, "timestamp": "00:00:01,000-00:00:05,000", "narration": "a", "OST": 3},
                    ]
                },
                duration=10.0,
            )


if __name__ == "__main__":
    unittest.main()
