from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logiccut.manifest import create_manifest, load_manifest, save_manifest


class ManifestContractTest(unittest.TestCase):
    def test_create_manifest_contains_core_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            input_path = Path(tmp) / "source.mp4"
            input_path.write_bytes(b"fake")

            manifest = create_manifest(project_dir, input_path, title="Demo")

            self.assertEqual(manifest["schema_version"], "0.2")
            self.assertEqual(manifest["title"], "Demo")
            self.assertEqual(manifest["input"]["path"], "../source.mp4")
            self.assertEqual(manifest["style"]["subtitle"], "subcap-ass-captioner")
            for key in [
                "transcripts",
                "speakers",
                "tracks",
                "clips",
                "timeline",
                "style",
                "renders",
                "recipes",
                "logs",
            ]:
                self.assertIn(key, manifest)

    def test_save_and_load_manifest_round_trips_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            input_path = Path(tmp) / "source.mp4"
            input_path.write_bytes(b"fake")

            manifest = create_manifest(project_dir, input_path)
            manifest["clips"].append({"id": "clip_01", "path": "clips/clip_01.mp4"})
            save_manifest(project_dir, manifest)

            loaded = load_manifest(project_dir)
            self.assertEqual(loaded["clips"][0]["id"], "clip_01")
            self.assertEqual(loaded["input"]["path"], "../source.mp4")


if __name__ == "__main__":
    unittest.main()
