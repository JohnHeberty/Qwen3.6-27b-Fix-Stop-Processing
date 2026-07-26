# HIPÓTESE 01 — Estouro da janela de contexto

**Status:** NÃO INVESTIGADO · **Suspeita:** ALTA (evidenciada no server.log)

## Hipótese
O agente acumula histórico (saídas de ferramentas, arquivos grandes como o `TOOLS.md`, o schema
de ~26 tools) e reenvia um prompt que cresce a cada turno, até **passar de 106.496 tokens**. O
llama-server rejeita a requisição inteira; o cliente não recebe resposta e surfaceia
"Agent couldn't generate a response".

## O que explicaria
- A falha aparecer justamente ao mexer no `TOOLS.md` (arquivo grande) + histórico longo.
- "some tool actions may have already been executed" = o turno anterior rodou tools, cresceu o
  histórico, e o próximo turno estourou.

## Evidência a favor
- `data/logs/server.log` linhas ~24889–27074, 33885, 40097:
  `E srv send_error: ... request (179852 tokens) exceeds the available context size (106496 tokens)`.
  Cluster grande dessas linhas (143k–179k tokens).
- `infra/litellm/config.yaml`: `max_input_tokens: 98304`, `max_tokens: 8192`. O servidor roda com
  `--ctx-size 106496`. Um prompt de 143k+ estoura os dois.
- `N_PARALLEL=1` → a janela inteira é um slot só; não há como dividir.

## Evidência contra
- Nem toda falha do MoltBot precisa ser overflow; pode coexistir com 02/03.

## Como investigar
1. Reproduzir: mandar via LiteLLM/`:8000` um prompt propositalmente grande (colar o `TOOLS.md` +
   tools) e ver se retorna o `send_error` de contexto.
2. Medir o tamanho real dos prompts do MoltBot: ligar logging de request no LiteLLM (ou um proxy
   de log temporário) e checar `prompt_tokens` / `usage` das chamadas que falham.
3. Conferir se o cliente respeita `max_input_tokens=98304` (o OpenCode tem `compaction`/`prune`;
   ver se está ativo e funcionando para esse agente).

## Confirmação / refutação
- **Confirma** se as falhas coincidem com `send_error ... exceeds context size` no server.log no
  mesmo timestamp.
- **Refuta** se as falhas ocorrem com `prompt_tokens` bem abaixo de 98304 e sem `send_error`.

## Correção provável (se confirmada)
- Poda/compactação de histórico no cliente (OpenCode `compaction.auto/prune`), truncar saídas de
  ferramenta gigantes, ou baixar o volume de tools por request. Eventualmente subir `N_CTX` (custa
  VRAM/velocidade — ver docs/infra).

## Como coletar a evidência

Ligue a captura de conteúdo e reproduza o problema, depois analise:
```bash
make capture-on && ...reproduza... && make capture-report && make capture-off
```
O relatório acende as flags relevantes desta hipótese. Detalhes: [docs/how-to/debugging.md](docs/how-to/debugging.md).
