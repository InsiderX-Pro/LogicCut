from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from logiccut.cli import main


class V03UserWorkflowTest(unittest.TestCase):
    def test_capabilities_lists_codex_facing_features(self) -> None:
        with patch("builtins.print") as print_mock:
            exit_code = main(["capabilities"])

        self.assertEqual(0, exit_code)
        payload = json.loads(print_mock.call_args.args[0])
        feature_ids = {item["id"] for item in payload["features"]}
        self.assertIn("download", feature_ids)
        self.assertIn("translate-video", feature_ids)
        self.assertIn("theme-opener", feature_ids)
        self.assertIn("comments", feature_ids)
        self.assertIn("merge", feature_ids)
        self.assertEqual("0.3", payload["version"])
        self.assertIn("codex", payload["usage_modes"])

    def test_guide_returns_task_specific_codex_steps(self) -> None:
        with patch("builtins.print") as print_mock:
            exit_code = main(["guide", "--task", "remix"])

        self.assertEqual(0, exit_code)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual("remix", payload["task"])
        self.assertGreaterEqual(len(payload["steps"]), 4)
        self.assertTrue(any("merge" in " ".join(step["commands"]) for step in payload["steps"]))
        self.assertTrue(any("Codex" in note for note in payload["notes"]))

    def test_doctor_reports_required_tools_without_failing_by_default(self) -> None:
        with patch("builtins.print") as print_mock:
            exit_code = main(["doctor", "--json"])

        self.assertEqual(0, exit_code)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertIn("checks", payload)
        self.assertIn("python", payload["checks"])
        self.assertIn("ffmpeg", payload["checks"])
        self.assertIn("summary", payload)

    def test_merge_command_calls_reencode_concat_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.mp4"
            second = root / "second.mp4"
            output = root / "final.mp4"
            first.write_bytes(b"one")
            second.write_bytes(b"two")

            with (
                patch("logiccut.merge.concat_videos_reencode", return_value=output) as concat_mock,
                patch("logiccut.merge.ffprobe_duration", side_effect=[1.25, 2.75, 4.0]),
                patch("builtins.print") as print_mock,
            ):
                exit_code = main(
                    [
                        "merge",
                        "--inputs",
                        str(first),
                        str(second),
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(0, exit_code)
            concat_mock.assert_called_once()
            payload = json.loads(print_mock.call_args.args[0])
            self.assertEqual(str(output), payload["output_video"])
            self.assertEqual(2, len(payload["inputs"]))
            self.assertTrue(Path(payload["manifest"]).exists())

    def test_plan_creates_codex_reviewable_workflow_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "case"

            with patch("builtins.print") as print_mock:
                exit_code = main(
                    [
                        "plan",
                        "--url",
                        "https://www.youtube.com/watch?v=abc123",
                        "--project-dir",
                        str(output_dir),
                        "--tasks",
                        "download,comments,comment-freeze,merge",
                        "--target-lang",
                        "中文",
                        "--theme",
                        "安全感",
                        "--comment-duration",
                        "20",
                    ]
                )

            self.assertEqual(0, exit_code)
            payload = json.loads(print_mock.call_args.args[0])
            plan_path = Path(payload["plan"])
            self.assertTrue(plan_path.exists())
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual("0.3", plan["version"])
            self.assertEqual("安全感", plan["options"]["theme"])
            self.assertEqual(["download", "comments", "comment-freeze", "merge"], plan["tasks"])
            self.assertTrue(any(step["command"] == "comments" for step in plan["steps"]))

    def test_plan_supports_logiccut_local_translation_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "case"

            with patch("builtins.print") as print_mock:
                exit_code = main(
                    [
                        "plan",
                        "--input",
                        str(Path(tmp) / "source.mp4"),
                        "--project-dir",
                        str(output_dir),
                        "--tasks",
                        "translate-local",
                        "--target-lang",
                        "中文",
                    ]
                )

            self.assertEqual(0, exit_code)
            payload = json.loads(print_mock.call_args.args[0])
            plan = json.loads(Path(payload["plan"]).read_text(encoding="utf-8"))
            step = plan["steps"][0]
            self.assertEqual("translate-local", step["id"])
            self.assertEqual("translate-video", step["command"])
            self.assertEqual("logiccut-local", step["args"]["backend"])
            self.assertTrue(step["args"]["burn_subtitles"])

    def test_execute_dry_run_prints_plan_steps_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "logiccut_plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "version": "0.3",
                        "project_dir": str(root / "case"),
                        "tasks": ["download", "merge"],
                        "steps": [
                            {"id": "download", "command": "download", "args": {"url": "https://example.com/v", "output_dir": "download"}},
                            {"id": "merge", "command": "merge", "args": {"inputs": [], "output": "final.mp4"}},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("builtins.print") as print_mock:
                exit_code = main(["execute", "--plan", str(plan_path), "--dry-run"])

        self.assertEqual(0, exit_code)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertTrue(payload["dry_run"])
        self.assertEqual(["download", "merge"], [step["command"] for step in payload["steps"]])


if __name__ == "__main__":
    unittest.main()
