#!/usr/bin/env bash
# ── Monitor de tamanho da pasta de captura (vLLM) ─────────────────────────
# Roda em background. Verifica a cada 30 min se data/logs/capture/passou de
# MAX_MB. Se sim, apaga os arquivos mais antigos até caber.
# Gerenciado pelo Makefile via PID em monitor.pid (capture-on/off).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CAPTURE_DIR="$PROJECT_ROOT/data/logs/capture"
PID_FILE="$CAPTURE_DIR/monitor.pid"
LOG_FILE="$CAPTURE_DIR/monitor.log"

MAX_MB="${CAPTURE_MAX_MB:-500}"
CHECK_INTERVAL=1800  # 30 minutos

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# Garante diretorios
mkdir -p "$CAPTURE_DIR"
echo $$ > "$PID_FILE"

log "Monitor iniciado (PID $$) — limite: ${MAX_MB}MB, intervalo: ${CHECK_INTERVAL}s"

cleanup() {
    log "Monitor encerrado (PID $$)"
    rm -f "$PID_FILE"
    exit 0
}

trap cleanup SIGTERM SIGINT SIGHUP

while true; do
    # Verifica se o capture ainda está ativo
    if ! grep -q '^CAPTURE_LOG=true' "$PROJECT_ROOT/.env" 2>/dev/null; then
        log "CAPTURE_LOG desligado — encerrando monitor."
        cleanup
    fi

    # Tamanho atual em MB
    if [ -d "$CAPTURE_DIR" ]; then
        # Exclui monitor.pid e monitor.log do cálculo
        CURRENT_MB=$(du -sm "$CAPTURE_DIR" 2>/dev/null | awk '{print $1}')

        if [ "$CURRENT_MB" -gt "$MAX_MB" ] 2>/dev/null; then
            log "CAPTURA ACIMA DO LIMITE: ${CURRENT_MB}MB > ${MAX_MB}MB — iniciando limpeza..."

            # Remove arquivos .log mais antigos até caber
            while [ "$(du -sm "$CAPTURE_DIR" 2>/dev/null | awk '{print $1}')" -gt "$MAX_MB" ]; do
                OLDEST=$(find "$CAPTURE_DIR" -maxdepth 1 -name '*.log' -type f ! -name 'monitor.*' -printf '%T+ %p\n' 2>/dev/null | sort | head -1 | awk '{print $2}')
                if [ -z "$OLDEST" ]; then
                    break
                fi
                FILE_SIZE=$(du -sm "$OLDEST" 2>/dev/null | awk '{print $1}')
                log "Removendo: $(basename "$OLDEST") (${FILE_SIZE}MB)"
                rm -f "$OLDEST"
            done

            FINAL_MB=$(du -sm "$CAPTURE_DIR" 2>/dev/null | awk '{print $1}')
            log "Limpeza concluida — tamanho atual: ${FINAL_MB}MB"
        fi
    fi

    sleep "$CHECK_INTERVAL"
done
