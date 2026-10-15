# ---------------------------------------------------------------------------
# OpenClaude -> Qwen3.8-27B local  (bash/zsh, Linux ou WSL)
# ---------------------------------------------------------------------------
# Mesmo objetivo da versao PowerShell: digitar apenas `openclaude` e ter o
# bypassPermissions disponivel no Shift+Tab, sem comecar nele.
#
# Instalacao: cole no ~/.bashrc (ou ~/.zshrc) e recarregue:
#     source ~/.bashrc
# ---------------------------------------------------------------------------

# Aqui alias basta, porque alias de shell aceita argumentos fixos.
alias openclaude='command openclaude --allow-dangerously-skip-permissions'

# Aponta para o servidor deste repo sem precisar de --provider-env-file.
# Comente este bloco se preferir usar o settings.json ou /provider.
export CLAUDE_CODE_USE_OPENAI=1
export OPENAI_BASE_URL=http://100.102.127.47:18020/v1
export OPENAI_MODEL=qwen3.8-27b
export OPENAI_API_KEY=vllm-local-sem-auth
