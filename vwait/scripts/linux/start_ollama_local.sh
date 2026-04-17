#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OLLAMA_BIN="$ROOT_DIR/tools/ollama-local/bin/ollama"
OLLAMA_HOME="$ROOT_DIR/workspace/ollama-home"
OLLAMA_MODELS_DIR="$ROOT_DIR/workspace/ollama-models"

if [[ ! -x "$OLLAMA_BIN" ]]; then
  echo "Ollama local nao encontrado em: $OLLAMA_BIN"
  echo "Baixe/extraia o Ollama local antes de iniciar o servico."
  exit 1
fi

mkdir -p "$OLLAMA_HOME" "$OLLAMA_MODELS_DIR"

export HOME="$OLLAMA_HOME"
export OLLAMA_MODELS="$OLLAMA_MODELS_DIR"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"

echo "Iniciando Ollama local em http://$OLLAMA_HOST"
echo "Modelos em: $OLLAMA_MODELS"
exec "$OLLAMA_BIN" serve
