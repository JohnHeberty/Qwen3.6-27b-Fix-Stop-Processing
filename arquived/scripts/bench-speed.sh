#!/usr/bin/env bash
# scripts/bench-speed.sh — Benchmark de velocidade para Qwen3.6-27B
# Testa diferentes configs: MTP, draft model, dual GPU
# NÃO afeta produção (roda na porta 8081)
#
# Uso: bash scripts/bench-speed.sh [teste]
#   teste = "mtp" | "draft" | "dual" | "all" (padrão: all)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEST="${1:-all}"

LLAMA_CPP_DIR="${LLAMA_CPP_DIR:-$HOME/llama.cpp}"
LLAMA_SERVER="${LLAMA_SERVER:-$LLAMA_CPP_DIR/build/bin/llama-server}"

MODEL_DIR="$PROJECT_ROOT/data/models"
MTP_MODEL="$MODEL_DIR/Qwen3.6-27B-Q4_K_M-MTP/Qwen3.6-27B-Q4_K_M-MTP.gguf"
DRAFT_MODEL="$MODEL_DIR/Qwen3.6-27B-Q4_K_M-MTP/draft/Qwen3-0.6B-Q4_K_M.gguf"
Q8_MODEL="$MODEL_DIR/Qwen3.6-27B-Q8_XL/Qwen3.6-27B-UD-Q8_K_XL.gguf"

PORT=8081
RESULTS_DIR="$PROJECT_ROOT/data/temp/bench-results"
mkdir -p "$RESULTS_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="$RESULTS_DIR/speed_bench_${TIMESTAMP}.txt"

echo "═══════════════════════════════════════════════════════" | tee "$RESULT_FILE"
echo "  Qwen3.6-27B Speed Benchmark — $(date)" | tee -a "$RESULT_FILE"
echo "═══════════════════════════════════════════════════════" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Verificar GPUs
echo "GPUs disponíveis:" | tee -a "$RESULT_FILE"
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Verificar se o modelo MTP existe
if [ ! -f "$MTP_MODEL" ]; then
    echo "ERRO: Modelo MTP não encontrado em $MTP_MODEL" | tee -a "$RESULT_FILE"
    echo "Baixe com: wget -O $MTP_MODEL 'https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF/resolve/main/Qwen3.6-27B-Q4_K_M-mtp.gguf'" | tee -a "$RESULT_FILE"
    exit 1
fi

# Função para rodar benchmark
run_bench() {
    local name="$1"
    local model="$2"
    local extra_flags="$3"
    local ctx="${4:-32768}"
    
    echo "───────────────────────────────────────────────────────" | tee -a "$RESULT_FILE"
    echo "  Teste: $name" | tee -a "$RESULT_FILE"
    echo "  Modelo: $(basename $model)" | tee -a "$RESULT_FILE"
    echo "  Contexto: $ctx" | tee -a "$RESULT_FILE"
    echo "  Flags: $extra_flags" | tee -a "$RESULT_FILE"
    echo "" | tee -a "$RESULT_FILE"
    
    # Matar servidor anterior se existir
    pkill -f "llama-server.*$PORT" 2>/dev/null || true
    sleep 2
    
    # Iniciar servidor
    echo "Iniciando servidor..." | tee -a "$RESULT_FILE"
    $LLAMA_SERVER \
        --model "$model" \
        --n-gpu-layers 999 \
        --ctx-size "$ctx" \
        --batch-size 4096 \
        --parallel 1 \
        --host 0.0.0.0 \
        --port "$PORT" \
        --alias "speed-test" \
        --jinja \
        --temp 0.6 \
        --top-k 20 \
        --top-p 0.95 \
        --min-p 0.0 \
        --repeat-penalty 1.0 \
        --seed 42 \
        -n 8192 \
        $extra_flags \
        > "$RESULTS_DIR/server_${name}.log" 2>&1 &
    
    SERVER_PID=$!
    echo "Server PID: $SERVER_PID" | tee -a "$RESULT_FILE"
    
    # Aguardar servidor ficar pronto
    echo "Aguardando servidor..." | tee -a "$RESULT_FILE"
    for i in $(seq 1 60); do
        if curl -sf "http://localhost:$PORT/health" > /dev/null 2>&1; then
            echo "Servidor pronto!" | tee -a "$RESULT_FILE"
            break
        fi
        if ! kill -0 $SERVER_PID 2>/dev/null; then
            echo "ERRO: Servidor morreu!" | tee -a "$RESULT_FILE"
            tail -20 "$RESULTS_DIR/server_${name}.log" | tee -a "$RESULT_FILE"
            return 1
        fi
        sleep 2
    done
    
    # Rodar 3 prompts de teste
    echo "" | tee -a "$RESULT_FILE"
    echo "Rodando testes..." | tee -a "$RESULT_FILE"
    
    PROMPTS=(
        "Write a Python function to check if a number is prime."
        "Explain the difference between TCP and UDP in 3 sentences."
        "Write a bash script that finds all .py files modified in the last 7 days."
    )
    
    for i in "${!PROMPTS[@]}"; do
        local prompt="${PROMPTS[$i]}"
        echo "" | tee -a "$RESULT_FILE"
        echo "  Prompt $((i+1)): ${prompt:0:50}..." | tee -a "$RESULT_FILE"
        
        RESPONSE=$(curl -s "http://localhost:$PORT/v1/chat/completions" \
            -H "Content-Type: application/json" \
            -d "{
                \"model\": \"speed-test\",
                \"messages\": [{\"role\": \"user\", \"content\": \"$prompt\"}],
                \"max_tokens\": 512,
                \"temperature\": 0.6,
                \"stream\": false
            }" 2>/dev/null)
        
        if echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'    Tokens: {d[\"usage\"][\"completion_tokens\"]}, Speed: {d[\"usage\"][\"completion_tokens\"]/d[\"usage\"][\"prompt_tokens\"]*100:.0f}%')" 2>/dev/null; then
            echo "$RESPONSE" | python3 -c "
import json,sys
d=json.load(sys.stdin)
t=d['timings']
print(f'    Prompt: {t[\"prompt_n\"]} tokens @ {t[\"prompt_per_second\"]:.1f} t/s')
print(f'    Generate: {t[\"predicted_n\"]} tokens @ {t[\"predicted_per_second\"]:.1f} t/s')
print(f'    Total: {t[\"prompt_ms\"]+t[\"predicted_ms\"]:.0f}ms')
" 2>/dev/null | tee -a "$RESULT_FILE"
        fi
    done
    
    # Parar servidor
    kill $SERVER_PID 2>/dev/null || true
    wait $SERVER_PID 2>/dev/null || true
    sleep 2
    
    echo "" | tee -a "$RESULT_FILE"
}

# ── Teste 1: Q4_K_M + MTP n=3 (single GPU) ────────────────
if [ "$TEST" = "all" ] || [ "$TEST" = "mtp" ]; then
    run_bench "q4km_mtp_n3" "$MTP_MODEL" \
        "--spec-type draft-mtp --spec-draft-n-max 3" \
        262144
fi

# ── Teste 2: Q4_K_M + MTP n=2 ─────────────────────────────
if [ "$TEST" = "all" ] || [ "$TEST" = "mtp" ]; then
    run_bench "q4km_mtp_n2" "$MTP_MODEL" \
        "--spec-type draft-mtp --spec-draft-n-max 2" \
        262144
fi

# ── Teste 3: Q4_K_M + MTP + draft model ────────────────────
if [ "$TEST" = "all" ] || [ "$TEST" = "draft" ]; then
    if [ -f "$DRAFT_MODEL" ]; then
        run_bench "q4km_mtp_draft" "$MTP_MODEL" \
            "--spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-model $DRAFT_MODEL --ctx-size-draft 4096" \
            262144
    else
        echo "Draft model não encontrado — pulando teste draft" | tee -a "$RESULT_FILE"
    fi
fi

# ── Teste 4: Dual GPU (tensor parallel) ─────────────────────
if [ "$TEST" = "all" ] || [ "$TEST" = "dual" ]; then
    run_bench "dual_gpu" "$MTP_MODEL" \
        "--tensor-split 0.5,0.5 --spec-type draft-mtp --spec-draft-n-max 3" \
        262144
fi

# ── Teste 5: Q8_0 baseline (produção atual) ─────────────────
if [ "$TEST" = "all" ]; then
    if [ -f "$Q8_MODEL" ]; then
        run_bench "q8_baseline" "$Q8_MODEL" \
            "" \
            262144
    fi
fi

echo "" | tee -a "$RESULT_FILE"
echo "═══════════════════════════════════════════════════════" | tee -a "$RESULT_FILE"
echo "  Benchmark completo!" | tee -a "$RESULT_FILE"
echo "  Resultados: $RESULT_FILE" | tee -a "$RESULT_FILE"
echo "═══════════════════════════════════════════════════════" | tee -a "$RESULT_FILE"

# Matar qualquer servidor de teste restante
pkill -f "llama-server.*$PORT" 2>/dev/null || true
