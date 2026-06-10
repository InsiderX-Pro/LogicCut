#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

REPORT_FILE="${LOGICCUT_LOG_DIR}/smoke-all-report.jsonl"
: > "${REPORT_FILE}"

run_step() {
  local name="$1"
  shift
  echo
  echo "==> ${name}"
  local started ended
  started="$(date +%s)"
  "$@"
  ended="$(date +%s)"
  "${LOGICCUT_VENV}/bin/python" - <<'PY' "${REPORT_FILE}" "${name}" "${started}" "${ended}"
import json
import sys

path, name, started, ended = sys.argv[1:5]
with open(path, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({
        "step": name,
        "status": "ok",
        "seconds": int(ended) - int(started),
    }, ensure_ascii=False) + "\n")
PY
}

model_args=("--local-files-only")
if [[ -n "${HF_TOKEN:-}" ]]; then
  model_args=("--include-gated" "--local-files-only")
fi

run_step "model-cache" "${LOGICCUT_ROOT}/scripts/download_models.sh" "${model_args[@]}"
run_step "doctor" "${LOGICCUT_ROOT}/scripts/doctor.sh"

if [[ -n "${GEMINI_CREDENTIALS_JSON:-}" ]]; then
  run_step "gemini-vertex" "${LOGICCUT_ROOT}/scripts/smoke_gemini_vertex.sh"
else
  echo "==> gemini-vertex skipped: GEMINI_CREDENTIALS_JSON is not set"
fi

run_step "omnivoice-api" "${LOGICCUT_ROOT}/scripts/smoke_omnivoice_api.sh"
run_step "ai-shorts-local" "${LOGICCUT_ROOT}/scripts/smoke_ai_shorts_local.sh"
run_step "auto-editor" "${LOGICCUT_ROOT}/scripts/smoke_auto_editor.sh"
run_step "logiccut-cli" "${LOGICCUT_ROOT}/scripts/smoke_logiccut_cli.sh"
run_step "openreel-ui" "${LOGICCUT_ROOT}/scripts/smoke_openreel.sh"

if [[ -n "${HF_TOKEN:-}" ]]; then
  run_step "pyannote" "${LOGICCUT_ROOT}/scripts/smoke_pyannote.sh"
else
  echo "==> pyannote skipped: HF_TOKEN is not set"
fi

echo
echo "All LogicCut smoke checks passed. Report: ${REPORT_FILE}"
