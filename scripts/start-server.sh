#!/usr/bin/env bash
# scripts/start-server.sh — Inicia llama-cpp-python servindo Qwen3.6 27B GGUF
# Ollama continua rodando em paralelo na porta 11434 — nao e tocado

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV="$PROJECT_ROOT/.venv"

# Carregar variaveis do .env (se existir)
[ -f "$PROJECT_ROOT/.env" ] && set -a && source "$PROJECT_ROOT/.env" && set +a

MODEL_DIR="${MODEL_DIR:-$PROJECT_ROOT/data/models}"
MODEL_FILE="${MODEL_FILE:-Qwen3.6-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf}"
PORT="${PORT:-8000}"
SERVED_NAME="${SERVED_NAME:-qwen3}"
N_GPU_LAYERS="${N_GPU_LAYERS:--1}"
N_CTX="${N_CTX:-63488}"
N_BATCH="${N_BATCH:-512}"

MODEL_PATH="$MODEL_DIR/$MODEL_FILE"

# ── Validacoes ─────────────────────────────────────────────────────────────────

echo ""
echo "================================================"
echo "  llama-cpp-python — Qwen3.6 27B GGUF"
echo "  Ollama continua em: http://localhost:11434"
echo "================================================"
echo ""

[ -d "$VENV" ] || {
    echo "ERRO: Virtualenv nao encontrado em $VENV"
    echo "      Execute scripts/setup.sh primeiro."
    exit 1
}
source "$VENV/bin/activate"

LLAMA_SERVER="${LLAMA_SERVER:-/root/llama.cpp/build/bin/llama-server}"
[ -x "$LLAMA_SERVER" ] || {
    echo "ERRO: llama-server nao encontrado em $LLAMA_SERVER"
    echo "      Execute: cd /root/llama.cpp && cmake --build build --target llama-server"
    exit 1
}

[ -f "$MODEL_PATH" ] || {
    echo "ERRO: Modelo nao encontrado em $MODEL_PATH"
    echo "      Execute scripts/setup.sh primeiro."
    exit 1
}

echo "Modelo    : $MODEL_PATH"
echo "Porta     : $PORT  (Ollama em 11434)"
echo "GPU layers: $N_GPU_LAYERS (todos na GPU)"
echo "Contexto  : $N_CTX tokens"
echo "Nome API  : $SERVED_NAME"
echo ""

if command -v nvidia-smi &>/dev/null; then
    echo "GPU:"
    nvidia-smi --query-gpu=name,memory.used,memory.free,memory.total \
               --format=csv,noheader | awk '{print "  "$0}'
    echo ""
fi

echo "Iniciando llama-cpp-python... (pode levar 30-60s para carregar o modelo)"
echo "Para parar: Ctrl+C"
echo ""

# ── Iniciar servidor ───────────────────────────────────────────────────────────

exec "$LLAMA_SERVER" \
    --model        "$MODEL_PATH"   \
    --n-gpu-layers "$N_GPU_LAYERS" \
    --ctx-size     "$N_CTX"        \
    --batch-size   "$N_BATCH"      \
    --host         0.0.0.0         \
    --port         "$PORT"         \
    --alias        "$SERVED_NAME"  \
    --jinja
