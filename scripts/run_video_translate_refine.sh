#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

INPUT="${1:?usage: scripts/run_video_translate_refine.sh INPUT_VIDEO [OUTPUT_DIR]}"
OUTPUT_DIR="${2:-${LOGICCUT_OUTPUT_DIR}/video-translate-refine-run}"

exec "${ROOT_DIR}/scripts/logiccut.sh" translate-video \
  --input "${INPUT}" \
  --output-dir "${OUTPUT_DIR}" \
  --clip "${LOGICCUT_VIDEO_TRANSLATION_CLIP_SECONDS:-60}" \
  --profile "${LOGICCUT_VIDEO_TRANSLATE_PROFILE:-v3}" \
  --src-lang "${LOGICCUT_SOURCE_LANGUAGE:-en}" \
  --tgt-lang "${LOGICCUT_TARGET_LANGUAGE:-中文}" \
  --translate-backend "${LOGICCUT_TRANSLATE_BACKEND:-qwen35_plus}" \
  --speaker-backend "${LOGICCUT_SPEAKER_BACKEND:-pyannote_local}" \
  --asr-text-refine-backend "${LOGICCUT_ASR_TEXT_REFINE_BACKEND:-qwen_omni}" \
  --tts-engine "${LOGICCUT_TTS_ENGINE:-rgad-tts}"
