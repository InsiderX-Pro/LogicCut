#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it first: https://docs.astral.sh/uv/" >&2
  exit 1
fi

if [[ ! -d "${LOGICCUT_ROOT}/third_party/OmniVoice-Studio" ]]; then
  "${LOGICCUT_ROOT}/scripts/clone_repos.sh"
fi

echo "[setup] Python env: ${LOGICCUT_VENV}"
UV_PROJECT_ENVIRONMENT="${LOGICCUT_VENV}" \
  uv sync \
    --project "${LOGICCUT_ROOT}/third_party/OmniVoice-Studio" \
    --no-dev \
    --extra supertonic \
    --extra eval

echo "[setup] AI-Youtube-Shorts local dependencies"
uv pip install --python "${LOGICCUT_VENV}/bin/python" \
  -r "${LOGICCUT_ROOT}/third_party/AI-Youtube-Shorts-Generator/requirements.txt" \
  -r "${LOGICCUT_ROOT}/third_party/AI-Youtube-Shorts-Generator/requirements-local.txt" \
  socksio \
  opencc-python-reimplemented \
  google-cloud-aiplatform

echo "[setup] auto-editor rough-cut adapter"
"${LOGICCUT_ROOT}/scripts/setup_auto_editor_python.sh"

if [[ "${INSTALL_NODE_TOOLS:-1}" == "1" ]]; then
  "${LOGICCUT_ROOT}/scripts/setup_node_tools.sh"
fi

cat <<EOF

LogicCut unified environment is ready.

Activate it with:
  source "${LOGICCUT_VENV}/bin/activate"

Download default local models:
  ./scripts/download_models.sh

Run checks:
  ./scripts/doctor.sh
  ./scripts/smoke_omnivoice_api.sh
  ./scripts/smoke_ai_shorts_local.sh
  ./scripts/smoke_auto_editor.sh
  ./scripts/smoke_openreel.sh
  ./scripts/smoke_pyannote.sh
  ./scripts/smoke_all.sh
EOF
