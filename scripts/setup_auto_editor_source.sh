#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTO_EDITOR_DIR="${ROOT_DIR}/third_party/auto-editor"

export PATH="${HOME}/.nimble/bin:${PATH}"

if [[ ! -d "${AUTO_EDITOR_DIR}" ]]; then
  echo "auto-editor source repo is missing. Run scripts/clone_repos.sh first." >&2
  exit 1
fi

if ! command -v nimble >/dev/null 2>&1; then
  cat >&2 <<'EOF'
nimble is required.

Install Nim with the official installer:
  curl -fsSL https://nim-lang.org/choosenim/init.sh -o /tmp/choosenim-init.sh
  sh /tmp/choosenim-init.sh -y
EOF
  exit 1
fi

if [[ "${AUTO_EDITOR_STATIC:-0}" == "1" ]]; then
  (
    cd "${AUTO_EDITOR_DIR}"
    nimble makeff -y
    nimble make -y
  )
else
  if command -v pkg-config >/dev/null 2>&1; then
    avcodec_version="$(pkg-config --modversion libavcodec 2>/dev/null || true)"
    echo "libavcodec version: ${avcodec_version:-missing}"
    avcodec_major="${avcodec_version%%.*}"
    if [[ -n "${avcodec_major}" && "${avcodec_major}" =~ ^[0-9]+$ && "${avcodec_major}" -lt 59 ]]; then
      cat >&2 <<EOF
auto-editor upstream currently uses FFmpeg channel-layout APIs that are not available in libavcodec ${avcodec_version}.

Options:
  AUTO_EDITOR_STATIC=1 ./scripts/setup_auto_editor_source.sh
  or build this adapter in a container with FFmpeg 6/7 development headers.
EOF
      exit 2
    fi
  fi
  (
    cd "${AUTO_EDITOR_DIR}"
    nimble brewmake -y
  )
fi

"${AUTO_EDITOR_DIR}/auto-editor" --version
