#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

PORT="${PORT:-3901}"
BASE_URL="${BASE_URL:-http://127.0.0.1:${PORT}}"
LOG_FILE="${LOGICCUT_LOG_DIR}/omnivoice-api-smoke.log"
STARTED_PID=""

cleanup() {
  if [[ -n "${STARTED_PID}" ]]; then
    kill "${STARTED_PID}" >/dev/null 2>&1 || true
    wait "${STARTED_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if ! curl -fsS "${BASE_URL}/system/info" >/dev/null 2>&1; then
  PORT="${PORT}" "${LOGICCUT_ROOT}/scripts/run_omnivoice_api.sh" >"${LOG_FILE}" 2>&1 &
  STARTED_PID="$!"
fi

for _ in $(seq 1 90); do
  if curl -fsS "${BASE_URL}/system/info" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

"${LOGICCUT_VENV}/bin/python" - <<'PY' "${BASE_URL}" "${LOGICCUT_ROOT}"
import json
import sys
import time
import urllib.request
from pathlib import Path

base_url = sys.argv[1]
root = Path(sys.argv[2])
expected_data_dir = str(root / "output" / "omnivoice-data")

def get(path):
    with urllib.request.urlopen(base_url + path, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

info = get("/system/info")
if info.get("data_dir") != expected_data_dir:
    raise SystemExit(f"wrong OmniVoice data_dir: {info.get('data_dir')} != {expected_data_dir}")

models = get("/models")["models"]
required = ["k2-fsa/OmniVoice", "Systran/faster-whisper-large-v3", "Systran/faster-whisper-base"]
missing = []
for repo in required:
    item = next((m for m in models if m["repo_id"] == repo), None)
    if not item or not item.get("installed"):
        missing.append(repo)
if missing:
    raise SystemExit(f"missing OmniVoice model cache: {', '.join(missing)}")

deadline = time.time() + 180
status = {}
while time.time() < deadline:
    status = get("/model/status")
    if status.get("status") == "ready":
        break
    if status.get("status") == "error":
        raise SystemExit(f"model status error: {status}")
    time.sleep(3)
else:
    raise SystemExit(f"model did not become ready: {status}")

print(json.dumps({
    "base_url": base_url,
    "data_dir": info.get("data_dir"),
    "device": info.get("device"),
    "model_status": status.get("status"),
    "checked_models": required,
}, ensure_ascii=False, indent=2))
PY
