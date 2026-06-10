#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

if [[ ! -x "${LOGICCUT_VENV}/bin/python" ]]; then
  echo "Unified Python env not found. Run ./scripts/setup_unified_env.sh first." >&2
  exit 1
fi

# auto-editor's current Nim build is not portable on Ubuntu 22.04 without a
# matching FFmpeg 6/7 header toolchain. The last Python-line release works for
# our rough-cut adapter, but its dependency metadata names PyAV as `pyav`; the
# actual PyPI package is `av`, so install the runtime deps explicitly first.
uv pip install --python "${LOGICCUT_VENV}/bin/python" \
  "av==12.3.0" \
  "ae-ffmpeg==1.2.0" \
  "pillow==10.1.0"

uv pip install --python "${LOGICCUT_VENV}/bin/python" \
  "${LOGICCUT_ROOT}/compat/pyav_alias"

uv pip install --python "${LOGICCUT_VENV}/bin/python" --no-deps \
  "auto-editor==24.31.1"

"${LOGICCUT_VENV}/bin/auto-editor" --version
