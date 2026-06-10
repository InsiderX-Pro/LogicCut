#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE_PREFIX="$(npm prefix -g 2>/dev/null || true)"
PNPM_CJS="${PNPM_CJS:-${NODE_PREFIX}/lib/node_modules/pnpm/bin/pnpm.cjs}"

if [[ ! -f "${PNPM_CJS}" ]]; then
  echo "pnpm was not found. Run scripts/setup_node_tools.sh first." >&2
  exit 1
fi

export CHOKIDAR_USEPOLLING="${CHOKIDAR_USEPOLLING:-1}"
export VITE_FORCE_POLLING="${VITE_FORCE_POLLING:-1}"

node "${PNPM_CJS}" \
  --dir "${ROOT_DIR}/third_party/openreel-video" \
  --filter @openreel/web \
  exec vite --host "${HOST:-127.0.0.1}" --port "${PORT:-5173}"
