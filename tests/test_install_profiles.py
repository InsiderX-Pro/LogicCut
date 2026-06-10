from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("logiccut_bootstrap", ROOT / "scripts" / "bootstrap.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load scripts/bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallProfileTest(unittest.TestCase):
    def test_bootstrap_defaults_to_standard_profile(self) -> None:
        bootstrap = _load_bootstrap()

        self.assertEqual("standard", bootstrap.DEFAULT_PROFILE)
        self.assertIn("standard", bootstrap.VALID_PROFILES)
        self.assertEqual(bootstrap.CREATOR_PACKAGES, bootstrap.packages_for_profile("standard"))

    def test_shell_install_defaults_to_standard_profile(self) -> None:
        install_sh = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")

        self.assertIn('PROFILE="standard"', install_sh)

    def test_powershell_install_defaults_to_standard_profile(self) -> None:
        install_ps1 = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")

        self.assertIn('[ValidateSet("lite", "standard", "creator", "full")]', install_ps1)
        self.assertIn('[string]$Profile = "standard"', install_ps1)


if __name__ == "__main__":
    unittest.main()
