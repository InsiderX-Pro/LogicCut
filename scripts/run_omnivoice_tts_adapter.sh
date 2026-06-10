#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

exec "${LOGICCUT_VENV}/bin/python" -m logiccut.omnivoice_tts_adapter \
  --host "${LOGICCUT_OMNIVOICE_TTS_HOST:-127.0.0.1}" \
  --port "${LOGICCUT_OMNIVOICE_TTS_PORT:-8391}" \
  --omnivoice-url "${LOGICCUT_OMNIVOICE_API_URL:-http://127.0.0.1:3900}" \
  --model "${LOGICCUT_OMNIVOICE_MODEL:-omnivoice}" \
  --voice "${LOGICCUT_OMNIVOICE_VOICE:-default}"
