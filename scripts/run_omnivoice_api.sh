#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

if [[ ! -x "${LOGICCUT_VENV}/bin/uvicorn" ]]; then
  echo "uvicorn not found in ${LOGICCUT_VENV}. Run ./scripts/setup_unified_env.sh first." >&2
  exit 1
fi

export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-3901}"
export OMNIVOICE_PORT="${OMNIVOICE_PORT:-${PORT}}"
export OMNIVOICE_UI_PORT="${OMNIVOICE_UI_PORT:-3902}"
export OMNIVOICE_SHARE_PORT="${OMNIVOICE_SHARE_PORT:-$((PORT + 1))}"
export PYTHONPATH="${LOGICCUT_ROOT}/third_party/OmniVoice-Studio/backend:${LOGICCUT_ROOT}/third_party/OmniVoice-Studio:${PYTHONPATH:-}"

exec "${LOGICCUT_VENV}/bin/uvicorn" main:app \
  --app-dir "${LOGICCUT_ROOT}/third_party/OmniVoice-Studio/backend" \
  --host "${HOST}" \
  --port "${PORT}"
