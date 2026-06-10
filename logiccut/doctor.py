from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


def run_doctor(*, profile: str = "standard", repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[1]
    checks: dict[str, dict[str, Any]] = {
        "python": _python_check(),
        "git": _command_check("git", ["git", "--version"]),
        "ffmpeg": _command_check("ffmpeg", ["ffmpeg", "-version"]),
        "ffprobe": _command_check("ffprobe", ["ffprobe", "-version"]),
        "yt-dlp": _python_module_or_command_check("yt_dlp", "yt-dlp"),
        "node": _command_check("node", ["node", "--version"]),
        "npm": _command_check("npm", ["npm", "--version"]),
        "playwright": _playwright_check(repo_root=root),
        "logiccut_package": {"status": "ok", "path": str(root / "logiccut")},
    }
    if profile in {"standard", "creator", "full"}:
        checks["opencc"] = _python_module_check("opencc")
    if profile == "full":
        checks["torch"] = _python_module_check("torch")
        checks["pyannote.audio"] = _python_module_check("pyannote.audio")
        checks["HF_TOKEN"] = _env_check("HF_TOKEN")

    missing = [name for name, item in checks.items() if item["status"] == "missing"]
    failed = [name for name, item in checks.items() if item["status"] == "failed"]
    return {
        "version": "0.3",
        "profile": profile,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "summary": {
            "ok": not missing and not failed,
            "missing": missing,
            "failed": failed,
        },
        "checks": checks,
        "next_steps": _next_steps(profile, missing, failed),
    }


def _python_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "path": shutil.which("python3") or shutil.which("python") or "",
        "version": platform.python_version(),
    }


def _command_check(name: str, version_cmd: list[str]) -> dict[str, Any]:
    path = shutil.which(name)
    if not path:
        return {"status": "missing", "message": f"{name} not found on PATH"}
    try:
        proc = subprocess.run(version_cmd, text=True, capture_output=True, timeout=20)
    except Exception as exc:
        return {"status": "failed", "path": path, "message": str(exc)}
    output = (proc.stdout or proc.stderr).strip().splitlines()
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "path": path,
        "version": output[0] if output else "",
        "returncode": proc.returncode,
    }


def _python_module_check(module: str) -> dict[str, Any]:
    proc = subprocess.run(
        [
            shutil.which("python3") or "python",
            "-c",
            f"import {module}; print('ok')",
        ],
        text=True,
        capture_output=True,
        timeout=20,
    )
    if proc.returncode == 0:
        return {"status": "ok", "module": module}
    return {"status": "missing", "module": module, "message": (proc.stderr or proc.stdout).strip()[-500:]}


def _python_module_or_command_check(module: str, command: str) -> dict[str, Any]:
    module_check = _python_module_check(module)
    if module_check["status"] == "ok":
        return module_check
    command_check = _command_check(command, [command, "--version"])
    if command_check["status"] == "ok":
        return command_check
    return {"status": "missing", "module": module, "command": command, "message": "module and command are unavailable"}


def _playwright_check(*, repo_root: Path) -> dict[str, Any]:
    python_check = _python_module_check("playwright")
    if python_check["status"] == "ok":
        return {**python_check, "runtime": "python"}
    if shutil.which("node"):
        proc = subprocess.run(
            ["node", "-e", "require('playwright'); console.log('ok')"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=20,
        )
        if proc.returncode == 0:
            return {"status": "ok", "module": "playwright", "runtime": "node"}
    return {
        "status": "missing",
        "module": "playwright",
        "message": "Neither Python nor Node Playwright is available.",
    }


def _env_check(name: str) -> dict[str, Any]:
    value = os.environ.get(name, "")
    if value:
        return {"status": "ok", "env": name, "set": True}
    return {"status": "missing", "env": name, "message": f"{name} is not set"}


def _next_steps(profile: str, missing: list[str], failed: list[str]) -> list[str]:
    if not missing and not failed:
        return ["Run `logiccut capabilities` and then `logiccut plan` for a video task."]
    steps = ["Run the installer for the requested profile, then re-run `logiccut doctor`."]
    if "ffmpeg" in missing or "ffprobe" in missing:
        steps.append("Install FFmpeg and ensure both `ffmpeg` and `ffprobe` are on PATH.")
    if "yt-dlp" in missing:
        steps.append("Install yt-dlp with `python -m pip install yt-dlp` or through the setup script.")
    if "playwright" in missing and profile in {"lite", "standard", "creator", "full"}:
        steps.append("Install Playwright browsers with `python -m playwright install chromium`.")
    return steps
