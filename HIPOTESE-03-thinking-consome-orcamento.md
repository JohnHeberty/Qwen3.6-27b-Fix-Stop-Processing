# HIPÓTESE 03 — O raciocínio consome o orçamento de tokens antes do `<tool_call>`

**Status:** NÃO INVESTIGADO · **Suspeita:** ALTA

## Hipótese
Em requisições com `tools`, o template **ainda abre `<think>\n`** (raciocínio ligado por padrão).
Com `-n = 8192` (N_PREDICT), numa tarefa difícil o modelo pode gastar todo o orçamento **dentro
do bloco de raciocínio** e bater `finish_reason=length` **antes** de emitir o `<tool_call>`.
Resultado: resposta truncada, sem `tool_calls` → agente sem ação utilizável.

## O que explicaria
- Já observamos esse padrão neste modelo: com `max_tokens` baixo, o `content` sai vazio e
  `finish_reason=length` (o raciocínio come tudo). Aqui é a mesma dinâmica atingindo o `tool_call`.
- É intermitente: depende de quão longo o modelo raciocina naquele turno.

## Evidência a favor
- Template `chat_template_local.jinja` (fim, prompt de geração): abre `<think>\n` a menos que
  thinking esteja off; `auto_disable_thinking_with_tools` **default false** → tools não desligam o
  thinking.
- `scripts/start-server.sh`: `-n "${N_PREDICT:-8192}"`, e **nenhum** `--reasoning-format`/`--reasoning`
  explícito.
- Comportamento já reproduzido em chat normal (64 tokens → content vazio, finish=length).

## Evidência contra
- 8192 tokens de saída é bastante; só estoura em turnos de raciocínio muito longo.

## Como investigar
1. Chamar com `tools` + prompt que exige ferramenta, variando `max_tokens` (256, 1024, 4096, 8192)
   e medir com que frequência sai `finish_reason=length` sem `tool_calls`.
2. Comparar com `enable_thinking=false` (mesmo prompt): a taxa de falha cai?
3. Medir `usage.completion_tokens` e o tamanho do `reasoning_content` nos casos que falham.

## Confirmação / refutação
- **Confirma** se as falhas trazem `finish_reason=length` com `reasoning_content` grande e sem
  `tool_calls`, e somem ao aumentar `max_tokens` ou desligar thinking.
- **Refuta** se as falhas têm `finish_reason=stop`/`tool_calls` e budget sobrando.

## Correção provável (se confirmada)
- Desligar thinking em chamadas de ferramenta: `auto_disable_thinking_with_tools=true` no template
  (via kwargs) **ou** `enable_thinking=false` no cliente para turnos de tool; e/ou subir o
  `max_tokens` do cliente. Avaliar `--reasoning-budget` do llama-server para limitar o raciocínio.
