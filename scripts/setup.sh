#!/usr/bin/env bash
# scripts/setup.sh — Prepara o servidor llama-cpp-python para o Qwen3.6 27B GGUF
# Executar UMA VEZ como usuario comum (nao root)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Carregar variaveis do .env (se existir)
[ -f "$PROJECT_ROOT/.env" ] && set -a && source "$PROJECT_ROOT/.env" && set +a

VENV="$PROJECT_ROOT/.venv"
MODEL_DIR="${MODEL_DIR:-$PROJECT_ROOT/data/models}"
MODEL_HF="${MODEL_HF:-HauhauCS/Qwen3.6-27B-Uncensored-HauhauCS-Aggressive}"
MODEL_FILE="${MODEL_FILE:-Qwen3.6-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf}"
TEMPLATE_FILE="${TEMPLATE_FILE:-data/templates/archive/qwen3.6/chat_template-v18.jinja}"

export HF_TOKEN="${HF_TOKEN:-${HUGGINGFACE_TOKEN:-}}"

GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[AVISO]${NC} $*"; }
err()  { echo -e "${RED}[ERRO]${NC} $*"; exit 1; }

echo ""
echo "================================================"
echo "  Setup: llama-cpp-python + Qwen3.6 27B GGUF"
echo "  Ollama nao e tocado — segue em :11434"
echo "  llama-cpp-python servira em :8000"
echo "================================================"
echo ""

# ── 1. Estrutura de pastas ─────────────────────────────────────────────────────

echo "[1/5] Verificando estrutura de pastas..."
mkdir -p "$MODEL_DIR" \
         "$PROJECT_ROOT/data/templates" \
         "$PROJECT_ROOT/data/logs" \
         "$PROJECT_ROOT/data/backups"
ok "Pastas verificadas em $PROJECT_ROOT/data/"

# ── 2. Virtualenv ──────────────────────────────────────────────────────────────

echo ""
echo "[2/5] Verificando virtualenv..."

python3 --version &>/dev/null || err "Python3 nao encontrado. Instale: sudo apt install python3 python3-venv"

if [ ! -d "$VENV" ]; then
    echo "      Criando virtualenv em $VENV ..."
    python3 -m venv "$VENV"
    ok "Virtualenv criado"
else
    ok "Virtualenv ja existe: $VENV"
fi

source "$VENV/bin/activate"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"

# ── 3. Instalar llama-cpp-python com CUDA ─────────────────────────────────────

echo ""
echo "[3/5] Instalando llama-cpp-python com CUDA..."

if command -v nvidia-smi &>/dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    ok "GPU detectada: $GPU_NAME"
else
    warn "nvidia-smi nao encontrado — llama-cpp-python requer GPU NVIDIA"
fi

if "$PYTHON" -c "import llama_cpp" &>/dev/null 2>&1; then
    ok "llama-cpp-python ja instalado"
else
    echo "      Instalando llama-cpp-python com CUDA 12.8..."
    "$PIP" install --quiet "llama-cpp-python[server]" \
        --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu128
    ok "llama-cpp-python instalado"
fi

if ! "$PYTHON" -c "import huggingface_hub" &>/dev/null; then
    "$PIP" install --quiet huggingface-hub
fi
ok "huggingface-hub OK"

if ! "$PYTHON" -c "import gguf" &>/dev/null; then
    "$PIP" install --quiet gguf
fi
ok "gguf OK"

# ── 4. Baixar o modelo GGUF ────────────────────────────────────────────────────

echo ""
echo "[4/5] Baixando modelo $MODEL_HF ..."
echo "      Arquivo: $MODEL_FILE"
echo "      Destino: $MODEL_DIR"
echo ""

if [ -f "$MODEL_DIR/$MODEL_FILE" ]; then
    ok "Modelo ja existe — pulando download"
else
    "$VENV/bin/hf" download "$MODEL_HF" "$MODEL_FILE" \
        --local-dir "$MODEL_DIR"

    [ -f "$MODEL_DIR/$MODEL_FILE" ] \
        && ok "Modelo baixado com sucesso" \
        || err "Download falhou — verifique conexao e espaco em disco"
fi

# ── 5. Aplicar template v18 no GGUF ───────────────────────────────────────────

echo ""
echo "[5/5] Aplicando template v18 no GGUF..."

TEMPLATE_ABS="$PROJECT_ROOT/$TEMPLATE_FILE"
FIX_SCRIPT="$PROJECT_ROOT/src/fix_template.py"

if [ ! -f "$TEMPLATE_ABS" ]; then
    warn "Template nao encontrado: $TEMPLATE_ABS"
    warn "Execute manualmente: $PYTHON src/fix_template.py"
elif [ -f "$FIX_SCRIPT" ]; then
    "$PYTHON" "$FIX_SCRIPT" \
        --model-dir "$MODEL_DIR" \
        --template  "$TEMPLATE_ABS"
else
    warn "fix_template.py nao encontrado"
fi

# ── Resumo ─────────────────────────────────────────────────────────────────────

echo ""
echo "================================================"
echo -e "  ${GREEN}Setup concluido!${NC}"
echo "================================================"
echo ""
echo "Iniciar o servidor:"
echo "  make start"
echo "  ou: $PROJECT_ROOT/scripts/start-server.sh"
echo ""
echo "Testar depois de subir:"
echo "  curl http://localhost:8000/health"
echo "  make test"
echo ""
echo "Ollama continua em: http://localhost:11434 (intocado)"
echo "llama-cpp-python em: http://localhost:8000/v1"
echo ""
