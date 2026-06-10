from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from logiccut.omnivoice_tts_adapter import OmniVoiceTtsAdapter


class OmniVoiceTtsAdapterTest(unittest.TestCase):
    def test_synthesize_calls_openai_speech_endpoint_and_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "speech.wav"
            poster = Mock(return_value=b"RIFFwav")
            adapter = OmniVoiceTtsAdapter(base_url="http://127.0.0.1:3900", post_json=poster)

            result = adapter.synthesize_from_payload(
                {
                    "text": "你好，LogicCut",
                    "output_path": str(output),
                    "backend_options": {"model": "omnivoice", "voice": "default", "speed": 1.1},
                }
            )

            self.assertTrue(result["success"])
            self.assertEqual("omnivoice", result["backend"])
            self.assertEqual(b"RIFFwav", output.read_bytes())
            poster.assert_called_once_with(
                "http://127.0.0.1:3900/v1/audio/speech",
                {
                    "model": "omnivoice",
                    "input": "你好，LogicCut",
                    "voice": "default",
                    "response_format": "wav",
                    "speed": 1.1,
                },
                timeout_s=300,
            )


if __name__ == "__main__":
    unittest.main()
