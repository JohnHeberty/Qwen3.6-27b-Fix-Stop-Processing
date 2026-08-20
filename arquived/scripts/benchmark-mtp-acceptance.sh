#!/usr/bin/env bash
# Compara MTP por throughput real e aceitacao em prompts diferentes.
# O servidor de producao deve estar parado enquanto este script roda.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER="${LLAMA_SERVER:-/root/llama.cpp-b10502/build-cuda/bin/llama-server}"
MODEL="${MODEL_PATH:-$PROJECT_ROOT/data/models/Qwen3.8-27B-UD-Q4_K_XL/Qwen3.8-27B-UD-Q4_K_XL.gguf}"
PORT="${BENCH_PORT:-18081}"
TOKENS="${BENCH_TOKENS:-256}"
OUT_DIR="${BENCH_OUT_DIR:-$PROJECT_ROOT/data/temp/mtp-sweep-$(date +%Y%m%d-%H%M%S)}"
# Lista opcional separada por espacos, por exemplo: BENCH_CONFIGS='n1_p0 n2_p05'.
BENCH_CONFIGS="${BENCH_CONFIGS:-}"

mkdir -p "$OUT_DIR"
RESULTS="$OUT_DIR/results.csv"
printf '%s\n' 'config,prompt,tokens,tok_s,draft,accepted,accept_pct' > "$RESULTS"

bench_pid=""
cleanup() {
    if [ -n "$bench_pid" ] && kill -0 "$bench_pid" 2>/dev/null; then
        kill "$bench_pid" 2>/dev/null || true
        wait "$bench_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

wait_ready() {
    local attempt
    for attempt in $(seq 1 120); do
        if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
            return 0
        fi
        if ! kill -0 "$bench_pid" 2>/dev/null; then
            echo "ERRO: servidor de benchmark encerrou durante a carga" >&2
            return 1
        fi
        sleep 1
    done
    echo "ERRO: timeout carregando servidor de benchmark" >&2
    return 1
}

run_prompt() {
    local config="$1" name="$2" prompt="$3" response
    response="$OUT_DIR/${config}-${name}.json"
    jq -n \
        --arg prompt "$prompt" \
        --argjson n_predict "$TOKENS" \
        '{prompt:$prompt,n_predict:$n_predict,temperature:0.3,top_k:20,top_p:0.95,min_p:0.0,seed:42,ignore_eos:true,stream:false}' |
        curl -fsS "http://127.0.0.1:$PORT/completion" \
            -H 'Content-Type: application/json' --data-binary @- > "$response"

    jq -r --arg config "$config" --arg name "$name" '
        [.tokens_predicted,
         .timings.predicted_per_second,
         (.timings.draft_n // 0),
         (.timings.draft_n_accepted // 0)] as $v |
        [$config,$name,$v[0],$v[1],$v[2],$v[3],
         (if $v[2] > 0 then (100*$v[3]/$v[2]) else 0 end)] | @csv
    ' "$response" >> "$RESULTS"
}

run_config() {
    local config="$1"
    shift
    local -a spec_flags=("$@")
    local log="$OUT_DIR/${config}.log"

    if [ -n "$BENCH_CONFIGS" ] && [[ " $BENCH_CONFIGS " != *" $config "* ]]; then
        return 0
    fi

    echo "== $config: ${spec_flags[*]:-sem MTP} =="
    CUDA_VISIBLE_DEVICES=0,1 "$SERVER" \
        --model "$MODEL" \
        --n-gpu-layers 999 \
        --ctx-size 32768 \
        --batch-size 4096 \
        --ubatch-size 512 \
        --threads 8 \
        --threads-batch 8 \
        --flash-attn on \
        --parallel 1 \
        --split-mode layer \
        --tensor-split 0.55,0.45 \
        --cache-type-k q8_0 \
        --cache-type-v q8_0 \
        --mmap \
        --backend-sampling \
        --no-context-shift \
        --no-webui \
        --host 127.0.0.1 \
        --port "$PORT" \
        "${spec_flags[@]}" > "$log" 2>&1 &
    bench_pid=$!
    wait_ready

    run_prompt "$config" prose \
        'Write a detailed technical essay explaining how TCP congestion control evolves from slow start through congestion avoidance. Use connected prose, concrete examples, and no lists.'
    run_prompt "$config" code \
        $'Complete this Python implementation of an LRU cache and explain the invariants after the code:\n\nclass Node:\n    def __init__(self, key, value):\n        self.key = key\n        self.value = value\n        self.prev = None\n        self.next = None\n\nclass LRUCache:'
    run_prompt "$config" reasoning \
        'A warehouse has 120 boxes. Red boxes are twice the number of blue boxes, and green boxes are 15 fewer than red boxes. Determine each count, check the constraints carefully, then explain the general algebraic method.'

    cleanup
    bench_pid=""
    sleep 2
}

# p_min alto pode elevar a porcentagem simplesmente desistindo de drafts dificeis;
# por isso cada caso tambem e comparado por tok/s contra o baseline sem MTP.
run_config off
run_config n1_p0   --spec-type draft-mtp --spec-draft-n-max 1 --spec-draft-p-min 0
run_config n2_p0   --spec-type draft-mtp --spec-draft-n-max 2 --spec-draft-p-min 0
run_config n2_p05  --spec-type draft-mtp --spec-draft-n-max 2 --spec-draft-p-min 0.5
run_config n2_p08  --spec-type draft-mtp --spec-draft-n-max 2 --spec-draft-p-min 0.8
run_config n3_p0   --spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0
run_config n4_p0   --spec-type draft-mtp --spec-draft-n-max 4 --spec-draft-p-min 0
run_config n6_p0   --spec-type draft-mtp --spec-draft-n-max 6 --spec-draft-p-min 0
run_config n6_p02  --spec-type draft-mtp --spec-draft-n-max 6 --spec-draft-p-min 0.2
run_config n8_p05  --spec-type draft-mtp --spec-draft-n-max 8 --spec-draft-p-min 0.5

echo
echo "Resultados: $RESULTS"
jq -Rn '
  [inputs | split(",") | map(gsub("^\"|\"$";""))] as $rows |
  $rows
' </dev/null >/dev/null

awk -F, '
    NR > 1 {
        gsub(/"/, "")
        count[$1]++
        speed[$1]+=$4
        draft[$1]+=$5
        accepted[$1]+=$6
    }
    END {
        printf "%-10s %10s %12s\n", "config", "tok/s avg", "accept"
        for (c in count) {
            pct = draft[c] ? 100*accepted[c]/draft[c] : 0
            printf "%-10s %10.2f %11.1f%%\n", c, speed[c]/count[c], pct
        }
    }
' "$RESULTS" | sort
