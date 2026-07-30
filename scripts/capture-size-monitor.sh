#!/usr/bin/env bash
# ── Monitor de tamanho da pasta de captura ──────────────────────────────────
# Roda em background. Verifica a cada 5 min se data/logs/capture/prompts
# passou de MAX_MB. Se sim, apaga as pastas de data mais antigas até caber.
# Gerenciado pelo Makefile via PID em monitor.pid (capture-on/off).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CAPTURE_PROMPTS="$PROJECT_ROOT/data/logs/capture/prompts"
PID_FILE="$PROJECT_ROOT/data/logs/capture/monitor.pid"
LOG_FILE="$PROJECT_ROOT/data/logs/capture/monitor.log"

MAX_MB="${CAPTURE_MAX_MB:-500}"
CHECK_INTERVAL=1800  # 30 minutos

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# Garante diretorios
mkdir -p "$CAPTURE_PROMPTS"
echo $$ > "$PID_FILE"

log "Monitor iniciado (PID $$) — limite: ${MAX_MB}MB, intervalo: ${CHECK_INTERVAL}s"

cleanup() {
    log "Monitor encerrado (PID $$)"
    rm -f "$PID_FILE"
    exit 0
}

trap cleanup SIGTERM SIGINT SIGHUP

while true; do
    # Verifica se o capture ainda esta ativo
    if ! grep -q '^CAPTURE_LOG=true' "$PROJECT_ROOT/.env" 2>/dev/null; then
        log "CAPTURE_LOG desligado — encerrando monitor."
        cleanup
    fi

    # Tamanho atual em MB
    if [ -d "$CAPTURE_PROMPTS" ]; then
        CURRENT_MB=$(du -sm "$CAPTURE_PROMPTS" 2>/dev/null | awk '{print $1}')

        if [ "$CURRENT_MB" -gt "$MAX_MB" ] 2>/dev/null; then
            log "CAPTURA ACIMA DO LIMITE: ${CURRENT_MB}MB > ${MAX_MB}MB — iniciando limpeza..."

            # Remove pastas de data mais antigas ate caber
            # Pastas tem formato YYYY-MM-DD
            while [ "$(du -sm "$CAPTURE_PROMPTS" 2>/dev/null | awk '{print $1}')" -gt "$MAX_MB" ]; do
                OLDEST_DIR=$(ls -1d "$CAPTURE_PROMPTS"/20* 2>/dev/null | head -1)
                if [ -z "$OLDEST_DIR" ]; then
                    break
                fi
                DIR_SIZE=$(du -sm "$OLDEST_DIR" 2>/dev/null | awk '{print $1}')
                log "Removendo: $(basename "$OLDEST_DIR") (${DIR_SIZE}MB)"
                rm -rf "$OLDEST_DIR"
            done

            FINAL_MB=$(du -sm "$CAPTURE_PROMPTS" 2>/dev/null | awk '{print $1}')
            log "Limpeza concluida — tamanho atual: ${FINAL_MB}MB"
        fi
    fi

    sleep "$CHECK_INTERVAL"
done
