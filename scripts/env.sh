#!/usr/bin/env bash
# Shared LogicCut runtime environment. Source this file from setup, download,
# smoke, and adapter scripts so every tool reads the same cache/output paths.

if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  LOGICCUT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
else
  LOGICCUT_ROOT="$(pwd)"
fi

export LOGICCUT_ROOT
export LOGICCUT_VENV="${LOGICCUT_VENV:-${LOGICCUT_ROOT}/.venv}"
export LOGICCUT_MODELS_DIR="${LOGICCUT_MODELS_DIR:-${LOGICCUT_ROOT}/model_cache}"
export LOGICCUT_OUTPUT_DIR="${LOGICCUT_OUTPUT_DIR:-${LOGICCUT_ROOT}/output}"
export LOGICCUT_LOG_DIR="${LOGICCUT_LOG_DIR:-${LOGICCUT_ROOT}/logs}"

if [[ -f "${LOGICCUT_ROOT}/.env.local" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${LOGICCUT_ROOT}/.env.local"
  set +a
fi

mkdir -p \
  "${LOGICCUT_MODELS_DIR}/huggingface/hub" \
  "${LOGICCUT_MODELS_DIR}/torch" \
  "${LOGICCUT_OUTPUT_DIR}" \
  "${LOGICCUT_LOG_DIR}"

# Keep HuggingFace's standard layout:
#   HF_HOME=<root>/huggingface
#   HF_HUB_CACHE=<root>/huggingface/hub
#
# Do not set OMNIVOICE_CACHE_DIR here. OmniVoice maps that variable to both
# HF_HOME and HF_HUB_CACHE, which flattens the cache layout and makes its model
# detector miss already-downloaded weights.
unset OMNIVOICE_CACHE_DIR
export HF_HOME="${HF_HOME:-${LOGICCUT_MODELS_DIR}/huggingface}"
export HF_HUB_CACHE="${HF_HUB_CACHE:-${HF_HOME}/hub}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-${HF_HUB_CACHE}}"
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
export TORCH_HOME="${TORCH_HOME:-${LOGICCUT_MODELS_DIR}/torch}"
export AUDIOSEAL_CACHE_DIR="${AUDIOSEAL_CACHE_DIR:-${LOGICCUT_MODELS_DIR}}"
# pyannote 3.x checkpoints are trusted HF checkpoints but are not compatible
# with PyTorch 2.6+'s default weights_only=True loader.
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="${TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD:-1}"
export PYTHONNOUSERSITE="${PYTHONNOUSERSITE:-1}"

export OMNIVOICE_DATA_DIR="${OMNIVOICE_DATA_DIR:-${LOGICCUT_OUTPUT_DIR}/omnivoice-data}"
export OMNIVOICE_IDLE_TIMEOUT="${OMNIVOICE_IDLE_TIMEOUT:-900}"

export LOCAL_OUTPUT_DIR="${LOCAL_OUTPUT_DIR:-${LOGICCUT_OUTPUT_DIR}/ai-shorts}"
export LOCAL_WHISPER_MODEL="${LOCAL_WHISPER_MODEL:-Systran/faster-whisper-base}"
export LOCAL_WHISPER_DEVICE="${LOCAL_WHISPER_DEVICE:-cpu}"
export LOGICCUT_GEMINI_MODEL="${LOGICCUT_GEMINI_MODEL:-gemini-2.5-pro}"

export PATH="${LOGICCUT_VENV}/bin:${HOME}/.nimble/bin:${PATH}"
export PYTHONPATH="${LOGICCUT_ROOT}/runtime_patches:${PYTHONPATH:-}"
