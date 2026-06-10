#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VIDEO_URL="${1:-${LOGICCUT_COMMENT_DEMO_URL:-}}"

if [[ -z "${VIDEO_URL}" ]]; then
  cat >&2 <<'USAGE'
Usage:
  ./scripts/run_v022_comment_video_demo.sh "https://www.bilibili.com/video/BV..."

This runs the V0.2.2 pipeline:
  1. comments: crawl text + real comment-section screenshots
  2. comment-freeze: crop screenshots into freeze-frame video
  3. comment-narration: build Codex-editable narration plan and render narrated video

Optional env:
  LOGICCUT_COMMENT_DEMO_OUTPUT
  LOGICCUT_COMMENT_LIMIT
  LOGICCUT_COMMENT_SCREENSHOTS
  LOGICCUT_COMMENT_LAYOUT
  LOGICCUT_COMMENT_MAX_FRAMES
  LOGICCUT_COMMENT_FRAME_DURATION
  LOGICCUT_COMMENT_NARRATION_ITEMS
  LOGICCUT_COMMENT_TTS_ENGINE
  LOGICCUT_COMMENT_REF_WAV
  LOGICCUT_COMMENT_REF_TEXT
  LOGICCUT_COMMENT_ALLOW_TTS_FALLBACK
  BILIBILI_COOKIES
USAGE
  exit 2
fi

CASE_DIR="${LOGICCUT_COMMENT_DEMO_OUTPUT:-${ROOT_DIR}/output/v022-comments/v022-comment-demo}"
FREEZE_DIR="${LOGICCUT_COMMENT_FREEZE_OUTPUT:-${CASE_DIR}/freeze}"
NARRATION_DIR="${LOGICCUT_COMMENT_NARRATION_OUTPUT:-${CASE_DIR}/narration}"
LAYOUT="${LOGICCUT_COMMENT_LAYOUT:-landscape}"
MAX_FRAMES="${LOGICCUT_COMMENT_MAX_FRAMES:-6}"
FRAME_DURATION="${LOGICCUT_COMMENT_FRAME_DURATION:-2.5}"
NARRATION_ITEMS="${LOGICCUT_COMMENT_NARRATION_ITEMS:-4}"
TTS_ENGINE="${LOGICCUT_COMMENT_TTS_ENGINE:-}"
REF_WAV="${LOGICCUT_COMMENT_REF_WAV:-}"
REF_TEXT="${LOGICCUT_COMMENT_REF_TEXT:-}"
ALLOW_TTS_FALLBACK="${LOGICCUT_COMMENT_ALLOW_TTS_FALLBACK:-1}"

"${ROOT_DIR}/scripts/run_v022_comment_demo.sh" "${VIDEO_URL}"

"${ROOT_DIR}/scripts/logiccut.sh" comment-freeze \
  --comments-json "${CASE_DIR}/comments.json" \
  --output-dir "${FREEZE_DIR}" \
  --layout "${LAYOUT}" \
  --max-frames "${MAX_FRAMES}" \
  --frame-duration "${FRAME_DURATION}"

narration_cmd=(
  "${ROOT_DIR}/scripts/logiccut.sh"
  comment-narration
  --comments-json "${CASE_DIR}/comments.json"
  --freeze-manifest "${FREEZE_DIR}/comment_freeze_manifest.json"
  --output-dir "${NARRATION_DIR}"
  --max-items "${NARRATION_ITEMS}"
)

if [[ -n "${TTS_ENGINE}" ]]; then
  narration_cmd+=(--tts-engine "${TTS_ENGINE}")
fi
if [[ -n "${REF_WAV}" ]]; then
  narration_cmd+=(--ref-wav "${REF_WAV}")
fi
if [[ -n "${REF_TEXT}" ]]; then
  narration_cmd+=(--ref-text "${REF_TEXT}")
fi
if [[ "${ALLOW_TTS_FALLBACK}" == "1" || "${ALLOW_TTS_FALLBACK}" == "true" || "${ALLOW_TTS_FALLBACK}" == "yes" ]]; then
  narration_cmd+=(--allow-tts-fallback)
fi

"${narration_cmd[@]}"

PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}" "${ROOT_DIR}/.venv/bin/python" - <<PY
import json
from pathlib import Path

case_dir = Path("${CASE_DIR}")
freeze_dir = Path("${FREEZE_DIR}")
narration_dir = Path("${NARRATION_DIR}")
summary = {
    "comments": str(case_dir / "comments.json"),
    "comments_report": str(case_dir / "comments_report.html"),
    "comment_freeze_video": str(freeze_dir / "comment_freeze_video.mp4"),
    "comment_freeze_report": str(freeze_dir / "comment_freeze_report.html"),
    "comment_narration_video": str(narration_dir / "comment_narration_video.mp4"),
    "comment_narration_plan": str(narration_dir / "comment_narration_plan.json"),
    "comment_narration_prompt": str(narration_dir / "comment_narration_prompt.md"),
    "comment_narration_report": str(narration_dir / "comment_narration_report.html"),
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY
