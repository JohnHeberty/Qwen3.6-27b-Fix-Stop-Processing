#!/usr/bin/env bash
# scripts/benchmark-ctx-sweep.sh — Benchmark sweep incremental 8k→max
# Testa N_CTX de 8192 ate max, incremento de 8192, com MTP habilitado.
# Para quando VRAM insuficiente ou servidor crasha.
#
# Uso:
#   bash scripts/benchmark-ctx-sweep.sh
#   bash scripts/benchmark-ctx-sweep.sh --start 8192 --step 8192 --max 131072
#   bash scripts/benchmark-ctx-sweep.sh --fill 90 --max-tokens 2048

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# ── Defaults ──────────────────────────────────────────────────────────────────
START_CTX=8192
STEP_CTX=8192
MAX_CTX=131072
FILL_PERCENT=90
MAX_TOKENS=2048
HEALTH_URL="http://localhost:8000/health"
CHAT_URL="http://localhost:8000/v1/chat/completions"
PDF_PATH="data/temp/RL_OREILLY_full.md"
RESULTS_DIR="data/temp"
PROMPT_FILE="$RESULTS_DIR/_bench_prompt.json"

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --start)      START_CTX="$2"; shift 2 ;;
        --step)       STEP_CTX="$2"; shift 2 ;;
        --max)        MAX_CTX="$2"; shift 2 ;;
        --fill)       FILL_PERCENT="$2"; shift 2 ;;
        --max-tokens) MAX_TOKENS="$2"; shift 2 ;;
        *) echo "Arg desconhecido: $1"; exit 1 ;;
    esac
done

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_FILE="$RESULTS_DIR/benchmark_sweep_${TIMESTAMP}.json"
mkdir -p "$RESULTS_DIR"

# ── Helpers ───────────────────────────────────────────────────────────────────

log() { echo "[$(date +%H:%M:%S)] $*"; }

get_vram() {
    nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits 2>/dev/null | head -1
}

get_ram_free() {
    awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo
}

get_rss() {
    ps -o rss= -C llama-server 2>/dev/null | awk '{s+=$1} END {print int(s/1024)}'
}

wait_server() {
    local timeout=180 elapsed=0
    while [ $elapsed -lt $timeout ]; do
        if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then return 0; fi
        sleep 3; elapsed=$((elapsed + 3))
    done
    return 1
}

stop_server() {
    pkill -f llama-server 2>/dev/null || true; sleep 3
    pkill -9 -f llama-server 2>/dev/null || true; sleep 2
}

update_env() {
    local new_ctx=$1
    if grep -q "^N_CTX=" .env 2>/dev/null; then
        sed -i "s/^N_CTX=.*/N_CTX=$new_ctx/" .env
    else
        echo "N_CTX=$new_ctx" >> .env
    fi
}

# ── Build prompt JSON file (avoids shell escaping issues) ─────────────────────
build_prompt_json() {
    local target_chars=$1
    python3 -c "
import json, sys

# Read truncated text from file
with open(sys.argv[1], 'r', encoding='utf-8', errors='replace') as f:
    text = f.read($target_chars)

prompt = '''Voce recebeu um livro completo sobre Reinforcement Learning. Analise e resuma em 3-5 paragrafos.

Conteudo:
''' + text

data = {
    'model': 'qwen3',
    'messages': [{'role': 'user', 'content': prompt}],
    'max_tokens': $MAX_TOKENS,
    'temperature': 0.3,
    'stream': False
}
with open(sys.argv[2], 'w') as f:
    json.dump(data, f)
print(len(text))
" "$PDF_PATH" "$PROMPT_FILE"
}

# ── Load PDF ──────────────────────────────────────────────────────────────────
if [ ! -f "$PDF_PATH" ]; then
    echo "ERRO: PDF não encontrado em $PDF_PATH"; exit 1
fi

PDF_CHARS=$(wc -c < "$PDF_PATH")
log "PDF: $PDF_CHARS caracteres (~$((PDF_CHARS * 10 / 35)) tokens)"

# ── Generate contexts ─────────────────────────────────────────────────────────
CONTEXTS=()
ctx=$START_CTX
while [ $ctx -le $MAX_CTX ]; do
    CONTEXTS+=($ctx)
    ctx=$((ctx + STEP_CTX))
done

log "Testes: ${#CONTEXTS[@]} | Start=$START_CTX Step=$STEP_CTX Max=$MAX_CTX"
for c in "${CONTEXTS[@]}"; do log "  N_CTX=$c ($((c/1024))k)"; done

# ── Main loop ─────────────────────────────────────────────────────────────────
RESULTS_JSON=()
STOPPED=false

for i in "${!CONTEXTS[@]}"; do
    N_CTX=${CONTEXTS[$i]}
    CTX_K=$((N_CTX / 1024))
    IDX=$((i + 1)); TOTAL=${#CONTEXTS[@]}

    log ""
    log "================================================================"
    log "[$IDX/$TOTAL] N_CTX=$N_CTX (${CTX_K}k)"
    log "================================================================"

    stop_server
    update_env "$N_CTX"

    log "Iniciando servidor..."
    make start-bg > /dev/null 2>&1 || true

    if ! wait_server; then
        log "ERRO: Servidor não iniciou"
        RESULTS_JSON+=("{\"n_ctx\":$N_CTX,\"status\":\"fail\"}")
        continue
    fi
    sleep 5

    # Baseline
    VRAM_LINE=$(get_vram)
    VRAM_USED=$(echo "$VRAM_LINE" | cut -d',' -f1 | tr -d ' ')
    VRAM_FREE=$(echo "$VRAM_LINE" | cut -d',' -f2 | tr -d ' ')
    RAM_FREE_BEFORE=$(get_ram_free)
    RSS_BEFORE=$(get_rss)
    log "Baseline: VRAM ${VRAM_USED}/${VRAM_FREE} MiB | RAM livre ${RAM_FREE_BEFORE} MiB"

    # Build prompt
    TARGET_CHARS=$((N_CTX * FILL_PERCENT / 100 * 35 / 100))
    [ "$TARGET_CHARS" -gt "$PDF_CHARS" ] && TARGET_CHARS=$PDF_CHARS
    CHARS_USED=$(build_prompt_json "$TARGET_CHARS")
    EST_TOKENS=$((CHARS_USED * 10 / 35))
    log "Prompt: ~${EST_TOKENS} tokens (${FILL_PERCENT}% de ${CTX_K}k)"

    # Send request
    PROMPT_START=$(date +%s%N)
    HTTP_CODE=$(curl -s -o "$RESULTS_DIR/_bench_resp.json" -w "%{http_code}" \
        "$CHAT_URL" -H "Content-Type: application/json" \
        -d @"$PROMPT_FILE" --max-time 600 2>/dev/null || echo "000")
    PROMPT_END=$(date +%s%N)
    PROMPT_MS=$(( (PROMPT_END - PROMPT_START) / 1000000 ))

    # Post-request measurements
    VRAM_AFTER=$(get_vram)
    VRAM_AFTER_USED=$(echo "$VRAM_AFTER" | cut -d',' -f1 | tr -d ' ')
    VRAM_AFTER_FREE=$(echo "$VRAM_AFTER" | cut -d',' -f2 | tr -d ' ')
    RAM_FREE_AFTER=$(get_ram_free)
    RSS_AFTER=$(get_rss)
    RAM_DELTA=$((RAM_FREE_BEFORE - RAM_FREE_AFTER))

    log "HTTP $HTTP_CODE | ${PROMPT_MS}ms | VRAM: ${VRAM_AFTER_USED}/${VRAM_AFTER_FREE} MiB | RAM Δ: ${RAM_DELTA} MiB"

    # Status check
    STATUS="ok"
    if [ "$HTTP_CODE" = "000" ] || [ "$HTTP_CODE" = "500" ] || [ "$HTTP_CODE" = "503" ]; then
        STATUS="oom"
        STOPPED=true
        log "!! SERVIDOR CRASHOU (HTTP $HTTP_CODE)"
    elif [ "$VRAM_AFTER_FREE" -lt 200 ]; then
        STATUS="vram_exhausted"
        STOPPED=true
        log "!! VRAM livre < 200 MiB"
    fi

    # Extract metrics via python
    METRICS=$(python3 -c "
import json, sys
try:
    with open('$RESULTS_DIR/_bench_resp.json') as f:
        d = json.load(f)
    u = d.get('usage', {})
    comp = u.get('completion_tokens', 0)
    prompt_t = u.get('prompt_tokens', 0)
    total_ms = $PROMPT_MS
    # Estimate gen time: total - prompt processing (~30% of total for prompt)
    gen_ms = max(total_ms * 0.6, 1)  # rough estimate
    speed = round(comp / (gen_ms / 1000), 1) if comp > 0 else 0
    print(f'{comp} {prompt_t} {speed}')
except Exception as e:
    print(f'0 0 0')
" 2>/dev/null || echo "0 0 0")

    TOKENS_GEN=$(echo "$METRICS" | awk '{print $1}')
    PROMPT_TOKENS=$(echo "$METRICS" | awk '{print $2}')
    TOK_PER_SEC=$(echo "$METRICS" | awk '{print $3}')

    log "Tokens: gen=$TOKENS_GEN prompt=$PROMPT_TOKENS speed=${TOK_PER_SEC} tok/s"

    # Result JSON
    RESULT=$(python3 -c "
import json
r = {
    'n_ctx': $N_CTX,
    'vram_used': $VRAM_AFTER_USED,
    'vram_free': $VRAM_AFTER_FREE,
    'ram_delta': $RAM_DELTA,
    'rss': $RSS_AFTER,
    'prompt_ms': $PROMPT_MS,
    'tokens_gen': $TOKENS_GEN,
    'tok_per_sec': $TOK_PER_SEC,
    'status': '$STATUS'
}
print(json.dumps(r))
")
    RESULTS_JSON+=("$RESULT")

    # Save checkpoint
    python3 -c "
import json
results = [$(IFS=,; echo "${RESULTS_JSON[*]}")]
with open('$RESULTS_FILE', 'w') as f:
    json.dump({'timestamp': '$TIMESTAMP', 'results': results}, f, indent=2)
" 2>/dev/null || true

    if [ "$STOPPED" = true ]; then
        log "!! Sweep interrompido em N_CTX=$N_CTX"; break
    fi
done

stop_server

# ── Print results ─────────────────────────────────────────────────────────────
log ""
log "================================================================"
log " RESULTADOS"
log "================================================================"
echo ""
echo "| \`N_CTX\` | Context | VRAM used | VRAM free | RAM Δ | tok/s | Prompt | Status |"
echo "|---|---|---|---|---|---|---|---|"

for r in "${RESULTS_JSON[@]}"; do
    echo "$r" | python3 -c "
import json, sys
r = json.loads(sys.stdin.read())
ctx = r['n_ctx']
icons = {'ok': '✓', 'oom': '✗ OOM', 'vram_exhausted': '✗ VRAM', 'fail': '✗ FAIL'}
print(f\"| {ctx:,} | {ctx//1024}k | {r['vram_used']} MiB | {r['vram_free']} MiB | {r['ram_delta']} MiB | {r['tok_per_sec']} | {r['prompt_ms']}ms | {icons.get(r['status'], r['status'])} |\")
"
done

echo ""
log "Salvo: $RESULTS_FILE"
log "Sweep completo!"
