from __future__ import annotations

import unittest

from logiccut.story_planner import build_story_timeline_from_semantic_plan


class StoryPlannerTest(unittest.TestCase):
    def test_build_story_timeline_alternates_narration_and_original_segments(self) -> None:
        plan = {
            "summary": "A food tour with several strong tasting moments.",
            "highlights": [
                {
                    "id": "h1",
                    "title": "Market opening",
                    "start_time": 10.0,
                    "end_time": 18.0,
                    "score": 93,
                    "hook_sentence": "The market is already packed.",
                    "virality_reason": "It establishes the place quickly.",
                },
                {
                    "id": "h2",
                    "title": "First bite",
                    "start_time": 40.0,
                    "end_time": 47.0,
                    "score": 96,
                    "hook_sentence": "That first bite changes the mood.",
                    "virality_reason": "The reaction sells the food.",
                },
            ],
        }

        timeline = build_story_timeline_from_semantic_plan(
            plan,
            duration=90.0,
            style_id="story_travel",
            item_count=2,
            narration_duration=3.0,
            original_duration=4.0,
        )

        self.assertEqual("story_travel", timeline["style_id"])
        self.assertEqual(4, len(timeline["items"]))
        self.assertEqual([0, 1, 0, 1], [item["OST"] for item in timeline["items"]])
        self.assertEqual("narration", timeline["items"][0]["type"])
        self.assertEqual("original", timeline["items"][1]["type"])
        self.assertIn("Market opening", timeline["items"][0]["narration"])
        self.assertEqual("播放原片2", timeline["items"][1]["narration"])
        self.assertLessEqual(timeline["items"][1]["end"] - timeline["items"][1]["start"], 4.0)
        self.assertIn("why", timeline["items"][1])

    def test_build_story_timeline_can_use_custom_micro_highlights_key(self) -> None:
        plan = {
            "micro_food_highlights": [
                {
                    "title": "Sizzling noodles",
                    "start_time": 23.0,
                    "end_time": 27.0,
                    "score": 88,
                    "hook_sentence": "The wok sound grabs attention.",
                    "virality_reason": "It is sensory and fast.",
                }
            ]
        }

        timeline = build_story_timeline_from_semantic_plan(plan, duration=60.0, item_count=1)

        self.assertEqual(2, len(timeline["items"]))
        self.assertIn("Sizzling noodles", timeline["items"][0]["picture"])

    def test_build_story_timeline_removes_terminal_title_punctuation_in_narration(self) -> None:
        plan = {
            "highlights": [
                {
                    "title": "像鸡肉的豆腐？",
                    "start_time": 12.0,
                    "end_time": 16.0,
                    "virality_reason": "将豆腐比作鸡肉的口感，引发好奇。",
                }
            ]
        }

        timeline = build_story_timeline_from_semantic_plan(
            plan,
            duration=30.0,
            style_id="story_travel",
            item_count=1,
        )

        self.assertIn("像鸡肉的豆腐", timeline["items"][0]["narration"])
        self.assertNotIn("？。", timeline["items"][0]["narration"])

    def test_drama_style_does_not_join_question_title_with_started(self) -> None:
        plan = {
            "highlights": [
                {
                    "title": "你没见过盲聋人士吗？",
                    "start_time": 12.0,
                    "end_time": 16.0,
                    "virality_reason": "冲突问题快速建立人物处境。",
                }
            ]
        }

        timeline = build_story_timeline_from_semantic_plan(
            plan,
            duration=30.0,
            style_id="story_drama",
            item_count=1,
        )

        self.assertIn("这一幕是你没见过盲聋人士吗", timeline["items"][0]["narration"])
        self.assertNotIn("吗开始", timeline["items"][0]["narration"])


if __name__ == "__main__":
    unittest.main()
