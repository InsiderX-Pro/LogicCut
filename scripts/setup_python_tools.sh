#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"

python3 -m venv "${VENV_DIR}"
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip wheel setuptools
python -m pip install opencc-python-reimplemented

if [[ -d "${ROOT_DIR}/third_party/AI-Youtube-Shorts-Generator" ]]; then
  python -m pip install -r "${ROOT_DIR}/third_party/AI-Youtube-Shorts-Generator/requirements.txt"
  if [[ "${INSTALL_AI_SHORTS_LOCAL:-0}" == "1" ]]; then
    python -m pip install -r "${ROOT_DIR}/third_party/AI-Youtube-Shorts-Generator/requirements-local.txt"
  fi
fi

python - <<'PY'
import shutil
import subprocess

print("python tools:")
for command in ["ffmpeg"]:
    path = shutil.which(command)
    print(f"- {command}: {path or 'missing'}")
PY

cat <<EOF

Reusable Python env is ready:
  source "${VENV_DIR}/bin/activate"

Next:
  ./scripts/doctor.sh

Heavy adapters such as OmniVoice-Studio and AI-Youtube-Shorts-Generator are cloned under third_party/.
Install them only after reading their upstream requirements and model/license notes.

Optional local high-light clipping dependencies:
  INSTALL_AI_SHORTS_LOCAL=1 ./scripts/setup_python_tools.sh

auto-editor is built through its Nim source path:
  ./scripts/setup_auto_editor_source.sh
EOF
