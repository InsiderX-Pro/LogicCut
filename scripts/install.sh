#!/usr/bin/env bash
set -euo pipefail

PROFILE="lite"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

python3 scripts/bootstrap.py --profile "${PROFILE}"

if [[ "${PROFILE}" == "full" ]]; then
  if [[ -x scripts/setup_unified_env.sh ]]; then
    scripts/setup_unified_env.sh
  fi
fi
