#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

SMOKE_DIR="${LOGICCUT_OUTPUT_DIR}/logiccut-smoke"
SOURCE="${SMOKE_DIR}/source.mp4"
PROJECT_DIR="${SMOKE_DIR}/project"
LOG_FILE="${LOGICCUT_LOG_DIR}/logiccut-cli-smoke.log"
mkdir -p "${SMOKE_DIR}" "${LOGICCUT_LOG_DIR}"
: > "${LOG_FILE}"

{
  echo "==> generate sample"
  "${LOGICCUT_ROOT}/scripts/logiccut.sh" sample --output "${SOURCE}" --duration 5

  echo "==> run all recipes"
  "${LOGICCUT_ROOT}/scripts/logiccut.sh" run \
    --input "${SOURCE}" \
    --project-dir "${PROJECT_DIR}" \
    --recipe all \
    --chapters 2 \
    --title "LogicCut smoke"

  echo "==> verify outputs"
  "${LOGICCUT_VENV}/bin/python" - <<'PY' "${PROJECT_DIR}"
import json
import sys
from pathlib import Path

project = Path(sys.argv[1])
manifest = json.loads((project / "project.json").read_text(encoding="utf-8"))
required_renders = {"translate_remix", "highlight_first"}
render_ids = {item["id"] for item in manifest["renders"]}
missing = sorted(required_renders - render_ids)
if missing:
    raise SystemExit(f"missing renders: {missing}")
for item in manifest["renders"]:
    path = project / item["path"]
    if not path.exists() or path.stat().st_size == 0:
        raise SystemExit(f"bad render: {item}")
chapters = [item for item in manifest["clips"] if item["id"].startswith("chapter_")]
if len(chapters) < 2:
    raise SystemExit(f"expected at least 2 chapter clips, got {len(chapters)}")
for item in chapters:
    path = project / item["path"]
    if not path.exists() or path.stat().st_size == 0:
        raise SystemExit(f"bad chapter clip: {item}")
print(json.dumps({
    "project": str(project),
    "renders": sorted(render_ids),
    "chapter_clips": len(chapters),
    "manifest": str(project / "project.json"),
}, ensure_ascii=False, indent=2))
PY
} 2>&1 | tee "${LOG_FILE}"
