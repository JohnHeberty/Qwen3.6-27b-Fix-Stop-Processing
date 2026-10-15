# ---------------------------------------------------------------------------
# OpenClaude -> Qwen3.8-27B local  (perfil do PowerShell, Windows)
# ---------------------------------------------------------------------------
# Objetivo: digitar apenas `openclaude` e ter o bypassPermissions DISPONIVEL
# no ciclo do Shift+Tab, sem comecar nele.
#
# Instalacao (PowerShell):
#     notepad $PROFILE          # cria se nao existir: New-Item -Type File -Force $PROFILE
# e cole o conteudo abaixo. Depois: . $PROFILE   (ou abra um terminal novo)
#
# Por que uma funcao e nao Set-Alias: alias do PowerShell nao aceita
# argumentos fixos. A funcao sobrepoe o nome `openclaude` e repassa o resto.
# ---------------------------------------------------------------------------

function openclaude {
    # --allow-dangerously-skip-permissions ADICIONA bypassPermissions ao ciclo
    # do Shift+Tab sem ativar: a sessao comeca no defaultMode do settings.json
    # (acceptEdits) e o ciclo fica
    #     default -> acceptEdits -> plan -> bypassPermissions
    & "$env:APPDATA\npm\openclaude.ps1" --allow-dangerously-skip-permissions @args
}

# O caminho absoluto evita recursao: sem ele, `openclaude` dentro da funcao
# chamaria a propria funcao de novo. Instalacao via npm expoe tres shims em
# %APPDATA%\npm (openclaude.ps1, .cmd e sem extensao); no PowerShell o .ps1
# tem precedencia. Confirme o seu com:
#     Get-Command openclaude -All | Format-List Name, Source

# ---------------------------------------------------------------------------
# Variante: comecar em plan mode (nada executa ate voce avancar o ciclo)
# ---------------------------------------------------------------------------
# function openclaude-plan {
#     & "$env:APPDATA\npm\openclaude.ps1" --allow-dangerously-skip-permissions --permission-mode plan @args
# }

# ---------------------------------------------------------------------------
# Variante: comecar JA em bypass (sem rede de seguranca)
# ---------------------------------------------------------------------------
# function openclaude-yolo { & "$env:APPDATA\npm\openclaude.ps1" --yolo @args }
