#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

exec "${LOGICCUT_VENV}/bin/python" "${LOGICCUT_ROOT}/scripts/smoke_ai_shorts_local.py"
