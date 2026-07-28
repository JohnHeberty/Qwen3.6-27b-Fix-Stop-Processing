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

## Validar o fix anti-loop — H09

O loop de repetição (o modelo repetindo o mesmo bloco de raciocínio até estourar os 8192 tokens) é
cortado por **`REASONING_BUDGET=2048`** — não por DRY (que foi revertido: quebrava tool-calling) e
não por reduzir contexto. Para **confirmar em uso real** que sumiu:

```bash
make capture-on        # liga a captura
#   ... reproduza o subagente/tarefa que loopava ...
make capture-report    # olhe as flags 'runaway' e 'loop_repeat'
```

- Se `runaway` e `loop_repeat` vierem **0/N**, está resolvido.
- Se ainda acenderem, **diagnostique qual dos dois problemas é** antes de mexer:
  - **Trava / `finish=length` / raciocínio longo repetitivo** → é o thought-loop:
    baixe `REASONING_BUDGET` (2048 → 1024).
  - **Saída curta repetindo/parafraseando a mesma frase** → NÃO é thought-loop, o
    `REASONING_BUDGET` não pega isso: suba `PRESENCE_PENALTY` (padrão já é 1.5; o model card
    do Qwen3 permite até 2.0 para modelos quantizados em thinking mode).
  - **nunca** reativar `DRY_MULTIPLIER` em uso agêntico (trunca caminhos de arquivo).
- **Atenção:** se o cliente (OpenCode/MoltBot) enviar parâmetros de sampling próprios na requisição,
  eles **sobrepõem** os do servidor — nesse caso o ajuste precisa ser no cliente. O prompt capturado
  (`prompts/*.txt`) ajuda a confirmar o que chegou.
- Um teste rápido sem reproduzir nada: `make test` inclui o "Contrato de reasoning", que falha se a
  geração terminar em `finish_reason=length` ou com `content` vazio.

## O loop de raciocínio — fix no servidor, contexto PRESERVADO

Descoberta importante: **não** se resolve jogando fora contexto. Testamos reduzir o contexto do
cliente e reverter — os clientes ficam com os **104k cheios** (`.opencode` e OpenClaw em 106496).
O thought-loop (o modelo repetindo um parágrafo dentro do `<think>` até estourar) é cortado no
servidor por **`REASONING_BUDGET`** (`--reasoning-budget`, default 2048): ao atingir o teto de
tokens de pensamento, o llama.cpp fecha `</think>` e força a resposta/ação. Isso capa o raciocínio
descontrolado **sem** encolher contexto nem quebrar tool-calling.

> ⚠️ **Não** use o DRY sampler em uso agêntico: ele trunca caminhos de arquivo repetidos (quebra
> tool calls — ver `HIPOTESE-09`). Se um loop verbatim persistir, prefira `REPEAT_PENALTY=1.05` leve.

Camadas anti-loop (todas preservam contexto): `REASONING_BUDGET` (thought-loop) · `error_warnings`
(loop de retry após 2 falhas de ferramenta) · `presence_penalty=0.1` (leve).

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
