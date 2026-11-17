#!/bin/bash
# Concurrency sanity on the running vLLM 0.33.0 server: 8 parallel chat requests,
# checks all 8 succeed and reports aggregate throughput.
# Writes to /root/qwen3/data/logs/concurrency-check.txt.
set -uo pipefail

PORT=${PORT:-18020}
URL="http://127.0.0.1:$PORT/v1/chat/completions"
N=${N:-8}
OUT=/root/qwen3/data/logs/concurrency-check.txt
: > "$OUT"

TMP=$(mktemp -d)
start=$(date +%s.%N)
for i in $(seq 1 "$N"); do
  (
    body=$(curl -s -m 300 "$URL" -H 'Content-Type: application/json' \
      -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"Escreva uma frase curta sobre o numero '"$i"'."}],"max_tokens":200}')
    printf '%s' "$body" > "$TMP/resp.$i"
  ) &
done
wait
end=$(date +%s.%N)

ok=0
for i in $(seq 1 "$N"); do
  if grep -q '"choices"' "$TMP/resp.$i" 2>/dev/null; then
    ok=$((ok + 1))
  else
    echo "FAIL request $i: $(head -c 200 "$TMP/resp.$i")" >> "$OUT"
  fi
done

tok=$(grep -ho '"completion_tokens":[0-9]*' "$TMP"/resp.* 2>/dev/null | grep -o '[0-9]*' | awk '{s+=$1} END {print s+0}')
elapsed=$(awk -v a="$start" -v b="$end" 'BEGIN {printf "%.2f", b-a}')
{
  echo "=== concurrency check $(date -Is) ==="
  echo "requests: $N   ok: $ok   wall: ${elapsed}s"
  echo "completion tokens total: ${tok:-0}"
  if [ "${tok:-0}" -gt 0 ]; then
    echo "aggregate decode tok/s: $(awk -v t="$tok" -v e="$elapsed" 'BEGIN {printf "%.2f", t/e}')"
  fi
  echo "result: $([ "$ok" -eq "$N" ] && echo PASS || echo FAIL)"
} | tee -a "$OUT"
rm -rf "$TMP"
[ "$ok" -eq "$N" ]
