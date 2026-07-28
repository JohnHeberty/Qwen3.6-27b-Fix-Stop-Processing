# HIPÓTESE 09 — Geração desenfreada / loop de repetição (bate o teto `n_predict`)

**Status:** ✅ CONFIRMADA · ⚠️ FIX corrigido: **DRY foi REVERTIDO** (quebrava tool-calling) · **Suspeita:** CONFIRMADA

## ✅ FIX REAL (2026-07-26): `--reasoning-budget` (preserva contexto e tools)
Depois de reverter o DRY, o fix correto (pesquisado — o `--reasoning-budget` do llama.cpp foi
criado **justamente para conter os thought-loops do Qwen3.6 em temperatura baixa**): capar os
tokens **de pensamento**. `REASONING_BUDGET=2048` → ao atingir 2048 tokens dentro do `<think>`, o
llama.cpp fecha o `</think>` e **força a resposta/ação**. Isso mata o loop de raciocínio (que ia até
8192) **sem** reduzir o contexto (segue 104k) e **sem** tocar no tool-calling. Verificado: raciocínio
longo real convergiu em ~1650 tokens (abaixo do teto), `finish=stop`, resposta completa, sem hang;
12/12 nos testes. Fontes: llama.cpp PR #25961 / discussão #21445.

## ⚠️ Correção do fix anterior (2026-07-26): DRY desligado
O DRY sampler (que tínhamos ligado) **truncava caminhos de arquivo repetidos**: a captura mostrou a
saída do modelo cortada no meio (`<parameter=command>sed -n '780,850p' src/ia_investing/i` ←
cortado), porque o path se repete no contexto e o DRY penaliza a repetição — sem distinguir "loop
ruim" de "path que o agente precisa repetir". Resultado: comandos/paths cortados → tool calls falham
→ loop de retry (42 prompts quase-idênticos na captura). **DRY_MULTIPLIER=0 agora.**

**Defesa anti-loop atual (2026-07-28, sem DRY e sem reduzir contexto):**
1. `REASONING_BUDGET=2048` — corta o thought-loop na RAIZ (é o fix principal).
2. `error_warnings` especialista — quebra o loop de *retry* após 2 falhas de ferramenta.
3. Contexto do cliente **cheio, 104k** (106496). A redução para ~60k que constava aqui foi
   **revertida**: jogar fora contexto era contornar o sintoma, não corrigir o loop.
4. `PRESENCE_PENALTY=1.5` — valor do model card do Qwen3 para modelos *quantizados* em thinking
   mode (rodamos Q4_K_M).

NÃO reativar o DRY em uso agêntico em nenhuma dessas etapas.

### Experimento que separou os dois modos de falha (2026-07-28)
Baixamos `PRESENCE_PENALTY` de 1.5 → 0.0 (seguindo a recomendação *base* do Qwen, que é para
modelos não-quantizados). Resultado observado em produção (OpenClaw/Telegram):

- ✅ **O travamento NÃO voltou** — o `REASONING_BUDGET` sozinho resolve o hang.
- ❌ **A repetição VOLTOU** — o modelo parafraseou a mesma confirmação curta 4x seguidas
  ("Combinado, John. Vou salvar isso no AGENTS.md…"). Saída **curta**, não raciocínio longo.

Conclusão: são **dois problemas distintos**, e cada defesa cobre um.

| Falha | Sintoma | Defesa |
|---|---|---|
| Raciocínio descontrolado | trava / `finish=length` sem resposta | `REASONING_BUDGET=2048` |
| Repetição na saída final | repete/parafraseia a mesma frase | `PRESENCE_PENALTY=1.5` |

`PRESENCE_PENALTY` revertido para 1.5. 13/13 nos testes com o valor alto — não quebra tool-calling.

**Regressão automatizada:** `tests/test_api.py` agora tem o teste "Contrato de reasoning" — afirma
`finish_reason == "stop"` com `reasoning_content` E `content` não-vazios. Se alguém puser um
`REASONING_BUDGET` ruim, o teste pega (13/13 hoje).

## Confirmação (conteúdo real do loop, 2026-07-26)
O usuário colou o raciocínio de um turno que "estourou limite": o modelo repetiu **o mesmo
parágrafo de ~6 blocos, palavra por palavra, dezenas de vezes** ("Wait, I think I see the issue
now… / OK I'm going in circles. Let me just add some debug logging"), até bater o teto de 8192
tokens. É um **loop de repetição no bloco de raciocínio** (`<think>`), não em tool-call.

## Por que as mitigações leves não seguraram
- `presence_penalty=0.1` é binário e satura (todos os tokens comuns já "presentes") — não quebra
  um atrator de loop forte.
- `repeat_last_n=64` é **pequeno demais**: o bloco repetido é maior que 64 tokens, então quando
  reaparece a ocorrência anterior já saiu da janela → penalidade zero.

## Fix aplicado — DRY sampler (afinado)
`DRY_MULTIPLIER=0.8 DRY_BASE=1.75 DRY_ALLOWED_LENGTH=4 DRY_PENALTY_LAST_N=1024`. DRY penaliza a
repetição de **sequências longas verbatim** (o loop), sem punir repetição legítima de código.
**Lição de afinação:** com `allowed_length=2` + contexto inteiro, o DRY ficou agressivo demais e o
modelo *thinking* passou a rambleiar até o limite mesmo numa conta trivial (7×8) — subir para
`allowed_length=4` e janela `1024` resolveu (12/12 nos testes, sem rambling). `multiplier=0` desliga.

> Falta: validar em **uso real** (reproduzir o subagente) que o loop de raciocínio some. Nota: se o
> cliente enviar seus próprios parâmetros de sampling, eles podem sobrepor os do servidor.

## Hipótese
O modelo entra em **loop de repetição** dentro de um único turno e gera texto até bater o teto
`n_predict = 8192`, em vez de dar uma resposta curta ou um `tool_call`. Para o subagente, isso
aparece como "travado em loop infinito" (a geração não converge; o turno demora e/ou volta lixo
repetido). Suspeito reforçado: aplicamos `repeat_penalty = 1.0` (penalidade **desligada**, valor
Qwen), o que remove justamente a proteção contra repetição.

## Evidência a favor (medida no `data/logs/server.log`, último run)
- **27 gerações com ≥6000 tokens de saída**; destas, **11 bateram EXATAMENTE 8192** (o teto
  `n_predict`) → force-stop por limite = geração que não converge. ~5 dessas no trecho mais recente
  (linhas 80k+ do log).
- Histograma de saída do run: `<50:17 · 50-499:3104 · 500-1999:605 · 2000-5999:111 · ≥6000:27`.
  O normal é <500 tokens; 27 turnos "explodindo" é anômalo.
- Servidor rodava com `--repeat-penalty 1.0 --frequency-penalty 0.0 --presence-penalty 0.0`
  (confirmado no cmdline do processo) — **nenhuma** penalidade anti-repetição.
- O `.env` anterior usava `REPEAT_PENALTY=1.15` (freava repetição); a troca para 1.0 veio da
  recomendação Qwen do `FIX/FIX`, mas pode não servir para contexto agêntico longo neste modelo.

## Evidência contra / a checar
- Não temos o **texto** gerado (o server.log não grava conteúdo) — a confirmação de que era
  repetição (e não conteúdo legítimo longo) precisa do log do cliente (MoltBot/OpenCode).
- MTP (speculative decoding) tem aceitação ~0.98 nessas gerações — não parece ser o MTP quebrando.

## Como investigar
1. Pegar do log do cliente (externo) o texto de um turno que bateu ~8192 tokens e confirmar se é
   repetição (mesma frase/estrutura ciclando).
2. Teste A/B de sampling no mesmo prompt problemático: `repeat_penalty=1.0` vs `1.05` vs `1.1`
   (e/ou `presence_penalty=0.1`), medindo taxa de gerações que batem 8192.
3. Verificar se as gerações desenfreadas coincidem com contexto muito longo (interação com H01).

## Confirmação / refutação
- **Confirma** se o texto for repetitivo e a taxa de "bate 8192" cair ao reintroduzir uma
  penalidade de repetição leve.
- **Refuta** se as gerações longas forem conteúdo legítimo (ex.: o modelo realmente gerando um
  arquivo grande pedido) e não repetição.

## Correção provável (se confirmada)
- Reintroduzir penalidade leve: `REPEAT_PENALTY=1.05`–`1.1` **ou** `PRESENCE_PENALTY=0.1`
  (mantendo temp/top_k Qwen). Documentar como exceção consciente à recomendação Qwen para uso
  agêntico. Opcional: baixar `N_PREDICT` para conter o custo de um runaway.

## Como coletar a evidência

Ligue a captura de conteúdo e reproduza o problema, depois analise:
```bash
make capture-on && ...reproduza... && make capture-report && make capture-off
```
O relatório acende as flags relevantes desta hipótese. Detalhes: [docs/how-to/debugging.md](docs/how-to/debugging.md).
