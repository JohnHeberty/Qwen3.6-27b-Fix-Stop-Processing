# HIPÓTESE 02 — Turno vazio: só `reasoning_content`, sem `content` nem `tool_calls`

**Status:** NÃO INVESTIGADO · **Suspeita:** ALTA

## Hipótese
O modelo devolve **apenas raciocínio** (`reasoning_content`) e termina o turno com `content`
vazio e **sem** `tool_calls`. O framework do agente (OpenClaw/MoltBot) interpreta isso como
"turno vazio" e emite "Agent couldn't generate a response". A transcrição do próprio agente
(`data/temp/opencode_session_mtp_export.md`) chega a essa conclusão.

## O que explicaria
- O log do MoltBot mostra o raciocínio (`🧠 The user said...`) e **em seguida** a falha — ou seja,
  houve raciocínio, mas nenhum conteúdo/ação final utilizável.
- Não gera erro no server.log (o servidor respondeu 200; quem rejeita o turno é o cliente).

## Evidência a favor
- `.opencode/opencode.json`: `reasoning:true`, `interleaved.field=reasoning_content` — o cliente
  separa o raciocínio; se só vier raciocínio, o "conteúdo" fica vazio.
- Server-side não loga erro nesses casos (consistente com falha no cliente).
- Interage com HIPÓTESE 03 (se o thinking consome o orçamento, sobra turno só-raciocínio).

## Evidência contra
- Se o cliente renderiza `reasoning_content` como resposta, um turno só-raciocínio poderia não ser
  "vazio" — precisa checar como o OpenClaw trata isso (diferente do OpenCode).

## Como investigar
1. Chamar o modelo com `tools` e uma pergunta que force ferramenta, com `stream=true`, e inspecionar
   o objeto final: `finish_reason`, `content`, `tool_calls`, `reasoning_content`. Ver se há casos
   com `content=""` e `tool_calls=None`.
2. Repetir várias vezes (o problema é intermitente) para pegar a variância.
3. Verificar no framework do MoltBot/OpenClaw como ele decide "no response" (precisa de log do lado
   do cliente — está fora deste repo).

## Confirmação / refutação
- **Confirma** se, nas falhas, a resposta do modelo tem `reasoning_content` preenchido mas
  `content` vazio **e** `tool_calls` ausente.
- **Refuta** se as falhas sempre trazem `content` ou `tool_calls` não-vazios (então o problema é
  no parsing/entrega, não no turno vazio).

## Correção provável (se confirmada)
- Garantir orçamento de saída suficiente (ligado à 03); e/ou desabilitar thinking para chamadas de
  ferramenta (`enable_thinking=false` ou `auto_disable_thinking_with_tools=true` no template); e/ou
  ajustar o cliente para tratar turno só-raciocínio como válido (continuar em vez de abortar).
