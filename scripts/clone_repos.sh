#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${ROOT_DIR}/configs/repos.json"

python3 - <<'PY' "${ROOT_DIR}" "${CONFIG}"
import json
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
config = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

for item in config["repos"]:
    target = root / item["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    repo = item["repo"]
    if (target / ".git").exists():
        print(f"[update] {item['name']} -> {target}")
        subprocess.run(["git", "-C", str(target), "pull", "--ff-only"], check=True)
    else:
        print(f"[clone] {item['name']} -> {target}")
        subprocess.run(["git", "clone", "--depth", "1", repo, str(target)], check=True)

    sha = subprocess.check_output(["git", "-C", str(target), "rev-parse", "HEAD"], text=True).strip()
    branch = subprocess.check_output(["git", "-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    print(f"[version] {item['name']} {branch} {sha}")
PY
