#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

VTR_ROOT="${LOGICCUT_VIDEO_TRANSLATE_REFINE_ROOT:-${LOGICCUT_ROOT}/third_party/video-translate-refine}"
VTR_PYTHON="${LOGICCUT_VIDEO_TRANSLATE_REFINE_PYTHON:-${LOGICCUT_VENV}/bin/python}"

export PYTHONPATH="${VTR_ROOT}/src:${PYTHONPATH:-}"

exec "${VTR_PYTHON}" -m video_translate.entrypoints.fish_tts_adapter_server \
  --fish-speech-url "${LOGICCUT_FISH_SPEECH_URL:-http://127.0.0.1:8320}" \
  --listen-host "${LOGICCUT_FISH_TTS_ADAPTER_HOST:-127.0.0.1}" \
  --listen-port "${LOGICCUT_FISH_TTS_ADAPTER_PORT:-8392}" \
  --timeout-s "${LOGICCUT_FISH_TTS_TIMEOUT_S:-300}"
