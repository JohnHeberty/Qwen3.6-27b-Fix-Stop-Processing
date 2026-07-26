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

## Ranking + status (atualizado 2026-07-26)

Legenda: ✅ feito/mitigado · 🟡 parcial (falta validar) · ⬜ pendente · 🔎 precisa do log do cliente

| # | Hipótese | Suspeita | Status | O que já foi feito | O que falta |
|---|---|---|---|---|---|
| 10 | **Crash por OOM de RAM** | ALTA | ✅ **Fechada** | Confirmada no `dmesg` (kill do llama-server, memcg /lxc/139). VM subida p/ 32 GB. Serviço systemd com `Restart=always` (auto-recupera). | Só observar que não recorre em uso pesado |
| 09 | **Loop de repetição** (bate 8192) | ALTA | ✅ **Confirmada + fix** | Conteúdo do loop obtido (raciocínio repetindo bloco verbatim). presence_penalty=0.1 NÃO segurou → **DRY sampler** aplicado (`DRY_MULTIPLIER=0.8`, allowed_length=4, last_n=1024). 12/12 testes. | Validar em **uso real** via captura (flags `runaway`/`loop_repeat` = 0); cliente pode sobrepor sampling |
| 01 | Estouro de janela de contexto | ALTA | ⬜ Pendente | Medido: prompts a 104k/106k; ~49% reprocessam contexto quase-idêntico. | Config **do cliente**: `compaction.prune`/`max_input` do OpenCode p/ o subagente não crescer até o teto |
| 03 | Thinking consome o orçamento (finish=length) | ALTA | ⬜ Pendente | Mecanismo mapeado (template abre `<think>` mesmo com tools; `-n=8192`). | Testar `max_tokens` maior e/ou `auto_disable_thinking_with_tools=true`; medir taxa de finish=length sem tool_call |
| 02 | Turno vazio (só `reasoning_content`) | ALTA | 🔎 Pendente | Hipótese descrita; bate com a transcrição. | Confirmar no **log do cliente** que falhas têm content vazio + sem tool_calls |
| 04 | LiteLLM `:4000` fora do ar | MÉDIA | ⬜ Pendente | Constatado: `:4000` não escutava. | Deixar o LiteLLM **supervisionado** (systemd) e healthcheck |
| 05 | Parse do XML de tool-call | MÉDIA | 🔎 Pendente | Formato/risco mapeado; sem erro no server.log. | Capturar a **saída crua** do modelo num tool com args complexos |
| 06 | Template `raise_exception` | MÉDIA/BAIXA | 🔎 Pendente | 5 pontos de throw listados. | Ver no log do cliente o **shape do `content`** enviado (mapping?) |
| 07 | Retry/timeout com `N_PARALLEL=1` | MÉDIA | 🔎 Pendente | Serialização confirmada. | Medir latência do turno vs timeout do cliente |
| 08 | Gramática de ~26 tools | BAIXA | ⬜ Pendente | Sem erro de grammar nos logs; patch já eleva limite. | Reproduzir com o array real de 26 tools e medir |

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

## O que falta fazer (resumo)

**Nosso lado (servidor) — praticamente fechado:**
- ✅ H10 (OOM): confirmada + mitigada (32 GB + systemd `Restart=always`).
- 🟡 H09 (loop): `presence_penalty=0.1` aplicado — falta só **ver em uso real** se resolveu.

**Depende de você / do log do cliente (MoltBot/OpenCode) — não fecha só no servidor:**
- ⬜ H01: ajustar compactação/`max_input` do cliente (contexto ia a 104k).
- ⬜ H03: testar `max_tokens` maior ou desligar thinking em chamadas de tool.
- ⬜ H04: deixar o LiteLLM supervisionado.
- 🔎 H02, H05, H06, H07: precisam do **log do cliente** de um turno que falhou (o `server.log` não grava conteúdo).
- ⬜ H08 (baixa): reproduzir com as 26 tools reais.

**Próximo passo mais útil:** reproduzir o subagente com o servidor já ajustado e trazer o **log do
cliente** — com ele dá pra confirmar H09 e fechar H02/H03/H05/H06/H07 de uma vez.

> H10 confirmada e H09 mitigada; o resto são hipóteses abertas. Vários podem ocorrer juntos
> (ex.: H03 alimenta H02; H01+H09 alimentam H10).
