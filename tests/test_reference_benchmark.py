from __future__ import annotations

import unittest
from pathlib import Path

from logiccut.reference_benchmark import (
    ReferenceCase,
    ReferencePattern,
    build_benchmark_html,
    build_case_report,
    build_reference_analysis_html,
    default_reference_cases,
    parse_blackdetect_output,
)


class ReferenceBenchmarkTest(unittest.TestCase):
    def test_default_reference_cases_are_specific_and_external(self) -> None:
        cases = default_reference_cases(Path("/repo"))

        self.assertEqual(["movie_recap_drama", "food_micro_montage"], [case.id for case in cases])
        self.assertTrue(all(case.reference_url.startswith("https://www.youtube.com/watch?v=") for case in cases))
        self.assertTrue(all(case.source_path for case in cases))
        self.assertTrue(all(case.reproduction_path for case in cases))
        self.assertIn("hook", cases[0].pattern.required_elements)
        self.assertFalse(cases[0].pattern.black_frames_allowed)

    def test_parse_blackdetect_output_extracts_segments(self) -> None:
        text = """
        [blackdetect @ 0x123] black_start:1.2 black_end:2.0 black_duration:0.8
        [blackdetect @ 0x123] black_start:9 black_end:9.7 black_duration:0.7
        """

        segments = parse_blackdetect_output(text)

        self.assertEqual(
            [
                {"start": 1.2, "end": 2.0, "duration": 0.8},
                {"start": 9.0, "end": 9.7, "duration": 0.7},
            ],
            segments,
        )

    def test_build_case_report_marks_missing_reproduction_as_failed(self) -> None:
        case = ReferenceCase(
            id="demo",
            title="Demo",
            category="movie_recap",
            reference_title="Reference",
            reference_url="https://www.youtube.com/watch?v=abc123",
            reference_channel="Ref Channel",
            source_label="Demo source",
            source_path=Path("source.mp4"),
            reproduction_path=Path("missing.mp4"),
            pattern=ReferencePattern(
                id="movie_recap",
                summary="Test pattern",
                required_elements=("hook", "captions"),
                shot_length_range=(1.0, 4.0),
                black_frames_allowed=False,
                narration_mode="continuous",
                original_audio_ratio=0.15,
                caption_style="large subtitles",
                breakdown=("hook", "proof"),
            ),
        )

        report = build_case_report(case, repo_root=Path("/repo"))

        self.assertFalse(report["checks"]["reproduction_exists"]["pass"])
        self.assertFalse(report["checks"]["machine_ready"]["pass"])
        self.assertIn("movie_recap", report["pattern"]["id"])

    def test_build_html_pages_include_reference_and_local_reproduction(self) -> None:
        case = default_reference_cases(Path("/repo"))[0]
        report = build_case_report(case, repo_root=Path("/repo"))

        analysis_html = build_reference_analysis_html(case, report)
        benchmark_html = build_benchmark_html([report])

        self.assertIn("Movie Recaps", analysis_html)
        self.assertIn("reference_analysis.html", benchmark_html)
        self.assertIn("movie_recap_drama", benchmark_html)
        self.assertIn("https://www.youtube.com/embed/", benchmark_html)
        self.assertIn("videos/movie_recap_drama.mp4", benchmark_html)


if __name__ == "__main__":
    unittest.main()
