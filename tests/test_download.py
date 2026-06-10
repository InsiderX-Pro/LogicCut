from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from logiccut.download import build_ytdlp_command, download_video


class DownloadTest(unittest.TestCase):
    def test_build_ytdlp_command_uses_safe_mp4_defaults(self) -> None:
        output_dir = Path("/tmp/logiccut-download")
        cmd = build_ytdlp_command(
            "https://www.youtube.com/watch?v=abc123&t=2s",
            output_dir,
            prefix="demo",
        )

        self.assertEqual("yt-dlp", cmd[0])
        self.assertIn("--merge-output-format", cmd)
        self.assertIn("mp4", cmd)
        self.assertIn("--restrict-filenames", cmd)
        self.assertIn("--print", cmd)
        self.assertIn("after_move:filepath", cmd)
        self.assertEqual("https://www.youtube.com/watch?v=abc123&t=2s", cmd[-1])
        self.assertTrue(any("demo.%(ext)s" in item for item in cmd))

    def test_build_ytdlp_command_adds_bilibili_browser_headers(self) -> None:
        cmd = build_ytdlp_command(
            "https://www.bilibili.com/video/BV1gTmCBsExD/",
            Path("/tmp/logiccut-download"),
            prefix="bili",
        )

        self.assertIn("--add-header", cmd)
        self.assertIn("Referer:https://www.bilibili.com", cmd)
        self.assertTrue(any("User-Agent:Mozilla/5.0" in item for item in cmd))

    def test_download_video_returns_metadata_from_ytdlp_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "downloaded.mp4"
            output.write_bytes(b"video")
            fake_stdout = "\n".join(
                [
                    json.dumps(
                        {
                            "id": "abc123",
                            "title": "Demo",
                            "webpage_url": "https://www.youtube.com/watch?v=abc123",
                            "duration": 12,
                            "extractor_key": "Youtube",
                        }
                    ),
                    str(output),
                ]
            )

            with patch("logiccut.download.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = fake_stdout
                run.return_value.stderr = ""

                result = download_video(
                    "https://www.youtube.com/watch?v=abc123",
                    root,
                    prefix="demo",
                )

            self.assertEqual(output, result.path)
            self.assertEqual("abc123", result.metadata["id"])
            self.assertEqual("Youtube", result.metadata["extractor_key"])
            self.assertGreater(result.bytes, 0)
            self.assertTrue((root / "download.json").exists())


if __name__ == "__main__":
    unittest.main()
