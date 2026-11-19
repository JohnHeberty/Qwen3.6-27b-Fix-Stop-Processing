#!/bin/bash
# Sobe UMA instância de teste do vLLM com o adaptador LoRA opencode-adapted, na porta 18021,
# reaproveitando o launcher do upstream (single-user/start_qwen.sh) inteiro: mesmo modelo da
# produção (base W4A16, lm_head INT8, MODEL= no lora.env), TP=2, DFlash2 (7 drafts,
# probabilistic), CTX=fast bf16, 142080 de contexto,
# prefix caching, parsers, patch local de defaults. Serve DOIS nomes:
#   qwen3.8-27b       -> modelo base (sem LoRA)
#   opencode-adapted  -> base + adaptador
#
# Uso:
#   bash lora/start_lora.sh             # foreground (Ctrl+C derruba)
#   DRY_RUN=1 bash lora/start_lora.sh   # só imprime o argv do vLLM (sem GPU, sem guardas)
#
# Recusa rodar se a produção (systemd qwen38-27b) estiver ativa ou se alguma GPU tiver
# > 1 GB em uso: NÃO cabem duas instâncias do 27B nas 2x 3090. Para a janela de teste
# completa (para produção -> testa -> religa produção, com trap) use lora/window.sh.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
UP="$ROOT/qwen38-27b-rtx3090"
SERVICE=qwen38-27b
DRY=${DRY_RUN:-0}

die() { echo "[start_lora] ERRO: $*" >&2; exit 1; }

# --- Config: produção (só leitura) + overrides do teste ------------------------------
[ -f "$ROOT/.env" ] || die "não achei $ROOT/.env"
[ -f "$HERE/lora.env" ] || die "não achei $HERE/lora.env"
# Overrides de linha de comando (ex.: GPU_UTIL=0.66 bash lora/start_lora.sh) vencem os
# dois arquivos: guardamos antes de carregar.
_CLI_GPU_UTIL=${GPU_UTIL:-}; _CLI_PORT=${PORT:-}; _CLI_HOST=${HOST:-}
set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
# shellcheck disable=SC1091
source "$HERE/lora.env"
set +a
[ -n "$_CLI_GPU_UTIL" ] && export GPU_UTIL=$_CLI_GPU_UTIL
[ -n "$_CLI_PORT" ] && export PORT=$_CLI_PORT
[ -n "$_CLI_HOST" ] && export HOST=$_CLI_HOST

[ "$PORT" != 18020 ] || die "PORT=18020 é a produção; a instância LoRA usa outra porta (18021)."
case "$LORA_PATH" in *" "*) die "LORA_PATH não pode ter espaços (EXTRA_ARGS é expandido sem aspas)";; esac
case " $EXTRA_ARGS " in *" --enable-lora "*) ;; *) die "EXTRA_ARGS do lora.env sem --enable-lora";; esac
[ "${DFLASH_TOKENS:-7}" -le 7 ] || die "DFLASH_TOKENS>7 liga o verify adaptativo do DFlash2, não validado com LoRA (ver lora.env)."

# --- Adaptador: presença e integridade --------------------------------------------
for f in adapter_config.json adapter_model.safetensors; do
  [ -f "$LORA_PATH/$f" ] || die "falta $LORA_PATH/$f (baixe: ver lora/README.md, seção Download)"
done
SZ=$(stat -c %s "$LORA_PATH/adapter_model.safetensors")
[ "$SZ" = "$LORA_SIZE" ] || die "adapter_model.safetensors com $SZ bytes, esperado $LORA_SIZE"
if [ "${VERIFY_SHA:-1}" = 1 ] && [ "$DRY" != 1 ]; then
  echo "[start_lora] conferindo sha256 do adaptador (~2 s)..."
  SHA=$(sha256sum "$LORA_PATH/adapter_model.safetensors" | cut -d' ' -f1)
  [ "$SHA" = "$LORA_SHA256" ] || die "sha256 do adaptador não confere ($SHA)"
fi

# --- Guardas (puladas no DRY_RUN, que não toca a GPU) ------------------------------
if [ "$DRY" != 1 ]; then
  if systemctl is-active --quiet "$SERVICE"; then
    cat >&2 <<EOF
[start_lora] RECUSADO: a produção ($SERVICE, porta 18020) está ativa.
  Não cabem duas instâncias do 27B nas 2x RTX 3090 (~16 de 24 GB por GPU já em uso).
  Faça a janela de teste completa, que para a produção e SEMPRE a religa no fim:
      bash $HERE/window.sh            # ver lora/README.md
  ou, manualmente:
      systemctl stop $SERVICE && bash $HERE/start_lora.sh
      ...testes...  (Ctrl+C)  && systemctl start $SERVICE
EOF
    exit 2
  fi
  while IFS=, read -r idx used; do
    used=${used// /}
    if [ "${used:-0}" -gt 1000 ]; then
      echo "[start_lora] RECUSADO: GPU $idx com ${used} MiB em uso (> 1 GB). Algo ainda segura VRAM:" >&2
      nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader >&2 || true
      echo "  (Ollama? 'ollama ps' / 'ollama stop <modelo>'; playground? 'make playground-down')" >&2
      exit 2
    fi
  done < <(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits)
  if (exec 3<>/dev/tcp/127.0.0.1/"$PORT") 2>/dev/null; then
    die "a porta $PORT já está em uso (outra instância de teste?)"
  fi
fi

# --- Monta o EXTRA_ARGS final e entrega para o launcher do upstream ------------------
export EXTRA_ARGS="$EXTRA_ARGS --lora-modules ${LORA_NAME}=${LORA_PATH}"
# Limpa variáveis que só fazem sentido aqui, para não confundir o launcher.
unset LORA_SHA256 LORA_SIZE _CLI_GPU_UTIL _CLI_PORT _CLI_HOST

echo "[start_lora] porta=$PORT host=$HOST GPU_UTIL=$GPU_UTIL SPEC=${SPEC:-} DFLASH_TOKENS=${DFLASH_TOKENS:-} MAX_LEN=${DFLASH_MAX_LEN:-}" >&2
echo "[start_lora] nomes servidos: qwen3.8-27b (base) e ${LORA_NAME} (LoRA ${LORA_PATH})" >&2
if [ "$DRY" = 1 ]; then
  export PRINT_ARGV=1
fi
cd "$UP" || die "não achei $UP"
exec bash "$UP/single-user/start_qwen.sh"
