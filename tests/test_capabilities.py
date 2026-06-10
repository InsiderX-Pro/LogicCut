from __future__ import annotations

import unittest

from logiccut.capabilities import build_capabilities


class CapabilitiesTest(unittest.TestCase):
    def test_capabilities_expose_local_first_translation_stack(self) -> None:
        payload = build_capabilities()

        self.assertEqual("local-first", payload["translation_default"])
        stack = " ".join(str(item) for item in payload["local_model_stack"])
        self.assertIn("faster-whisper", stack)
        self.assertIn("pyannote", stack)
        self.assertIn("Codex-file", stack)

    def test_capabilities_expose_supported_tts_backends(self) -> None:
        payload = build_capabilities()
        engines = " ".join(item["engine"] for item in payload["tts_backends"])

        self.assertIn("rgad-tts", engines)
        self.assertIn("fishaudio", engines)
        self.assertIn("fish-speech-s2", engines)
        self.assertIn("indextts2", engines)
        self.assertIn("omnivoice", engines)

    def test_capabilities_expose_task_based_install_recommendations(self) -> None:
        payload = build_capabilities()

        self.assertEqual("standard", payload["install"]["default_profile"])
        recommendations = payload["install"]["task_recommendations"]
        chinese = recommendations["zh_translation_lightweight"]
        multilingual = recommendations["multilingual_dubbing"]

        self.assertEqual("rgad-tts", chinese["recommended_tts"])
        self.assertIn("rgad-crosslingual-tts", " ".join(chinese["sources"]))
        self.assertEqual("omnivoice", multilingual["recommended_tts"])
        self.assertIn("OmniVoice", multilingual["reason"])


if __name__ == "__main__":
    unittest.main()
