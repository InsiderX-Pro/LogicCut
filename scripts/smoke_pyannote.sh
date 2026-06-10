#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

VTR_ROOT="${LOGICCUT_VIDEO_TRANSLATE_REFINE_ROOT:-${LOGICCUT_ROOT}/third_party/video-translate-refine}"
VTR_PYTHON="${LOGICCUT_VIDEO_TRANSLATE_REFINE_PYTHON:-${LOGICCUT_VENV}/bin/python}"

PYTHONPATH="${VTR_ROOT}/src:${PYTHONPATH:-}" "${VTR_PYTHON}" - <<'PY'
import json

from video_translate.core.pyannote_speaker_diarization import _load_pyannote_pipeline

pipeline = _load_pyannote_pipeline()
print(json.dumps({
    "pyannote_pipeline_loaded": pipeline is not None,
    "class": pipeline.__class__.__name__,
}, ensure_ascii=False, indent=2))
PY
