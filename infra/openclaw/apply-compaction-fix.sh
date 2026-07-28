#!/usr/bin/env bash
# Corrige a compactacao destrutiva do OpenClaw (causa do loop de re-anuncio).
# Rodar NA MAQUINA DO OPENCLAW. Ver HIPOTESE-09 para a evidencia.
#
#   Antes: compactava aos ~53k e deixava ~2k -> o modelo perdia a memoria de que
#          ja tinha respondido e re-anunciava a mesma coisa a cada turno.
#
# Uso:  ./apply-compaction-fix.sh --dry-run   (mostra o que mudaria)
#       ./apply-compaction-fix.sh             (aplica de verdade)

set -euo pipefail

DRY=""
[ "${1:-}" = "--dry-run" ] && DRY="--dry-run"

set_cfg() {
    local path="$1" value="$2" why="$3"
    echo ""
    echo "── $path = $value"
    echo "   $why"
    openclaw config set "$path" "$value" --strict-json $DRY
}

echo "════════════════════════════════════════════════════════════"
echo "  Fix de compactacao do OpenClaw ${DRY:+(DRY-RUN)}"
echo "════════════════════════════════════════════════════════════"

# ── O FIX PRINCIPAL ──────────────────────────────────────────────────────────
# Sem isto o loop volta na proxima compactacao, mesmo com os outros dois certos.
set_cfg agents.defaults.compaction.keepRecentTokens 32000 \
    "CRITICO: era 5000 -> apos compactar jogava fora quase todo o contexto."

# ── Teto de saida: 8192 nao cabia um HTML inteiro ────────────────────────────
# Sintoma: stopReason=length -> "Agent couldn't generate a response" no Telegram.
# Precisa bater com N_PREDICT=16384 no .env do llama-server.
set_cfg models.providers.litellm.models[0].maxTokens 16384 \
    "Era 8192 — o modelo era cortado no meio da escrita do arquivo."

# ── Reserva de saida (janela 106496; entrada util = 106496 - 20480 = 86016) ──
set_cfg agents.defaults.compaction.reserveTokensFloor 20480 \
    "Piso de reserva: 16384 de saida + folga para o resumo da compactacao."

set_cfg agents.defaults.compaction.reserveTokens 20480 \
    "Tem de ser >= maxTokens, senao a saida nao cabe na reserva."

# ── Opcional (cosmetico neste backend) ───────────────────────────────────────
# O llama.cpp so honra reasoning_effort='none'; low/medium/high nao mudam a
# profundidade do raciocinio. Quem controla isso e o REASONING_BUDGET no servidor.
# Serve so para deixar o default explicito em vez de implicito.
set_cfg agents.defaults.thinkingDefault '"medium"' \
    "Opcional: torna o default explicito. Nao muda profundidade neste backend."

echo ""
echo "════════════════════════════════════════════════════════════"
if [ -n "$DRY" ]; then
    echo "  DRY-RUN — nada foi alterado."
    echo "  Rode sem --dry-run para aplicar."
else
    echo "  Aplicado. Validando..."
    echo "════════════════════════════════════════════════════════════"
    openclaw config validate || openclaw doctor
    echo ""
    echo "  Valores agora:"
    openclaw config get agents.defaults.compaction
    echo ""
    echo "  Reinicie o gateway para carregar a config nova."
fi
echo "════════════════════════════════════════════════════════════"
