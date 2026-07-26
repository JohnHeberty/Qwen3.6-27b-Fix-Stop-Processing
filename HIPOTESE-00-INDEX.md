# Investigação: falha ao chamar functions (MoltBot / OpenClaw → Qwen local)

**Sintoma:** o agente externo (MoltBot, persona do OpenClaw/Clawdbot no Telegram) falha ao
chamar ferramentas, com `⚠️ Agent couldn't generate a response. Note: some tool actions may
have already been executed — please verify before retrying.` Às vezes surfaceia o raciocínio
(`🧠 The user said...`) e então falha.

**Arquitetura do caminho que falha:** MoltBot (externo, `@ai-sdk/openai-compatible`) →
LiteLLM `:4000` (`100.91.54.69`) → llama-server `:8000` → template `chat_template_local.jinja`.
Chat Completions, **streaming ligado**, `tools:true`, `reasoning:true`,
`interleaved.field=reasoning_content`. Refs: `.opencode/opencode.json`,
`infra/litellm/config.yaml`.

## Achados que orientam o ranking (evidência já coletada)

1. **`server.log` NÃO tem erros de tool-parse / grammar / template.** Grep: `failed to parse`=0,
   `tool_call`=0, `grammar`=0, `jinja`=0, `exception`=0. O único erro duro do servidor é
   **estouro de contexto**: `request (143k–179k tokens) exceeds the available context size
   (106496 tokens)` (server.log linhas ~24889–27074, 33885, 40097).
2. **LiteLLM (:4000) não está escutando** agora (`ss -tlnp`: só :8000 llama-server e :11434
   ollama). O `.opencode/opencode.json` aponta pra `100.91.54.69:4000` → conexão falharia antes
   de chegar no modelo.
3. **Requisições de tool ainda abrem `<think>` por padrão** (`auto_disable_thinking_with_tools`
   default false) e `-n=8192` → o raciocínio pode consumir todo o orçamento antes do `<tool_call>`.
4. MoltBot/OpenClaw é **externo** ao repo — não há código dele aqui, só a transcrição em
   `data/temp/opencode_session_mtp_export.md`, que já diagnostica turnos com `reasoning_content`
   sem `content`/`tool_calls`.

## Ranking (a confirmar com investigação)

| # | Hipótese | Suspeita | Base |
|---|---|---|---|
| 10 | **Crash do servidor por OOM de RAM** (cache-ram 10G em host de 16G) | **ALTA** | Servidor caído; log corta em linha de memória |
| 09 | **Geração desenfreada / loop de repetição** (bate teto 8192) | **ALTA** | 11 gerações no teto 8192; repeat_penalty=1.0 |
| 01 | Estouro de janela de contexto | **ALTA** | Prompts até 104k/106k; 2 overflows |
| 02 | Turno vazio: só `reasoning_content`, sem `content`/`tool_calls` | **ALTA** | Config + transcrição |
| 03 | Thinking consome o orçamento antes do tool_call (finish=length) | **ALTA** | Template + `-n=8192` |
| 04 | LiteLLM `:4000` fora do ar / caminho quebrado | **MÉDIA** | `ss` sem listener |
| 05 | Mismatch de parsing do XML de tool-call (`<function=>`) | **MÉDIA** | Sem flag de parser |
| 06 | Template `raise_exception` em content mal-formado | **MÉDIA/BAIXA** | 5 pontos de throw |
| 07 | Retry/timeout do framework com `N_PARALLEL=1` | **MÉDIA** | "actions already executed" |
| 08 | Gramática enorme do array de ~26 tools | **BAIXA** | Sem erro nos logs |

## Achados da investigação de logs (2026-07-26, `server.log` último run, ~3864 requests)

- **Servidor CAÍDO agora** (`:8000` HTTP 000, sem processo). Log termina abruptamente numa linha de
  pressão de memória do prompt cache (885 MiB) → provável **OOM** (host 16 GB, `cache-ram 10 GB`). → **H10**
- **27 gerações ≥6000 tokens; 11 bateram o teto exato 8192** (force-stop) — loop de repetição no
  nível de geração. Rodava com `repeat_penalty=1.0` (penalidade desligada). → **H09**
- Prompts cresceram até **104.296 / 106.496** tokens; ~**49%** das requisições reprocessam contexto
  quase-idêntico (`sim_best ≥ 0.99`) — consistente com subagente reenviando a mesma conversa. → **H01**
- **Limitação:** o `server.log` **não grava conteúdo** — o texto do loop precisa vir do log do
  cliente (MoltBot/OpenCode subagent), que é externo a este repo.

## Método de investigação (para cada HIPOTESE-NN)

Cada arquivo tem: hipótese, o que explicaria, evidência a favor/contra, **como investigar**
(passos concretos), **critério de confirmação/refutação**, e correção provável. Investigar em
ordem de suspeita (01→08). Marcar o `Status` no topo de cada arquivo ao concluir.

> Nada aqui foi confirmado ainda — são hipóteses para investigar com calma. Vários podem estar
> ocorrendo juntos (ex.: 03 alimenta 02).
