#!/usr/bin/env bash
# scripts/start-vllm.sh — sobe o Qwen3.6-27B INT4 (AutoRound) no vLLM.
#
# Lê o .env e traduz cada variável numa flag do `vllm serve`, no mesmo padrão do
# antigo start-server.sh: a fonte da verdade é o .env, este script só encaminha.
#
# ATENÇÃO: diferente do llama-server, o vLLM PRÉ-ALOCA a VRAM
# (--gpu-memory-utilization). Não dá para conviver com o Ollama nem com o
# llama-server na mesma placa — os dois têm de estar parados antes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV="$PROJECT_ROOT/.venv-vllm"

# Carrega o .env SEM sobrescrever o que já veio do ambiente — assim
# `MAX_MODEL_LEN=26624 ./scripts/start-vllm.sh` realmente vence o .env.
# (`set -a && source` faria o contrário: o .env clobberia o override inline.)
if [ -f "$PROJECT_ROOT/.env" ]; then
    while IFS= read -r _line || [ -n "$_line" ]; do
        case "$_line" in ''|\#*) continue ;; esac
        _key="${_line%%=*}"
        _val="${_line#*=}"
        case "$_key" in *[!A-Za-z0-9_]*|'') continue ;; esac
        [ -n "${!_key+x}" ] && continue      # já definido no ambiente: preserva
        export "$_key=$_val"
    done < "$PROJECT_ROOT/.env"
fi

MODEL_PATH="${MODEL_PATH:-$PROJECT_ROOT/data/models-vllm/Qwen3.6-27B-int4-AutoRound}"
SERVED_NAME="${SERVED_NAME:-qwen3}"
PORT="${PORT:-8000}"

# Contexto. O teto real depende do KV cache escolhido — ver docs/.
MAX_MODEL_LEN="${MAX_MODEL_LEN:-32768}"

# KV cache: 'auto' (fp16) = qualidade cheia, contexto menor.
#           'turboquant_3bit_nc' = 4.9x de compressão, mas a doc do vLLM mede
#           +20.6% de perplexidade e queda em raciocínio/contexto longo.
KV_CACHE_DTYPE="${KV_CACHE_DTYPE:-auto}"

# 0.97 é o da receita de referência. Baixe se der OOM na inicialização.
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.95}"

# Uso single-user: 1 sequência por vez, como o N_PARALLEL=1 do llama.cpp.
MAX_NUM_SEQS="${MAX_NUM_SEQS:-1}"
MAX_BATCHED_TOKENS="${MAX_BATCHED_TOKENS:-4128}"

# MTP — só funciona porque este quant mantém a camada mtp.fc em BF16.
ENABLE_MTP="${ENABLE_MTP:-true}"
MTP_TOKENS="${MTP_TOKENS:-3}"

# Reasoning: equivalente ao --reasoning-format deepseek do llama.cpp. Sem isto o
# `message.reasoning_content` não é populado e o OpenClaw/OpenCode param de
# mostrar o raciocínio.
REASONING_PARSER="${REASONING_PARSER:-qwen3}"

# Tool calling: sem o parser o modelo emite a tool call como texto cru e o
# cliente não enxerga nenhuma ferramenta sendo chamada.
TOOL_CALL_PARSER="${TOOL_CALL_PARSER:-hermes}"

[ -d "$VENV" ] || { echo "ERRO: venv não encontrado em $VENV"; exit 1; }
[ -d "$MODEL_PATH" ] || { echo "ERRO: modelo não encontrado em $MODEL_PATH"; exit 1; }

# ── Guarda de VRAM ────────────────────────────────────────────────────────────
if pgrep -f "llama-server --model" > /dev/null 2>&1; then
    echo "ERRO: llama-server está rodando e segurando a VRAM."
    echo "      Pare com: systemctl stop qwen-server"
    exit 1
fi
if curl -sf -m 3 http://localhost:11434/api/ps 2>/dev/null | grep -q '"name"'; then
    echo "AVISO: Ollama tem modelo carregado na GPU. Descarregando..."
    curl -s http://localhost:11434/api/generate -d '{"model":"","keep_alive":0}' >/dev/null 2>&1 || true
fi

echo ""
echo "================================================"
echo "  vLLM — Qwen3.6-27B INT4 AutoRound"
echo "================================================"
echo "Modelo    : $MODEL_PATH"
echo "Porta     : $PORT   (nome na API: $SERVED_NAME)"
echo "Contexto  : $MAX_MODEL_LEN tokens"
echo "KV cache  : $KV_CACHE_DTYPE"
echo "VRAM util : $GPU_MEM_UTIL"
echo "MTP       : $ENABLE_MTP (n=$MTP_TOKENS)"
echo "Parsers   : reasoning=$REASONING_PARSER tool=$TOOL_CALL_PARSER"
echo ""
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader | awk '{print "GPU livre : "$3" "$4}'
echo ""

EXTRA=()
if [ "$ENABLE_MTP" = "true" ]; then
    EXTRA+=(--speculative-config "{\"method\":\"mtp\",\"num_speculative_tokens\":$MTP_TOKENS}")
fi

source "$VENV/bin/activate"

# O FlashInfer tenta compilar kernels de sampling em JIT no primeiro boot e falha
# aqui: o torch é cu130 e os headers do sistema são 12.8 (cuda_runtime.h não
# encontrado / mismatch). O sampler é só uma otimização — o nativo do vLLM
# funciona. Se um dia o CUDA do sistema casar com o do torch, dá para religar.
# O FlashInfer compila kernels em JIT no primeiro request. Por padrão ele acha o
# nvcc do sistema (CUDA 12.8) e falha com "cuda_runtime.h: No such file or
# directory", porque o torch aqui é cu130 e os includes do sistema não são
# passados. O próprio wheel do torch traz um toolkit CUDA 13 completo (nvcc +
# headers) — apontar o CUDA_HOME para ele casa compilador, headers e runtime.
# Combinação que funciona (achada por tentativa, 2026-07-29):
#   flashinfer-python 0.6.13 + flashinfer-cubin 0.6.13 + CUDA_HOME=/usr/local/cuda (12.8)
# O cccl que o flashinfer 0.6.13 empacota espera CUDA 12.x. Apontar para o
# toolkit cu13 que vem no wheel do torch faz o nvcc reclamar de
# "CUDA compiler and CUDA toolkit headers are incompatible"; não apontar nada
# faz ele não achar cuda_runtime.h. Tem de ser o 12.8 do sistema.
#
# ⚠️ Ao atualizar o vLLM, o flashinfer volta para 0.6.14 e isso quebra de novo.
#    Reinstale com: uv pip install --no-deps \
#      "flashinfer-python==0.6.13" "flashinfer-cubin==0.6.13"
#    O --no-deps é obrigatório: sem ele o flashinfer arrasta o torch para cu12
#    e destrói o ambiente.
if [ -x "/usr/local/cuda/bin/nvcc" ]; then
    export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
    export PATH="$CUDA_HOME/bin:$PATH"
fi

# Se ainda assim o JIT falhar, este flag desliga só o sampler do FlashInfer
# (o backend de atenção continua). 0 = desligado.
export VLLM_USE_FLASHINFER_SAMPLER="${VLLM_USE_FLASHINFER_SAMPLER:-0}"

# Backend de atenção. Com KV em fp8 o vLLM escolhe o FlashInfer sozinho, que
# também compila em JIT e falha pelo mesmo motivo. O Triton traz o próprio
# toolchain (não depende dos headers do sistema) — é o backend que as receitas
# de referência usam em Ampere. Deixe vazio para o vLLM escolher.
if [ -n "${VLLM_ATTENTION_BACKEND:-}" ]; then
    export VLLM_ATTENTION_BACKEND
    echo "Attention : $VLLM_ATTENTION_BACKEND"
fi

exec vllm serve "$MODEL_PATH" \
    --served-model-name   "$SERVED_NAME" \
    --host                0.0.0.0 \
    --port                "$PORT" \
    --max-model-len       "$MAX_MODEL_LEN" \
    --kv-cache-dtype      "$KV_CACHE_DTYPE" \
    --gpu-memory-utilization "$GPU_MEM_UTIL" \
    --max-num-seqs        "$MAX_NUM_SEQS" \
    --max-num-batched-tokens "$MAX_BATCHED_TOKENS" \
    --reasoning-parser    "$REASONING_PARSER" \
    --tool-call-parser    "$TOOL_CALL_PARSER" \
    --enable-auto-tool-choice \
    --enable-chunked-prefill \
    --enable-prefix-caching \
    "${EXTRA[@]}"
