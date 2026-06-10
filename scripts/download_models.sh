#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

if [[ ! -x "${LOGICCUT_VENV}/bin/python" ]]; then
  echo "Unified Python env not found. Run ./scripts/setup_unified_env.sh first." >&2
  exit 1
fi

exec "${LOGICCUT_VENV}/bin/python" "${LOGICCUT_ROOT}/scripts/download_models.py" "$@"
