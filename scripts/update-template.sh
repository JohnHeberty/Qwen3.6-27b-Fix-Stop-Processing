#!/usr/bin/env bash
# scripts/update-template.sh — Baixa e aplica o template mais recente do froggeric
# Executa automaticamente a aplicação ao GGUF

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Carregar variáveis do .env
[ -f "$PROJECT_ROOT/.env" ] && set -a && source "$PROJECT_ROOT/.env" && set +a

VENV="$PROJECT_ROOT/.venv"
TEMPLATE_HF_REPO="${TEMPLATE_HF_REPO:-froggeric/Qwen-Fixed-Chat-Templates}"
TEMPLATE_DIR="$PROJECT_ROOT/data/templates"
TEMPLATE_FILE="${TEMPLATE_FILE:-$TEMPLATE_DIR/chat_template.jinja}"

export HF_TOKEN="${HF_TOKEN:-${HUGGINGFACE_TOKEN:-}}"

GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[AVISO]${NC} $*"; }
err()  { echo -e "${RED}[ERRO]${NC} $*"; exit 1; }

echo ""
echo "================================================"
echo "  Atualizando template Qwen (froggeric)"
echo "================================================"
echo ""

# ── Validações ─────────────────────────────────────────────────────────────────
[ -d "$VENV" ] || err "Virtualenv não encontrado em $VENV. Execute: make setup"
source "$VENV/bin/activate"

if [ -z "$HF_TOKEN" ]; then
    warn "HUGGINGFACE_TOKEN não definido em .env"
    warn "Tentando download público (pode falhar para repos privados)..."
else
    ok "HuggingFace token carregado"
fi

echo "Repositório : $TEMPLATE_HF_REPO"
echo "Destino     : $TEMPLATE_DIR"
echo ""

# ── Download do repositório inteiro ────────────────────────────────────────────
echo "Baixando repositório do HuggingFace..."
"$VENV/bin/hf" download "$TEMPLATE_HF_REPO" \
    --local-dir "$TEMPLATE_DIR" \
    --repo-type dataset 2>/dev/null || \
"$VENV/bin/hf" download "$TEMPLATE_HF_REPO" \
    --local-dir "$TEMPLATE_DIR" 2>/dev/null || \
    err "Falha ao baixar $TEMPLATE_HF_REPO. Verifique token e conectividade."

ok "Repositório atualizado"

# ── Detectar versão ────────────────────────────────────────────────────────────
VERSION="desconhecida"
if [ -f "$TEMPLATE_DIR/README.md" ]; then
    VERSION=$(head -30 "$TEMPLATE_DIR/README.md" | grep -oP "v\d+" | head -1 || echo "desconhecida")
    if [ -z "$VERSION" ]; then
        VERSION=$(head -30 "$TEMPLATE_DIR/README.md" | grep -oP "\*\*Version:\*\* (v\d+)" | grep -oP "v\d+" || echo "desconhecida")
    fi
fi
echo ""
echo "Versão detectada: $VERSION"
echo ""

# ── Aplicar template ao GGUF ───────────────────────────────────────────────────
echo "Aplicando template ao modelo GGUF..."
if [ -f "$TEMPLATE_FILE" ]; then
    "$VENV/bin/python" "$PROJECT_ROOT/src/fix_template.py" \
        --model-dir "$PROJECT_ROOT/data/models" \
        --template "$TEMPLATE_FILE" || \
        err "Falha ao aplicar template"
    ok "Template $VERSION aplicado com sucesso"
else
    warn "Template não encontrado em $TEMPLATE_FILE"
    warn "Execute novamente após confirmar o download."
fi

echo ""
echo "================================================"
echo "  ✓ Próximos passos:"
echo "  make restart    (reinicia servidor com novo template)"
echo "================================================"
echo ""
