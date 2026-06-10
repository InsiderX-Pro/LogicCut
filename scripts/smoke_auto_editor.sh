#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

if [[ ! -x "${LOGICCUT_VENV}/bin/auto-editor" ]]; then
  echo "auto-editor is not installed. Run ./scripts/setup_auto_editor_python.sh first." >&2
  exit 1
fi

SOURCE="${SOURCE:-${LOGICCUT_OUTPUT_DIR}/ai-shorts/smoke/source.mp4}"
if [[ ! -f "${SOURCE}" ]]; then
  "${LOGICCUT_ROOT}/scripts/smoke_ai_shorts_local.sh" >/dev/null
fi

OUT_DIR="${LOGICCUT_OUTPUT_DIR}/auto-editor"
mkdir -p "${OUT_DIR}"
OUT_FILE="${OUT_DIR}/source_auto_edited.mp4"

"${LOGICCUT_VENV}/bin/auto-editor" "${SOURCE}" \
  --no-open \
  --progress none \
  -o "${OUT_FILE}"

"${LOGICCUT_VENV}/bin/python" - <<'PY' "${OUT_FILE}"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists() or path.stat().st_size == 0:
    raise SystemExit(f"auto-editor produced no output: {path}")
print(json.dumps({"path": str(path), "bytes": path.stat().st_size}, ensure_ascii=False, indent=2))
PY
