#!/bin/bash
# Post-upgrade verification for the Qwen3.8-27B native venv (vLLM 0.33.0).
# Writes a report to data/logs/post-upgrade-check.txt and exits non-zero on failure.
set -uo pipefail

REPO=/root/qwen3/qwen38-27b-rtx3090
PORT=18020
OUT=/root/qwen3/data/logs/post-upgrade-check.txt
FAIL=0

say() { printf '%s\n' "$*" | tee -a "$OUT"; }
check() { # name, expected, actual
  if [ "$2" = "$3" ]; then say "OK    $1: $3"; else say "FAIL  $1: expected $2, got $3"; FAIL=1; fi
}

: > "$OUT"
say "=== post-upgrade check $(date -Is) ==="

# vLLM version in the installed venv
VER=$("$REPO/venv/bin/python" -c 'import vllm;print(vllm.__version__)' 2>/dev/null | tail -n1)
check "vllm version" "0.33.0" "$VER"

# server health
CODE=$(curl -s -o /dev/null -w '%{http_code}' -m 20 "http://127.0.0.1:$PORT/health")
check "vllm /health" "200" "$CODE"

# models list carries the served name
curl -s -m 20 "http://127.0.0.1:$PORT/v1/models" > /tmp/opencode/models.json 2>/dev/null
if grep -q '"qwen3.8-27b"' /tmp/opencode/models.json; then say "OK    /v1/models lists qwen3.8-27b"; else say "FAIL  /v1/models does not list qwen3.8-27b"; FAIL=1; fi

# chat completion end to end
RESP=$(curl -s -m 120 "http://127.0.0.1:$PORT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"Responda em portugues: qual a capital do Brasil? Curto."}],"max_tokens":120}')
printf '%s' "$RESP" > /tmp/opencode/chat.json
if grep -q '"choices"' /tmp/opencode/chat.json; then say "OK    chat completion returned choices"; else say "FAIL  chat completion: $RESP"; FAIL=1; fi

# tool calling
RESP=$(curl -s -m 120 "http://127.0.0.1:$PORT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"Qual o clima em Paris?"}],"tools":[{"type":"function","function":{"name":"get_weather","description":"weather","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],"max_tokens":200}')
printf '%s' "$RESP" > /tmp/opencode/tools.json
if grep -q '"tool_calls"' /tmp/opencode/tools.json; then say "OK    tool calling returned tool_calls"; else say "FAIL  tool calling: $RESP"; FAIL=1; fi

# streaming
if curl -s -N -m 120 "http://127.0.0.1:$PORT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"conte ate 5"}],"stream":true,"max_tokens":60}' \
  | grep -q 'data: \[DONE\]'; then say "OK    streaming ended with [DONE]"; else say "FAIL  streaming did not finish"; FAIL=1; fi

# systemd + playground
say "systemd qwen38-27b: $(systemctl is-active qwen38-27b)"
say "playground container: $(docker ps --filter name=vllm-playground --format '{{.Status}}')"
CODE=$(curl -s -o /dev/null -w '%{http_code}' -m 20 http://localhost:7860/)
check "playground UI" "200" "$CODE"

# disk
df -h / | tail -1 | tee -a "$OUT"
say "=== result: $([ $FAIL -eq 0 ] && echo PASS || echo FAIL) ==="
exit $FAIL
