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

# ── Recupera contexto util (janela e 106496, saida maxima e 8192) ────────────
set_cfg agents.defaults.compaction.reserveTokensFloor 12288 \
    "Era 20000. Piso de reserva; 12288 = 8192 de saida + folga p/ o resumo."

set_cfg agents.defaults.compaction.reserveTokens 12288 \
    "Era 20000 — reservava 20k para uma saida que nunca passa de 8192."

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
