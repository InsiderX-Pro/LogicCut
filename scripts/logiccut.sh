#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

export PYTHONPATH="${LOGICCUT_ROOT}:${PYTHONPATH:-}"
exec "${LOGICCUT_VENV}/bin/python" -m logiccut.cli "$@"
