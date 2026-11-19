#!/bin/bash
# LoRA test window: stops production -> starts the LoRA instance (18021) -> runs the tests ->
# shuts it down -> brings production back. The EXIT/INT/TERM trap ALWAYS brings production back
# (if it was active when the window started), even on error, Ctrl+C or a failed test.
#
#   bash lora/window.sh --plan                       # only prints what it would do (touches nothing)
#   bash lora/window.sh --yes                        # default phases: smoke,regress,speed,ab
#   bash lora/window.sh --yes --phases smoke         # just check that it loads (~5 min)
#   bash lora/window.sh --yes --phases smoke,regress,speed,ab,loop,opencode2
#
# Phases (in this order, whichever are in --phases):
#   smoke     lora/tests/smoke.py (loads? 2 names? does the LoRA change the output? tool call?) -- aborts on failure
#   regress   upstream bench/api_smoke.py on both names + verify.sh (live checks) on PORT=18021
#   speed     lora/tests/speed.py (decode tok/s base vs LoRA, DFlash2 acceptance)
#   ab        lora/tests/agent_ab.py (A/B agentic: lora-nothink, base-nothink, base-think-prod)
#   loop      scripts/loop_stress.py (versioned; port 18021, LS_*): lora off/card, base off/card, base low/prod
#   opencode2 lora/opencode2/run_task.sh on 2 tasks x 2 models (real OpenCode 2.2.7 harness)
# Knobs: AB_REPS (2), AB_TASKS (all), AB_MAX_TURNS (40), LOOP_N (4), BOOT_TIMEOUT (900 s).
# Time estimate in lora/README.md (default ~1.5-2.5 h; smoke alone ~5 min + boots).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
UP="$ROOT/qwen38-27b-rtx3090"
PY="$UP/venv/bin/python"
SERVICE=qwen38-27b
PORT=18021
URL="http://127.0.0.1:$PORT"
PHASES="smoke,regress,speed,ab"
YES=0
PLAN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1 ;;
    --plan) PLAN=1 ;;
    --phases) PHASES="$2"; shift ;;
    --phases=*) PHASES="${1#*=}" ;;
    -h|--help) sed -n 2,22p "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
  shift
done
has() { case ",$PHASES," in *",$1,"*) return 0;; *) return 1;; esac; }

TS=$(date +%Y%m%d-%H%M%S)
RES="$HERE/results/window-$TS"
LOGDIR="$HERE/logs"
LOG="$LOGDIR/lora-$TS.log"
log() { echo "[window $(date +%H:%M:%S)] $*" | tee -a "$RES/window.log" >&2; }

if [ "$PLAN" = 1 ]; then
  cat <<EOF
PLAN (nothing executed):
  1. preflight: adapter (sha256), OpenCode 2 (if opencode2), selftest of the harness, GPUs with no foreign process
  2. systemctl stop $SERVICE           (production down from here on)
  3. wait GPU0/GPU1 < 1 GB (up to 120 s)
  4. setsid bash $HERE/start_lora.sh  >> $LOG   (port $PORT, 127.0.0.1)
  5. wait $URL/health (up to \${BOOT_TIMEOUT:-900} s; aborts if the process dies)
  6. phases: $PHASES  -> $RES/
  7. trap: kill the LoRA instance's process group -> wait GPU free -> systemctl start $SERVICE
     -> wait http://127.0.0.1:18020/health (up to 600 s) -> summary
EOF
  exit 0
fi

mkdir -p "$RES" "$LOGDIR"

# ------------------------------------------------------------------ preflight (touches no GPU)
log "preflight"
[ -x "$PY" ] || { log "no venv at $PY"; exit 1; }
DRY_RUN=1 bash "$HERE/start_lora.sh" > "$RES/argv.txt" 2> "$RES/argv.err" || { log "start_lora.sh dry run failed: see $RES/argv.err"; exit 1; }
SHA=$(sha256sum "$HERE/adapters/opencode-adapted/adapter_model.safetensors" | cut -d' ' -f1)
grep -q "LORA_SHA256=$SHA" "$HERE/lora.env" || { log "adapter sha256 does not match lora.env"; exit 1; }
python3 -I "$HERE/tests/agent_ab.py" --selftest > "$RES/selftest.log" 2>&1 || { log "agent_ab --selftest failed"; exit 1; }
if has opencode2 && [ ! -x "$HERE/opencode2/node_modules/.bin/opencode" ]; then log "OpenCode 2 not installed"; exit 1; fi
OTHERS=$(nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader | grep -v -i 'VLLM' || true)
[ -z "$OTHERS" ] || { log "foreign process on the GPU (stop it first): $OTHERS"; exit 1; }
WAS_ACTIVE=0
systemctl is-active --quiet "$SERVICE" && WAS_ACTIVE=1
if [ "$YES" != 1 ]; then
  echo "This STOPS production ($SERVICE, port 18020) during the test (phases: $PHASES)."
  echo "Clients (OpenCode, OpenClaw, LiteLLM) will get errors until the end. Type STOP to continue:"
  read -r ans; [ "$ans" = "STOP" ] || { echo "cancelled"; exit 1; }
fi

gpu_free() {  # waits until every GPU is < 1 GB, up to $1 s
  local t=0
  while [ "$t" -lt "$1" ]; do
    if nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '$1>1000{b=1} END{exit b}'; then return 0; fi
    sleep 5; t=$((t + 5))
  done
  return 1
}

LORA_PGID=""
cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  log "cleanup (rc=$rc)"
  if [ -n "$LORA_PGID" ] && kill -0 "$LORA_PGID" 2>/dev/null; then
    log "shutting down the LoRA instance (pgid $LORA_PGID)"
    kill -TERM -- "-$LORA_PGID" 2>/dev/null
    for _ in $(seq 1 60); do kill -0 "$LORA_PGID" 2>/dev/null || break; sleep 1; done
    kill -KILL -- "-$LORA_PGID" 2>/dev/null || true
  fi
  # orphaned vLLM workers of the instance (production is stopped, so any vllm serve on :18021 is ours)
  pkill -TERM -f "vllm serve .* --port $PORT" 2>/dev/null || true
  gpu_free 120 || log "WARNING: GPU still occupied after 120 s; the unit's ExecStartPre waits 2 more minutes"
  if [ "$WAS_ACTIVE" = 1 ]; then
    log "bringing production back: systemctl start $SERVICE"
    systemctl start "$SERVICE" || log "ERROR: systemctl start failed -- run: systemctl start $SERVICE"
    for _ in $(seq 1 120); do curl -sf -o /dev/null http://127.0.0.1:18020/health && break; sleep 5; done
    if curl -sf -o /dev/null http://127.0.0.1:18020/health; then log "production OK (18020 /health 200)"
    else log "WARNING: production still has no /health after 600 s -- check: make status / make logs"; fi
  fi
  log "results in $RES ; instance log in $LOG"
  exit $rc
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# ------------------------------------------------------------------ stop production, start LoRA
if [ "$WAS_ACTIVE" = 1 ]; then
  log "systemctl stop $SERVICE"
  systemctl stop "$SERVICE" || { log "failed to stop production"; exit 1; }
fi
gpu_free 120 || { log "GPU did not free up in 120 s"; exit 1; }
log "starting the LoRA instance -> $LOG"
setsid bash "$HERE/start_lora.sh" >> "$LOG" 2>&1 < /dev/null &
LORA_PGID=$!
T0=$(date +%s)
until curl -sf -o /dev/null "$URL/health"; do
  kill -0 "$LORA_PGID" 2>/dev/null || { log "LoRA instance DIED during boot: tail of $LOG"; tail -40 "$LOG" | tee -a "$RES/window.log" >&2; exit 1; }
  [ $(( $(date +%s) - T0 )) -lt "${BOOT_TIMEOUT:-900}" ] || { log "boot timeout"; exit 1; }
  sleep 5
done
log "LoRA instance up in $(( $(date +%s) - T0 )) s"
grep -a -E "KV cache|Available KV|LoRA|lora|graph capturing|Maximum concurrency" "$LOG" | tail -30 > "$RES/boot-highlights.log"
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv > "$RES/gpu-after-boot.csv"
SINCE=$(date +"%m-%d %H:%M:%S")

# ------------------------------------------------------------------ phases
export LORA_URL="$URL"
if has smoke; then
  log "phase smoke"
  python3 -I "$HERE/tests/smoke.py" --url "$URL" --out "$RES/smoke.json" 2>&1 | tee "$RES/smoke.log"
  [ "${PIPESTATUS[0]}" = 0 ] || { log "SMOKE FAILED -- aborting (production will be brought back)"; exit 1; }
fi
if has regress; then
  log "phase regress (upstream api_smoke + verify.sh on 18021)"
  ( cd "$UP" && PORT=$PORT "$PY" bench/api_smoke.py ) > "$RES/api_smoke-base.log" 2>&1; log "api_smoke base rc=$?"
  ( cd "$UP" && PORT=$PORT VLLM_MODEL=opencode-adapted "$PY" bench/api_smoke.py ) > "$RES/api_smoke-lora.log" 2>&1; log "api_smoke lora rc=$?"
  ( cd "$UP" && PORT=$PORT bash verify.sh ) > "$RES/verify.log" 2>&1; log "verify.sh rc=$? (see $RES/verify.log)"
fi
if has speed; then
  log "phase speed"
  python3 -I "$HERE/tests/speed.py" --url "$URL" --reps 3 --out "$RES/speed.json" > "$RES/speed.log" 2>&1; log "speed rc=$?"
fi
if has ab; then
  log "phase ab (this is the long one)"
  python3 -I "$HERE/tests/agent_ab.py" --url "$URL" --reps "${AB_REPS:-2}" --max-turns "${AB_MAX_TURNS:-40}" \
    ${AB_TASKS:+--tasks "$AB_TASKS"} ${AB_ARMS:+--arms "$AB_ARMS"} ${AB_PREFILL:+--prefill-tokens "$AB_PREFILL"} \
    --out "$RES/ab" 2>&1 | tee "$RES/ab.log"; log "ab rc=${PIPESTATUS[0]}"
fi
if has loop; then
  log "phase loop"
  # scripts/loop_stress.py (versioned, the one from the 2026-11-19 INT4 x INT8 A/B), port as 4th argument;
  # LS_* switch model/thinking/sampling. LS_PARALLEL=1 keeps the per-arm acceptance readable in the log.
  LS_MODEL=opencode-adapted LS_THINKING=off LS_SAMPLING=card LS_PARALLEL=1 python3 -I "$ROOT/scripts/loop_stress.py" \
    "${LOOP_N:-4}" lora-off-card "$RES/loop-lora-off-card.json" "$PORT" > "$RES/loop-lora.log" 2>&1
  LS_MODEL=qwen3.8-27b LS_THINKING=off LS_SAMPLING=card LS_PARALLEL=1 python3 -I "$ROOT/scripts/loop_stress.py" \
    "${LOOP_N:-4}" base-off-card "$RES/loop-base-off-card.json" "$PORT" > "$RES/loop-base-off.log" 2>&1
  # control identical to the A/B that chose production's model (thinking on, effort low, protections off)
  LS_PARALLEL=1 python3 -I "$ROOT/scripts/loop_stress.py" \
    "${LOOP_N:-4}" base-low-prod "$RES/loop-base-low.json" "$PORT" > "$RES/loop-base-low.log" 2>&1
  log "loop done: $(grep -h 'RESUMO' "$RES"/loop-*.log | tr '\n' ' ')"
fi
if has opencode2; then
  log "phase opencode2 (real harness)"
  for t in slugify-bug inventory-multi; do
    for m in opencode-adapted qwen3.8-27b; do
      OC_BASEURL="$URL/v1" bash "$HERE/opencode2/run_task.sh" "$t" "$m" "$RES/opencode2-$m-$t" >> "$RES/opencode2.log" 2>&1
    done
  done
  log "opencode2 done: $(cat "$RES"/opencode2-*/result.json 2>/dev/null | tr '\n' ' ')"
fi
python3 -I "$HERE/tests/spec_log.py" "$LOG" --since "$SINCE" > "$RES/spec_log.txt" 2>&1
grep -a -E "Traceback|ERROR|CUDA error|out of memory" "$LOG" | tail -20 > "$RES/log-errors.txt"
log "phases complete"
# the EXIT trap shuts down the instance and brings production back
