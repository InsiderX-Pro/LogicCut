#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE_PREFIX="$(npm prefix -g 2>/dev/null || true)"
PNPM_CJS="${PNPM_CJS:-${NODE_PREFIX}/lib/node_modules/pnpm/bin/pnpm.cjs}"

if ! command -v bun >/dev/null 2>&1; then
  echo "bun is required for OmniVoice-Studio but was not found." >&2
  exit 1
fi

if [[ ! -f "${PNPM_CJS}" ]]; then
  npm install -g pnpm@9.0.0
fi

if [[ ! -f "${PNPM_CJS}" ]]; then
  echo "pnpm was installed but ${PNPM_CJS} was not found." >&2
  exit 1
fi

if [[ -d "${ROOT_DIR}/third_party/OmniVoice-Studio" ]]; then
  echo "[setup] OmniVoice-Studio bun install"
  bun install --cwd "${ROOT_DIR}/third_party/OmniVoice-Studio"
fi

if [[ -d "${ROOT_DIR}/third_party/openreel-video" ]]; then
  echo "[setup] OpenReel pnpm install"
  timeout "${OPENREEL_INSTALL_TIMEOUT_SECONDS:-240}"s \
    node "${PNPM_CJS}" --dir "${ROOT_DIR}/third_party/openreel-video" install \
      --ignore-scripts --prefer-offline --child-concurrency=1 --network-concurrency=4 --reporter=append-only
fi

cat <<EOF

Node/Bun tool setup finished.

OmniVoice-Studio:
  cd third_party/OmniVoice-Studio
  bun run smoke-test:quick

OpenReel:
  ./scripts/run_openreel_dev.sh

EOF
