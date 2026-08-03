#!/usr/bin/env bash
# Warm CPU Unit server (ADR 0008). Mainstream llama-server, no GPU.
set -euo pipefail

INTRAFACE_HOME="${INTRAFACE_HOME:-$HOME/.intraface}"
ENV_FILE="${UNIT_RUNTIME_ENV:-$INTRAFACE_HOME/config/unit-runtime.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
fi

LLAMA_SERVER="${LLAMA_SERVER:-$HOME/prj/llama.cpp/build/bin/llama-server}"
MODEL_PATH="${UNIT_MODEL_PATH:-$INTRAFACE_HOME/models/unit/lfm2.5-1.2b-instruct/LFM2.5-1.2B-Instruct-Q4_K_M.gguf}"
HOST="${UNIT_HOST:-127.0.0.1}"
PORT="${UNIT_PORT:-7713}"
CTX="${UNIT_CTX:-32768}"
NGL="${UNIT_NGL:-0}"
LOG="${UNIT_LOG:-$INTRAFACE_HOME/state/unit-server.log}"
PIDFILE="${UNIT_PIDFILE:-$INTRAFACE_HOME/state/unit-server.pid}"

if [[ ! -x "$LLAMA_SERVER" ]]; then
  echo "unit-server: missing binary: $LLAMA_SERVER" >&2
  exit 1
fi
if [[ ! -f "$MODEL_PATH" ]]; then
  echo "unit-server: missing model: $MODEL_PATH" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG")" "$(dirname "$PIDFILE")"

# Hard CPU-only: empty CUDA visibility for this process tree.
export CUDA_VISIBLE_DEVICES=

exec "$LLAMA_SERVER" \
  -m "$MODEL_PATH" \
  --host "$HOST" \
  --port "$PORT" \
  -c "$CTX" \
  -ngl "$NGL" \
  "$@"
