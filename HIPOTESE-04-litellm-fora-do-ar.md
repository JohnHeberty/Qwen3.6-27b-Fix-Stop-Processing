# HIPÓTESE 04 — LiteLLM (:4000) fora do ar / caminho quebrado

**Status:** NÃO INVESTIGADO · **Suspeita:** MÉDIA

## Hipótese
O `.opencode/opencode.json` do MoltBot aponta para `http://100.91.54.69:4000/v1` (LiteLLM). Se o
LiteLLM não estiver rodando (ou instável), a conexão falha **antes** de chegar no modelo, e o
framework surfaceia "Agent couldn't generate a response". Não seria culpa do modelo nem do template.

## O que explicaria
- Falhas totais e imediatas (sem raciocínio), diferentes das falhas "depois de pensar" (02/03).
- Intermitência se o LiteLLM cai/reinicia sob carga.

## Evidência a favor
- **Agora** (`ss -tlnp`): só `:8000` (llama-server) e `:11434` (ollama) escutando. **Nada em :4000.**
- `data/logs/litellm.log`: subiu, atendeu poucas chamadas, e registrou `Shutting down` — não está
  ativo continuamente.
- `.opencode/opencode.json` linha ~11: `baseURL: http://100.91.54.69:4000/v1`.

## Evidência contra
- O MoltBot roda em outra máquina; o LiteLLM que ele usa pode estar em `100.91.54.69` (Tailscale) e
  não neste host. Antes (mais cedo nesta sessão) o `100.91.54.69:4000` respondeu 200 a um teste real.
- Falhas que mostram raciocínio antes de falhar (02/03) não se explicam por LiteLLM off.

## Como investigar
1. No momento de uma falha, testar `curl -s -o /dev/null -w '%{http_code}' http://100.91.54.69:4000/health`.
2. Ver se o LiteLLM tem supervisão (systemd/pm2) ou se depende de `make litellm-start` manual.
3. Ligar log de request no LiteLLM e correlacionar quedas com as falhas do MoltBot.

## Confirmação / refutação
- **Confirma** se as falhas coincidem com `:4000` indisponível / 5xx do LiteLLM.
- **Refuta** se o LiteLLM responde 200 no momento das falhas (então o problema é adiante).

## Correção provável (se confirmada)
- Subir o LiteLLM como serviço supervisionado (systemd) com restart automático; healthcheck; e/ou
  apontar o MoltBot direto pro `:8000` se o LiteLLM não for necessário para esse agente.
