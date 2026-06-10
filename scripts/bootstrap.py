#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path


LITE_PACKAGES = [
    "yt-dlp",
    "requests",
    "pillow",
    "opencc-python-reimplemented",
    "playwright",
]
CREATOR_PACKAGES = LITE_PACKAGES + [
    "beautifulsoup4",
]
DEFAULT_PROFILE = "standard"
VALID_PROFILES = ["lite", "standard", "creator", "full"]


def packages_for_profile(profile: str) -> list[str]:
    if profile in {"standard", "creator", "full"}:
        return CREATOR_PACKAGES
    return LITE_PACKAGES


def main() -> int:
    parser = argparse.ArgumentParser(description="Install LogicCut local dependencies")
    parser.add_argument("--profile", choices=VALID_PROFILES, default=DEFAULT_PROFILE)
    parser.add_argument("--venv", type=Path, default=Path(".venv"))
    parser.add_argument("--skip-playwright", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    venv_dir = (root / args.venv).resolve() if not args.venv.is_absolute() else args.venv
    _ensure_venv(venv_dir)
    python = _venv_python(venv_dir)
    installer = _installer(python)
    _install(installer, ["--upgrade", "pip", "wheel"])
    packages = packages_for_profile(args.profile)
    _install(installer, packages)
    _write_command_shims(root, venv_dir)
    if not args.skip_playwright:
        _run([str(python), "-m", "playwright", "install", "chromium"])
    if args.profile == "full":
        print("[logiccut] full profile selected; run scripts/setup_unified_env.sh on Linux/WSL2 for model-heavy services.")
    print(f"[logiccut] installed {args.profile} profile into {venv_dir}")
    print(f"[logiccut] activate: {_activate_hint(venv_dir)}")
    return 0


def _ensure_venv(path: Path) -> None:
    if (path / _python_relpath()).exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    venv.EnvBuilder(with_pip=True).create(path)


def _venv_python(path: Path) -> Path:
    return path / _python_relpath()


def _python_relpath() -> Path:
    if platform.system().lower().startswith("win"):
        return Path("Scripts") / "python.exe"
    return Path("bin") / "python"


def _activate_hint(path: Path) -> str:
    if platform.system().lower().startswith("win"):
        return str(path / "Scripts" / "Activate.ps1")
    return f"source {path / 'bin' / 'activate'}"


def _write_command_shims(root: Path, venv_dir: Path) -> None:
    if platform.system().lower().startswith("win"):
        scripts = venv_dir / "Scripts"
        shim = scripts / "logiccut.cmd"
        shim.write_text(
            f'@echo off\r\nset PYTHONPATH={root};%PYTHONPATH%\r\n"{scripts / "python.exe"}" -m logiccut.cli %*\r\n',
            encoding="utf-8",
        )
        ps1 = scripts / "logiccut.ps1"
        ps1.write_text(
            f'$env:PYTHONPATH="{root};$env:PYTHONPATH"\n& "{scripts / "python.exe"}" -m logiccut.cli @args\n',
            encoding="utf-8",
        )
        return
    bin_dir = venv_dir / "bin"
    shim = bin_dir / "logiccut"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'export PYTHONPATH="{root}:${{PYTHONPATH:-}}"\n'
        f'exec "{bin_dir / "python"}" -m logiccut.cli "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)


def _installer(python: Path) -> list[str]:
    if _has_pip(python):
        return [str(python), "-m", "pip", "install"]
    ensurepip = subprocess.run([str(python), "-m", "ensurepip", "--upgrade"], text=True, capture_output=True)
    if ensurepip.returncode == 0 and _has_pip(python):
        return [str(python), "-m", "pip", "install"]
    uv = shutil.which("uv")
    if uv:
        return [uv, "pip", "install", "--python", str(python)]
    raise RuntimeError("pip is unavailable in the virtualenv and uv was not found")


def _has_pip(python: Path) -> bool:
    proc = subprocess.run([str(python), "-m", "pip", "--version"], text=True, capture_output=True)
    return proc.returncode == 0


def _install(installer: list[str], packages: list[str]) -> None:
    _run([*installer, *packages])


def _run(cmd: list[str]) -> None:
    env = {**os.environ, "PYTHONNOUSERSITE": "1"}
    subprocess.run(cmd, check=True, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
