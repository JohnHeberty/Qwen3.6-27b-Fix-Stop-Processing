#!/usr/bin/env bash
# Qwen3.8-27B AutoRound + DFlash2, distribuido nas duas RTX 3090.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROFILE="${VLLM_DFLASH2_ENV:-$PROJECT_ROOT/.env.vllm-dflash2}"

if [ -f "$PROFILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$PROFILE"
    set +a
fi

VLLM_ROOT="${VLLM_ROOT:-$PROJECT_ROOT/qwen38-27b-rtx3090}"
VLLM_BIN="${VLLM_BIN:-$VLLM_ROOT/venv/bin/vllm}"
TARGET_MODEL="${TARGET_MODEL:-$VLLM_ROOT/models/Qwen3.8-27B-int4-AutoRound-Frozenlock}"
DRAFT_MODEL="${DRAFT_MODEL:-$VLLM_ROOT/models/Qwen3.8-27B-DFlash2-zlab}"
SERVED_NAME="${SERVED_NAME:-qwen3.8-27b}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-96000}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.95}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-2}"
MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-8192}"
DRAFT_TOKENS="${DFLASH_DRAFT_TOKENS:-7}"
LONG_PREFILL_TOKEN_THRESHOLD="${LONG_PREFILL_TOKEN_THRESHOLD:-1600}"
CUDA_TOOLKIT="${CUDA_TOOLKIT:-/usr/local/cuda-12.8}"
CUDA_PY_ROOT="${CUDA_PY_ROOT:-$VLLM_ROOT/venv/lib/python3.12/site-packages/nvidia/cu13}"
DEFAULT_CHAT_TEMPLATE_KWARGS="${DEFAULT_CHAT_TEMPLATE_KWARGS:-}"
GENERATION_CONFIG="${GENERATION_CONFIG:-}"
[ -n "$DEFAULT_CHAT_TEMPLATE_KWARGS" ] || DEFAULT_CHAT_TEMPLATE_KWARGS='{"enable_thinking":true,"reasoning_effort":"low","preserve_thinking":false}'
[ -n "$GENERATION_CONFIG" ] || GENERATION_CONFIG='{"temperature":0.6,"top_p":0.95,"top_k":20,"min_p":0.0,"repetition_penalty":1.0}'

[ -x "$VLLM_BIN" ] || { echo "ERRO: vLLM nao encontrado em $VLLM_BIN" >&2; exit 1; }
[ -s "$TARGET_MODEL/config.json" ] || { echo "ERRO: modelo alvo ausente em $TARGET_MODEL" >&2; exit 1; }
[ -s "$DRAFT_MODEL/model.safetensors" ] || { echo "ERRO: drafter DFlash2 ausente em $DRAFT_MODEL" >&2; exit 1; }

# Evita que um modelo carregado pelo Ollama dispute VRAM com o TP=2.
if curl -sf http://127.0.0.1:11434/api/ps >/dev/null 2>&1; then
    while read -r model; do
        [ -n "$model" ] || continue
        curl -sf http://127.0.0.1:11434/api/generate \
            -d "{\"model\":\"$model\",\"keep_alive\":0,\"prompt\":\"\"}" \
            >/dev/null 2>&1 || true
    done < <(curl -s http://127.0.0.1:11434/api/ps | python3 -c \
        "import json,sys; print(*[m['name'] for m in json.load(sys.stdin).get('models',[])], sep='\\n')")
fi

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1}"
export CUDA_HOME="$CUDA_TOOLKIT"
export PATH="$CUDA_TOOLKIT/bin:$VLLM_ROOT/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export CPATH="$CUDA_TOOLKIT/include${CPATH:+:$CPATH}"
export LD_LIBRARY_PATH="$CUDA_PY_ROOT/lib:$CUDA_TOOLKIT/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_MARLIN_USE_ATOMIC_ADD=1
export VLLM_DFLASH2_TORCH_TOPK=1
export VLLM_DFLASH2_LOOKUP="${VLLM_DFLASH2_LOOKUP:-0}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-max_split_size_mb:512}"

echo "Qwen3.8 DFlash2 TP=2: $SERVED_NAME em $HOST:$PORT"
echo "Contexto=$MAX_MODEL_LEN, concorrencia=$MAX_NUM_SEQS, drafts=$DRAFT_TOKENS, thinking=low"

exec "$VLLM_BIN" serve "$TARGET_MODEL" \
    --served-model-name "$SERVED_NAME" \
    --host "$HOST" --port "$PORT" \
    --quantization inc --dtype bfloat16 \
    --tensor-parallel-size 2 \
    --max-model-len "$MAX_MODEL_LEN" \
    --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
    --max-num-seqs "$MAX_NUM_SEQS" \
    --max-num-batched-tokens "$MAX_NUM_BATCHED_TOKENS" \
    --long-prefill-token-threshold "$LONG_PREFILL_TOKEN_THRESHOLD" \
    --kv-cache-dtype int8_per_token_head \
    --mamba-ssm-cache-dtype float16 \
    --enable-mamba-cache-stochastic-rounding \
    --attention-backend TRITON_ATTN \
    --language-model-only \
    --trust-remote-code \
    --enable-chunked-prefill \
    --async-scheduling \
    --reasoning-parser qwen3 \
    --default-chat-template-kwargs "$DEFAULT_CHAT_TEMPLATE_KWARGS" \
    --override-generation-config "$GENERATION_CONFIG" \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_coder \
    --speculative-config "{\"method\":\"dflash\",\"model\":\"$DRAFT_MODEL\",\"num_speculative_tokens\":$DRAFT_TOKENS}"
