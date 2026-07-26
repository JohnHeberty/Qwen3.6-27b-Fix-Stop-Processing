# HIPÓTESE 09 — Geração desenfreada / loop de repetição (bate o teto `n_predict`)

**Status:** ✅ CONFIRMADA (conteúdo do loop obtido) + FIX aplicado (DRY sampler) · **Suspeita:** CONFIRMADA

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
