#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

LOG_FILE="${LOGICCUT_LOG_DIR}/openreel-smoke.log"
PORT="${PORT:-5173}"

set +e
PORT="${PORT}" timeout "${OPENREEL_SMOKE_TIMEOUT_SECONDS:-8}"s \
  "${LOGICCUT_ROOT}/scripts/run_openreel_dev.sh" >"${LOG_FILE}" 2>&1
code=$?
set -e

if [[ "${code}" != "124" && "${code}" != "0" ]]; then
  cat "${LOG_FILE}" >&2
  exit "${code}"
fi

if ! grep -Eq "Local:|ready in|http://127.0.0.1:${PORT}" "${LOG_FILE}"; then
  cat "${LOG_FILE}" >&2
  echo "OpenReel did not print a Vite ready line." >&2
  exit 1
fi

echo "OpenReel Vite smoke passed. Log: ${LOG_FILE}"
