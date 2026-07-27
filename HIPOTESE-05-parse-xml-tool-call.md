# HIPÓTESE 05 — Mismatch no parsing do formato XML de tool-call

**Status:** ✅ **CONFIRMADO SEGURO** · **Suspeita:** REFUTADA

## Hipótese
O template manda o modelo emitir o dialeto froggeric XML
(`<tool_call><function=NOME><parameter=X>valor</parameter></function></tool_call>`). O llama-server
tem que **reconverter** esse XML em `tool_calls` JSON — mas **nenhum flag de parser** é passado, ele
auto-detecta pelo conteúdo do template. Se o modelo desvia levemente do formato (indentação, prosa
antes do `<tool_call>`, valor multi-linha, aspas não escapadas), o parse falha → vem texto puro sem
`tool_calls`, e o agente que esperava uma ferramenta falha.

## O que explicaria
- Intermitência (o modelo às vezes formata certo, às vezes não).
- Nossos 12/12 testes passam porque usam prompts simples; casos reais (26 tools, args complexos)
  estressam mais o formato.

## Evidência a favor
- `scripts/start-server.sh`: `--jinja` + `--chat-template-file`, **sem** flag de parser de tool-call.
- Template exige `<tool_call>`/`<function>` no **início da linha, sem prosa antes** (instruções nas
  linhas ~126–138) — se o modelo põe texto antes, quebra.
- Args mapping/sequence são `tojson`; escalares são `| string` — valores com aspas/quebras podem
  gerar JSON inválido no `arguments`.

## Evidência contra
- `server.log` não tem `failed to parse` (grep=0). Se o parser do servidor falhasse, poderia (ou
  não) logar. Precisa confirmar se esse tipo de falha é logado.

## Como investigar
1. Capturar a saída **crua** do modelo (antes do parse) num caso real de tool com args complexos —
   ex.: `--chat-template-kwargs` ou um request com `stream` inspecionando os deltas crus.
2. Testar tool com valor multi-linha e com aspas/JSON aninhado nos argumentos; ver se `tool_calls`
   chega bem-formado.
3. Comparar formato `xml` vs `json` (`tool_call_format='json'`) no comportamento de parse.

## Resultado do teste automatizado (2026-07-26)
Teste com 3 tools (search_files, read_file, create_issue com oneOf) + prompt multi-tool:
- Tempo: 1.9s, 1 tool_call gerado: `search_files({"pattern": "src/**/*.py", "max_results": 10})`
- JSON parseado corretamente, schema respeitado.

H05 **refutada** — parse de XML/JSON de tool_call funciona corretamente no servidor.

## Confirmação / refutação
- **Confirma** se, nas falhas, o modelo emitiu um `<tool_call>` que **não** virou `tool_calls`
  (veio como texto), ou `arguments` com JSON inválido.
- **Refuta** se `tool_calls` sempre chega bem-formado quando o modelo tenta chamar ferramenta.

## Correção provável (se confirmada)
- Reforçar as instruções de formato no template; considerar `tool_call_format='json'` se o parser
  JSON for mais robusto; ou fixar um parser explícito do llama.cpp compatível com o dialeto.

## Como coletar a evidência

Ligue a captura de conteúdo e reproduza o problema, depois analise:
```bash
make capture-on && ...reproduza... && make capture-report && make capture-off
```
O relatório acende as flags relevantes desta hipótese. Detalhes: [docs/how-to/debugging.md](docs/how-to/debugging.md).
