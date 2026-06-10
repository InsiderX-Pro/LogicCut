#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "${LOG_DIR}"

python3 - <<'PY' "${ROOT_DIR}"
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
config = json.loads((root / "configs/repos.json").read_text(encoding="utf-8"))

def command_status(name: str) -> dict:
    path = shutil.which(name)
    if path:
        return {"status": "ok", "path": path}
    for extra_dir in (Path.home() / ".nimble/bin",):
        candidate = extra_dir / name
        if candidate.exists():
            return {"status": "ok", "path": str(candidate), "path_note": "not on PATH"}
    return {"status": "missing", "message": f"Command not found: {name}"}

def glibc_status() -> dict:
    proc = run_capture(["ldd", "--version"])
    if proc["status"] != "ok":
        return proc
    first_line = (proc.get("stdout") or proc.get("stderr") or "").splitlines()[0:1]
    return {"status": "ok", "version": first_line[0] if first_line else "unknown"}

def pnpm_status() -> dict:
    path = shutil.which("pnpm")
    if path:
        return {"status": "ok", "path": path}
    try:
        proc = subprocess.run(["npm", "prefix", "-g"], text=True, capture_output=True, timeout=15)
        prefix = proc.stdout.strip()
        candidate = Path(prefix) / "lib/node_modules/pnpm/bin/pnpm.cjs"
        if candidate.exists():
            return {"status": "ok", "path": str(candidate), "runner": "node"}
    except Exception:
        pass
    return {"status": "missing", "message": "pnpm not found; run scripts/setup_node_tools.sh"}

def run_capture(args: list[str], cwd: Path | None = None) -> dict:
    try:
        proc = subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=60)
        return {
            "status": "ok" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip()[-2000:],
            "stderr": proc.stderr.strip()[-2000:],
        }
    except Exception as exc:
        return {"status": "failed", "message": str(exc)}

checks = {
    "system": {
        "python3": command_status("python3"),
        "git": command_status("git"),
        "ffmpeg": command_status("ffmpeg"),
        "node": command_status("node"),
        "npm": command_status("npm"),
        "uv": command_status("uv"),
        "bun": command_status("bun"),
        "pnpm": pnpm_status(),
        "nim": command_status("nim"),
        "glibc": glibc_status(),
    },
    "repos": {},
}

venv_python = root / ".venv/bin/python"
if venv_python.exists():
    checks["system"]["logiccut-venv"] = {"status": "ok", "path": str(venv_python)}
    checks["system"]["python-imports"] = run_capture([
        str(venv_python),
        "-c",
        (
            f"import sys; sys.path.insert(0, {str(root)!r}); "
            "import torch, torchaudio, faster_whisper, whisperx, funasr, "
            "pyannote.audio, demucs, cv2, yt_dlp, omnivoice, logiccut; "
            "print('imports ok; torch=' + torch.__version__)"
        ),
    ])
    checks["system"]["pip-check"] = run_capture([
        "uv", "pip", "check", "--python", str(venv_python)
    ])
    checks["system"]["model-cache"] = run_capture([
        str(venv_python),
        "-c",
        r'''
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from huggingface_hub import scan_cache_dir

root = Path(os.environ.get("LOGICCUT_ROOT", Path.cwd()))
config = json.loads((root / "configs" / "models.json").read_text(encoding="utf-8"))
cache_dir = os.environ.get("HF_HUB_CACHE") or str(root / "model_cache" / "huggingface" / "hub")
repos = {repo.repo_id: repo for repo in scan_cache_dir(cache_dir).repos}
missing = []
checked = []
for model in config["default"]:
    repo_id = model["repo_id"]
    if model.get("cache_type") == "audioseal":
        base = Path(os.environ.get("AUDIOSEAL_CACHE_DIR", str(root / "model_cache"))).expanduser() / "audioseal"
        ok = True
        for url in model.get("files", []):
            name = hashlib.sha1(urlparse(url).path.encode()).hexdigest()[:24]
            path = base / name
            ok = ok and path.exists() and path.stat().st_size > 0
        if not ok:
            missing.append(repo_id)
        checked.append(repo_id)
    else:
        repo = repos.get(repo_id)
        if repo is None or repo.size_on_disk <= 0:
            missing.append(repo_id)
        checked.append(repo_id)
print(json.dumps({"checked": checked, "missing": missing}, ensure_ascii=False))
raise SystemExit(1 if missing else 0)
        ''',
    ])
else:
    checks["system"]["logiccut-venv"] = {
        "status": "missing",
        "message": "Unified env not found; run scripts/setup_unified_env.sh",
    }

venv_auto_editor = root / ".venv/bin/auto-editor"
source_auto_editor = root / "third_party/auto-editor/auto-editor"
if source_auto_editor.exists():
    checks["system"]["auto-editor"] = run_capture([str(source_auto_editor), "--version"])
elif venv_auto_editor.exists():
    checks["system"]["auto-editor"] = run_capture([str(venv_auto_editor), "--version"])
else:
    status = command_status("auto-editor")
    if status["status"] == "missing":
        status["message"] = "auto-editor binary not found; run scripts/setup_auto_editor_source.sh or use a container with FFmpeg 6/7 headers"
    checks["system"]["auto-editor"] = status

for item in config["repos"]:
    repo_dir = root / item["path"]
    repo_check = {
        "path": str(repo_dir),
        "exists": repo_dir.exists(),
        "role": item["role"],
        "reason": item["reason"],
        "files": {},
        "git": {},
        "light_checks": {},
    }
    if repo_dir.exists():
        for file_group in ("python_files", "node_files", "source_files"):
            for file_name in item["doctor"].get(file_group, []):
                repo_check["files"][file_name] = (repo_dir / file_name).exists()
        repo_check["git"]["head"] = run_capture(["git", "rev-parse", "HEAD"], cwd=repo_dir)
        repo_check["git"]["branch"] = run_capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)

        if (repo_dir / "package.json").exists() and shutil.which("npm"):
            repo_check["light_checks"]["npm_pkg_name"] = run_capture(
                ["node", "-e", "const p=require('./package.json'); console.log(p.name || 'unnamed')"],
                cwd=repo_dir,
            )
        if (repo_dir / "pyproject.toml").exists():
            repo_check["light_checks"]["python_build_metadata"] = {"status": "ok", "file": "pyproject.toml"}
        if (repo_dir / "requirements.txt").exists():
            repo_check["light_checks"]["requirements"] = {"status": "ok", "file": "requirements.txt"}
        if (repo_dir / "README.md").exists():
            repo_check["light_checks"]["readme"] = {"status": "ok", "file": "README.md"}
    checks["repos"][item["name"]] = repo_check

missing = []
failed = []
for name, check in checks["system"].items():
    if check["status"] == "missing":
        missing.append(f"system:{name}")
    if check["status"] == "failed":
        failed.append(f"system:{name}")
for name, repo_check in checks["repos"].items():
    if not repo_check["exists"]:
        missing.append(f"repo:{name}")
    for file_name, exists in repo_check["files"].items():
        if not exists:
            missing.append(f"file:{name}:{file_name}")

result = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "summary": {
        "has_errors": bool(missing or failed),
        "missing": missing,
        "failed": failed,
    },
    "checks": checks,
}

json_path = root / "logs" / "doctor-report.json"
json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

md_lines = [
    "# LogicCut Doctor Report",
    "",
    f"Generated: {result['generated_at']}",
    "",
    "## Summary",
    "",
    f"- has_errors: `{str(result['summary']['has_errors']).lower()}`",
    f"- missing: `{', '.join(missing) if missing else 'none'}`",
    f"- failed: `{', '.join(failed) if failed else 'none'}`",
    "",
    "## System",
    "",
]
for name, check in checks["system"].items():
    md_lines.append(f"- {name}: `{check['status']}`")
md_lines.extend(["", "## Repositories", ""])
for name, repo_check in checks["repos"].items():
    md_lines.append(f"### {name}")
    md_lines.append(f"- role: `{repo_check['role']}`")
    md_lines.append(f"- exists: `{str(repo_check['exists']).lower()}`")
    if repo_check["git"].get("head", {}).get("stdout"):
        md_lines.append(f"- head: `{repo_check['git']['head']['stdout']}`")
    for file_name, exists in repo_check["files"].items():
        md_lines.append(f"- {file_name}: `{str(exists).lower()}`")
    md_lines.append("")

md_path = root / "logs" / "doctor-report.md"
md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
PY
