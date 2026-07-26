#!/usr/bin/env bash
# scripts/start-server.sh — Inicia llama-cpp-python servindo Qwen3.6 GGUF (ver MODEL_FILE no .env)
# Ollama continua rodando em paralelo na porta 11434 — nao e tocado

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV="$PROJECT_ROOT/.venv"

# Carregar variaveis do .env (se existir)
[ -f "$PROJECT_ROOT/.env" ] && set -a && source "$PROJECT_ROOT/.env" && set +a

MODEL_DIR="${MODEL_DIR:-$PROJECT_ROOT/data/models}"
MODEL_FILE="${MODEL_FILE:-Qwen3.6-35B-A3B-UD-Q4_K_M.gguf}"
PORT="${PORT:-8000}"
SERVED_NAME="${SERVED_NAME:-qwen3}"
N_GPU_LAYERS="${N_GPU_LAYERS:--1}"
N_CTX="${N_CTX:-73728}"
N_BATCH="${N_BATCH:-4096}"

# Quantização do KV Cache
CACHE_TYPE_K="${CACHE_TYPE_K:-q8_0}"
CACHE_TYPE_V="${CACHE_TYPE_V:-q8_0}"

# Controle de RAM (prevenção OOM)
CTX_CHECKPOINTS="${CTX_CHECKPOINTS:-16}"
CACHE_RAM="${CACHE_RAM:-4096}"
CACHE_IDLE_SLOTS="${CACHE_IDLE_SLOTS:-1}"

# Speculative Decoding (MTP)
ENABLE_MTP="${ENABLE_MTP:-true}"
MTP_TOKENS="${MTP_TOKENS:-2}"

# External draft model (alternativa ao MTP interno)
DRAFT_ENABLED="${DRAFT_ENABLED:-false}"
DRAFT_MODEL_FILE="${DRAFT_MODEL_FILE:-}"
DRAFT_N_MAX="${DRAFT_N_MAX:-5}"

# Parâmetros de amostragem (ajustáveis no .env)
# Fallbacks = valores oficiais recomendados pelo Qwen para código/tool-calling.
TEMPERATURE="${TEMPERATURE:-0.6}"
TOP_K="${TOP_K:-20}"
TOP_P="${TOP_P:-0.95}"
MIN_P="${MIN_P:-0.0}"
REPEAT_PENALTY="${REPEAT_PENALTY:-1.0}"
REPEAT_LAST_N="${REPEAT_LAST_N:-64}"
FREQUENCY_PENALTY="${FREQUENCY_PENALTY:-0.0}"
PRESENCE_PENALTY="${PRESENCE_PENALTY:-0.1}"
SEED="${SEED:--1}"
N_PREDICT="${N_PREDICT:-8192}"

# DRY sampler — anti-loop de repetição verbatim (qualquer tamanho de bloco).
# Necessário porque presence/repeat penalties leves NÃO quebram loop de parágrafo
# (evidência: loop de raciocínio repetindo o mesmo bloco até estourar 8192 — HIPOTESE-09).
# DRY penaliza só sequências longas repetidas -> não atrapalha repetição legítima de código.
DRY_MULTIPLIER="${DRY_MULTIPLIER:-1.0}"     # 0.0 = desligado
DRY_BASE="${DRY_BASE:-1.75}"
DRY_ALLOWED_LENGTH="${DRY_ALLOWED_LENGTH:-4}"   # 2 é agressivo p/ modelo thinking (rambleia)
DRY_PENALTY_LAST_N="${DRY_PENALTY_LAST_N:-2048}"  # janela (não o contexto todo)

MODEL_PATH="$MODEL_DIR/$MODEL_FILE"

# ── Validacoes ─────────────────────────────────────────────────────────────────

echo ""
echo "================================================"
echo "  llama-cpp-python — Qwen3.6 GGUF ($MODEL_FILE)"
echo "  Ollama continua em: http://localhost:11434"
echo "================================================"
echo ""

[ -d "$VENV" ] || {
    echo "ERRO: Virtualenv nao encontrado em $VENV"
    echo "      Execute scripts/setup.sh primeiro."
    exit 1
}
source "$VENV/bin/activate"

LLAMA_CPP_DIR="${LLAMA_CPP_DIR:-$HOME/llama.cpp}"
LLAMA_SERVER="${LLAMA_SERVER:-$LLAMA_CPP_DIR/build/bin/llama-server}"
[ -x "$LLAMA_SERVER" ] || {
    echo "ERRO: llama-server nao encontrado em $LLAMA_SERVER"
    echo "      Execute: make build-llama-server"
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
echo "KV cache  : K=$CACHE_TYPE_K V=$CACHE_TYPE_V"
echo "Nome API  : $SERVED_NAME"
echo "RAM ctrl  : ctx_checkpoints=$CTX_CHECKPOINTS cache_ram=${CACHE_RAM}MiB idle_slots=$CACHE_IDLE_SLOTS"
echo "Decode    : MTP=$ENABLE_MTP(tokens=$MTP_TOKENS) Draft=$DRAFT_ENABLED(n_max=$DRAFT_N_MAX)"
echo "Sampling  : temp=$TEMPERATURE top_k=$TOP_K top_p=$TOP_P min_p=$MIN_P"
echo "            repeat=$REPEAT_PENALTY(last $REPEAT_LAST_N) freq=$FREQUENCY_PENALTY pres=$PRESENCE_PENALTY"
echo "            seed=$SEED n_predict=$N_PREDICT"
echo ""

# ── Liberar VRAM do Ollama antes de iniciar ────────────────────────────────────
if curl -sf http://localhost:11434/api/ps > /dev/null 2>&1; then
    OLLAMA_MODELS=$(curl -s http://localhost:11434/api/ps 2>/dev/null | \
        python3 -c "import json,sys; d=json.load(sys.stdin); print(' '.join(m['name'] for m in d.get('models',[])))" 2>/dev/null)
    if [ -n "$OLLAMA_MODELS" ]; then
        echo "Ollama: descarregando modelos da GPU para liberar VRAM..."
        for MODEL in $OLLAMA_MODELS; do
            curl -s http://localhost:11434/api/generate \
                -d "{\"model\":\"$MODEL\",\"keep_alive\":0,\"prompt\":\"\"}" \
                > /dev/null 2>&1 && echo "  ✓ $MODEL descarregado"
        done
        sleep 2
    fi
fi

if command -v nvidia-smi &>/dev/null; then
    echo "GPU:"
    nvidia-smi --query-gpu=name,memory.used,memory.free,memory.total \
               --format=csv,noheader | awk '{print "  "$0}'
    echo ""
fi

echo "Iniciando llama-server... (pode levar 30-60s para carregar o modelo)"
echo "Para parar: Ctrl+C"
echo ""

# ── Iniciar servidor ───────────────────────────────────────────────────────────

EXTRA_FLAGS=""
[ "${NO_MMAP:-1}" = "1" ] && EXTRA_FLAGS="$EXTRA_FLAGS --no-mmap"
[ "${CACHE_IDLE_SLOTS:-0}" = "0" ] && EXTRA_FLAGS="$EXTRA_FLAGS --no-cache-idle-slots"

# DRY sampler (anti-loop) — só adiciona se ligado (multiplier != 0)
if [ "$DRY_MULTIPLIER" != "0" ] && [ "$DRY_MULTIPLIER" != "0.0" ]; then
    EXTRA_FLAGS="$EXTRA_FLAGS --dry-multiplier $DRY_MULTIPLIER --dry-base $DRY_BASE --dry-allowed-length $DRY_ALLOWED_LENGTH --dry-penalty-last-n $DRY_PENALTY_LAST_N"
fi

# ── Custom chat template ────────────────────────────────────────────
TEMPLATE_FILE="${TEMPLATE_FILE:-data/templates/custom/chat_template_local.jinja}"
CUSTOM_TEMPLATE="${PROJECT_ROOT}/${TEMPLATE_FILE}"
if [ -f "$CUSTOM_TEMPLATE" ]; then
    EXTRA_FLAGS="$EXTRA_FLAGS --chat-template-file $CUSTOM_TEMPLATE"
fi

# Heuristica de deteccao de erro do template (avisos ⚠️ + force-off do thinking).
# Default off (evita falsos positivos). ERROR_WARNINGS=true reativa via kwargs do template.
ERROR_WARNINGS="${ERROR_WARNINGS:-true}"
if [ "$ERROR_WARNINGS" = "true" ]; then
    EXTRA_FLAGS="$EXTRA_FLAGS --chat-template-kwargs {\"error_warnings\":true}"
fi

# ── Captura de conteudo para depuracao (CAPTURE_LOG) — DEFAULT OFF ───────────────
# Liga o log do CONTEUDO real das requisicoes (o server.log normal so tem timings):
#   --log-prompts-dir : grava o prompt renderizado (1 arquivo <ts>.txt por requisicao)
#   --verbose         : loga cada token gerado ("next token: N 'txt'") -> reconstroi a saida
#   --log-file        : roteia o verbose p/ arquivo SEPARADO (nao incha o server.log)
# Use `make capture-on`/`capture-off`. Volumoso: ligue so numa janela de depuracao.
CAPTURE_LOG="${CAPTURE_LOG:-false}"
if [ "$CAPTURE_LOG" = "true" ]; then
    CAPTURE_DIR="$PROJECT_ROOT/data/logs/capture"
    CAPTURE_PROMPTS="$CAPTURE_DIR/prompts/$(date +%Y-%m-%d)"
    mkdir -p "$CAPTURE_PROMPTS"
    EXTRA_FLAGS="$EXTRA_FLAGS --log-prompts-dir $CAPTURE_PROMPTS --verbose --log-file $CAPTURE_DIR/llama-verbose.log"
    echo "CAPTURA LIGADA: prompts em $CAPTURE_PROMPTS ; geracao em $CAPTURE_DIR/llama-verbose.log"
fi

# ── Speculative Decoding ────────────────────────────────────
if [ "${DRAFT_ENABLED:-false}" = "true" ] && [ -n "$DRAFT_MODEL_FILE" ]; then
    DRAFT_PATH="$MODEL_DIR/$DRAFT_MODEL_FILE"
    if [ -f "$DRAFT_PATH" ]; then
        EXTRA_FLAGS="$EXTRA_FLAGS --model-draft $DRAFT_PATH --spec-draft-n-max $DRAFT_N_MAX"
        echo "Draft model: $DRAFT_PATH (n_max=$DRAFT_N_MAX)"
    else
        echo "AVISO: Draft model nao encontrado em $DRAFT_PATH — usando MTP interno"
    fi
elif [ "${ENABLE_MTP:-false}" = "true" ]; then
    MTP_N="${MTP_TOKENS:-2}"
    EXTRA_FLAGS="$EXTRA_FLAGS --spec-type draft-mtp --spec-draft-n-max $MTP_N"
fi

exec "$LLAMA_SERVER" \
    --model            "$MODEL_PATH"        \
    --n-gpu-layers     "$N_GPU_LAYERS"      \
    --ctx-size         "$N_CTX"             \
    --batch-size       "$N_BATCH"           \
    --parallel         "${N_PARALLEL:-1}"   \
    --host             0.0.0.0              \
    --port             "$PORT"              \
    --alias            "$SERVED_NAME"       \
    --jinja                                 \
    --temp             "$TEMPERATURE"       \
    --top-k            "$TOP_K"             \
    --top-p            "$TOP_P"             \
    --min-p            "$MIN_P"             \
    --repeat-penalty   "$REPEAT_PENALTY"    \
    --repeat-last-n    "$REPEAT_LAST_N"     \
    --frequency-penalty "$FREQUENCY_PENALTY" \
    --presence-penalty "$PRESENCE_PENALTY"  \
    --seed             "$SEED"              \
    -n                 "$N_PREDICT"         \
    --ctx-checkpoints  "$CTX_CHECKPOINTS"   \
    --cache-ram        "$CACHE_RAM"         \
    --cache-type-k     "$CACHE_TYPE_K"      \
    --cache-type-v     "$CACHE_TYPE_V"      \
    $EXTRA_FLAGS
