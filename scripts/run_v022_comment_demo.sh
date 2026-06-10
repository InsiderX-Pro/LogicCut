#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DEMO_URL="${1:-${LOGICCUT_COMMENT_DEMO_URL:-}}"
if [[ -z "${DEMO_URL}" ]]; then
  cat >&2 <<'USAGE'
Usage:
  ./scripts/run_v022_comment_demo.sh "https://www.bilibili.com/video/BV..."

Or:
  LOGICCUT_COMMENT_DEMO_URL="https://www.youtube.com/watch?v=..." ./scripts/run_v022_comment_demo.sh

Optional env:
  LOGICCUT_COMMENT_DEMO_OUTPUT
  LOGICCUT_COMMENT_LIMIT
  LOGICCUT_COMMENT_SCREENSHOTS
  BILIBILI_COOKIES
USAGE
  exit 2
fi

if [[ "${DEMO_URL}" == *"bilibili.com"* ]]; then
  PLATFORM="bilibili"
elif [[ "${DEMO_URL}" == *"youtube.com"* || "${DEMO_URL}" == *"youtu.be"* ]]; then
  PLATFORM="youtube"
else
  PLATFORM="auto"
fi

OUTPUT_DIR="${LOGICCUT_COMMENT_DEMO_OUTPUT:-${ROOT_DIR}/output/v022-comments/v022-comment-demo}"
LIMIT="${LOGICCUT_COMMENT_LIMIT:-20}"
SCREENSHOT_COUNT="${LOGICCUT_COMMENT_SCREENSHOTS:-10}"
VIEWPORT_WIDTH="${LOGICCUT_COMMENT_VIEWPORT_WIDTH:-1280}"
VIEWPORT_HEIGHT="${LOGICCUT_COMMENT_VIEWPORT_HEIGHT:-720}"
BILIBILI_COOKIES="${BILIBILI_COOKIES:-}"

cmd=(
  "${ROOT_DIR}/scripts/logiccut.sh"
  comments
  --url "${DEMO_URL}"
  --output-dir "${OUTPUT_DIR}"
  --platform "${PLATFORM}"
  --limit "${LIMIT}"
  --screenshot-count "${SCREENSHOT_COUNT}"
  --viewport-width "${VIEWPORT_WIDTH}"
  --viewport-height "${VIEWPORT_HEIGHT}"
)

if [[ "${PLATFORM}" == "bilibili" && -n "${BILIBILI_COOKIES}" && -f "${BILIBILI_COOKIES}" ]]; then
  cmd+=(--cookies "${BILIBILI_COOKIES}")
elif [[ "${PLATFORM}" == "bilibili" && -n "${BILIBILI_COOKIES}" ]]; then
  echo "[v0.2.2] Bilibili cookies not found at ${BILIBILI_COOKIES}; running anonymous screenshot mode." >&2
elif [[ "${PLATFORM}" == "bilibili" ]]; then
  echo "[v0.2.2] BILIBILI_COOKIES is not set; running anonymous screenshot mode." >&2
fi

"${cmd[@]}"

PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}" "${ROOT_DIR}/.venv/bin/python" - <<PY
import json
from pathlib import Path

from logiccut.comments import write_comments_showcase

output_dir = Path("${OUTPUT_DIR}")
showcase_dir = output_dir.parent
data = json.loads((output_dir / "comments.json").read_text(encoding="utf-8"))
case_dir_name = output_dir.name
data["report_path"] = f"{case_dir_name}/comments_report.html"
data["comment_screenshots"] = [
    {**item, "path": f"{case_dir_name}/{item.get('path', '')}"}
    for item in data.get("comment_screenshots", [])
]
index = write_comments_showcase(showcase_dir, [data])
print(json.dumps({"showcase": str(index), "case_dir": str(output_dir)}, ensure_ascii=False, indent=2))
PY
