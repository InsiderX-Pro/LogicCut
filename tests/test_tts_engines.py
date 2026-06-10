from __future__ import annotations

import unittest

from logiccut.tts_engines import resolve_tts_engine


class TtsEngineTest(unittest.TestCase):
    def test_missing_engine_defaults_to_rgad_tts(self) -> None:
        preset = resolve_tts_engine(None)

        self.assertEqual("rgad-tts", preset.engine)
        self.assertEqual("8393", preset.tts_ports)

    def test_fishaudio_defaults_to_local_compatible_tts_port(self) -> None:
        preset = resolve_tts_engine("fishaudio")

        self.assertEqual("fishaudio", preset.engine)
        self.assertEqual("legacy_router", preset.tts_backend)
        self.assertEqual("8321", preset.tts_ports)
        self.assertIsNone(preset.fish_tts_adapter_url)

    def test_indextts2_defaults_to_existing_router_port(self) -> None:
        preset = resolve_tts_engine("indextts2")

        self.assertEqual("indextts2", preset.engine)
        self.assertEqual("legacy_router", preset.tts_backend)
        self.assertEqual("8304", preset.tts_ports)

    def test_omnivoice_defaults_to_logiccut_compat_adapter_port(self) -> None:
        preset = resolve_tts_engine("omnivoice")

        self.assertEqual("omnivoice", preset.engine)
        self.assertEqual("legacy_router", preset.tts_backend)
        self.assertEqual("8391", preset.tts_ports)

    def test_rgad_tts_defaults_to_lightweight_local_router_port(self) -> None:
        preset = resolve_tts_engine("rgad-crosslingual-tts")

        self.assertEqual("rgad-tts", preset.engine)
        self.assertEqual("legacy_router", preset.tts_backend)
        self.assertEqual("8393", preset.tts_ports)
        self.assertIn("lightweight", preset.note.lower())
        self.assertIn("cross-language", preset.note.lower())

    def test_fish_speech_adapter_mode_uses_adapter_url(self) -> None:
        preset = resolve_tts_engine("fish-speech-s2")

        self.assertEqual("fish-speech-s2", preset.engine)
        self.assertEqual("fish_speech_s2", preset.tts_backend)
        self.assertIsNone(preset.tts_ports)
        self.assertEqual("http://127.0.0.1:8392", preset.fish_tts_adapter_url)


if __name__ == "__main__":
    unittest.main()
