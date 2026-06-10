from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logiccut.omnivoice_pipeline import (
    SpeechSegment,
    _auto_clone_profiles,
    _profile_for_segment,
    merge_segments_for_dubbing,
    write_srt,
    write_vtt,
)


class OmniVoicePipelineTest(unittest.TestCase):
    def test_merge_segments_respects_duration_and_character_limits(self) -> None:
        segments = [
            {"start": 0.0, "end": 3.0, "text": "第一句"},
            {"start": 3.0, "end": 6.0, "text": "第二句"},
            {"start": 6.0, "end": 12.5, "text": "第三句很长"},
            {"start": 12.5, "end": 15.0, "text": "第四句"},
        ]

        merged = merge_segments_for_dubbing(segments, max_duration=7.0, max_chars=20)

        self.assertEqual(
            [
                SpeechSegment(0.0, 6.0, "第一句 第二句"),
                SpeechSegment(6.0, 12.5, "第三句很长"),
                SpeechSegment(12.5, 15.0, "第四句"),
            ],
            merged,
        )

    def test_write_srt_uses_subrip_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dub.srt"

            write_srt(path, [SpeechSegment(1.25, 4.5, "你好")])

            self.assertIn("00:00:01,250 --> 00:00:04,500", path.read_text(encoding="utf-8"))

    def test_write_vtt_uses_webvtt_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dub.vtt"

            write_vtt(path, [SpeechSegment(1.25, 4.5, "你好")])

            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("WEBVTT"))
            self.assertIn("00:00:01.250 --> 00:00:04.500", text)

    def test_auto_clone_profiles_use_omnivoice_profile_ids(self) -> None:
        profiles = _auto_clone_profiles(
            {
                "speaker_clones": {
                    "Speaker 1": {"ref_audio": "/tmp/voice_speaker_1.wav"},
                    "Guest-A": {"ref_audio": "/tmp/voice_guest_a.wav"},
                    "Broken": {},
                }
            }
        )

        self.assertEqual(
            {
                "Speaker 1": "auto:speaker_1",
                "Guest-A": "auto:guest_a",
            },
            profiles,
        )

    def test_profile_for_imported_segment_matches_source_speaker_by_overlap(self) -> None:
        source_segments = [
            {"start": 0.0, "end": 4.0, "speaker_id": "Speaker 1"},
            {"start": 4.0, "end": 8.0, "speaker_id": "Speaker 2"},
        ]
        clone_profiles = {
            "Speaker 1": "auto:speaker_1",
            "Speaker 2": "auto:speaker_2",
        }

        profile = _profile_for_segment(
            {"start": 4.5, "end": 7.0, "text": "导入字幕"},
            source_segments=source_segments,
            clone_profiles=clone_profiles,
        )

        self.assertEqual("auto:speaker_2", profile)

    def test_profile_for_segment_uses_fallback_profile_without_auto_clones(self) -> None:
        profile = _profile_for_segment(
            {"start": 0.0, "end": 2.0, "text": "导入字幕"},
            source_segments=[],
            clone_profiles={},
            fallback_profile_id="source-prof",
        )

        self.assertEqual("source-prof", profile)


if __name__ == "__main__":
    unittest.main()
