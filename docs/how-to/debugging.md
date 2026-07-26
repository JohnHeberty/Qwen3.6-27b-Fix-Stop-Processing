# Debugging: capturar o conteúdo real das requisições

O `data/logs/server.log` só grava **timings** (tok/s, n_decoded, motivo de parada), não o
**conteúdo** (prompt, resposta, tool_calls, texto de um loop). Para diagnosticar tool-calling
quebrado, "Agent couldn't generate a response", loops de repetição, ou overflow de contexto, ligue
a **captura de conteúdo** — nativa do llama-server, **sem proxy** e **sem mexer no cliente**.

> Captura é **opt-in** e **volumosa** (loga cada token gerado). Ligue só numa janela de depuração e
> desligue depois com `make capture-off`.

## Fluxo

```bash
make capture-on        # liga --log-prompts-dir + --verbose e reinicia o servidor
#   ... reproduza o problema (rode o subagente/cliente que falha) ...
make capture-report    # analisa o que foi capturado e mostra um relatório com flags
make capture-off       # desliga e volta ao normal
make clean-capture     # (opcional) apaga os dados capturados
```

## O que é capturado (em `data/logs/capture/`)

- `prompts/YYYY-MM-DD/<ts>.txt` — o **prompt renderizado** de cada requisição (saída do template +
  todas as mensagens + as tools que o cliente enviou). Um arquivo por chamada.
- `llama-verbose.log` — log verboso com **cada token gerado** (`next token: N 'txt'`) e o **motivo de
  parada** (`stopped by EOS` / `stopped by limit`). O analisador reconstrói o texto gerado a partir
  daqui (inclusive o `<tool_call>` cru e o texto de um loop).

## O relatório (`make capture-report`)

Emite contadores + top ofensores, com **flags automáticas** que mapeiam nas hipóteses:

| Flag | Significa | Hipótese |
|---|---|---|
| `runaway` | geração bateu (ou quase) o teto `N_PREDICT` | H09 (loop) |
| `loop_repeat` | texto gerado tem repetição cíclica | H09 |
| `empty_turn` | resposta sem `content` e sem `<tool_call>` | H02 ("couldn't generate a response") |
| `thinking_only` | só raciocínio, nada depois de `</think>` | H02/H03 |
| `has_tool_call` | emitiu `<tool_call>`/`<function=` (vê o XML cru) | H05 |
| `near_context` | prompt > 90% do contexto | H01 (overflow) |

Opções úteis: `make capture-report ARGS="--jsonl out.jsonl --top 20"` (grava 1 registro por geração
em JSONL para análise posterior). O script é `scripts/analyze-capture.py`.

## Validar o fix anti-loop (DRY) — H09

O loop de repetição (o modelo repetindo o mesmo bloco de raciocínio até estourar os 8192 tokens)
foi corrigido com o **DRY sampler** (`DRY_MULTIPLIER=0.8`, ver `.env` / `docs/reference/configuration.md`).
Para **confirmar em uso real** que sumiu:

```bash
make capture-on        # captura + DRY ficam ativos
#   ... reproduza o subagente/tarefa que loopava ...
make capture-report    # olhe as flags 'runaway' e 'loop_repeat'
```

- Se `runaway` e `loop_repeat` vierem **0/N**, o DRY resolveu.
- Se ainda acenderem, aumente `DRY_MULTIPLIER` (0.8 → 1.0) ou reduza `DRY_ALLOWED_LENGTH` (4 → 3),
  `make capture-off && make capture-on`, e reproduza de novo.
- **Atenção:** se o cliente (OpenCode/MoltBot) enviar parâmetros de sampling próprios na requisição,
  eles **sobrepõem** os do servidor — nesse caso o loop pode persistir mesmo com DRY aqui, e o ajuste
  precisa ser no cliente. O prompt capturado (`prompts/*.txt`) ajuda a confirmar o que chegou.

## Compactação no cliente (OpenClaw / OpenCode) — reduzir a "zona de loop"

Na captura, os prompts chegavam a **~72k tokens** e o modelo entrava em loop. Isso é a soma do
lado servidor (DRY + `error_warnings`) **com** o lado cliente: se o agente deixa o contexto crescer
até ~72k, o modelo degrada. Mantenha o contexto de operação **bem abaixo disso (~48–60k)**.

**OpenCode** (`.opencode/opencode.json`): o modelo `qwen` usa `limit.context: 60000` (era 98304) +
`compaction: { auto, prune }`. Contexto menor = sem zona de loop, mais rápido, menos risco de OOM.

**OpenClaw** (`/root/.openclaw/…`, na outra máquina): ver o arquivo
[`openclaw-recommended-compaction.json`](../../openclaw-recommended-compaction.json) na raiz do repo
— baixa `contextWindow/contextTokens` para `60000`, `reserveTokensFloor` 35000 → 12000, liga
`midTurnPrecheck` (corta o crescimento dentro do turno) e aperta o pruning de tool results.
Regra: `contextWindow − reserveTokensFloor` = teto do histórico; deixe isso ~48k, não ~72k.

## Rotação de logs

`server.log` não rotaciona sozinho e cresce rápido (mais ainda com captura ligada). Instale a
rotação (diária, 7 dias, `copytruncate`):

```bash
make install-logrotate     # instala /etc/logrotate.d/qwen-logs (caminho resolvido)
make uninstall-logrotate   # remove
```

## Limitação conhecida

O cliente (OpenCode/MoltBot) usa um LiteLLM em **outra máquina**; esta captura pega o que chega no
`llama-server` desta máquina (`:8000`) — que é onde os crashes/loops ocorreram. Se algum dia quiser
log **estruturado** com custo/latência por requisição no gateway, dá para instrumentar o LiteLLM
**local** (LiteLLM 1.93.0 suporta `CustomLogger` via `litellm_settings.callbacks`) e repontar o
cliente para cá — fora do escopo atual.
