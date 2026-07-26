# HIPÓTESE 09 — Geração desenfreada / loop de repetição (bate o teto `n_predict`)

**Status:** MITIGAÇÃO APLICADA (`PRESENCE_PENALTY=0.1` desde 2026-07-26; monitorar se some o "bate 8192") · confirmação de conteúdo pendente (log do cliente) · **Suspeita:** ALTA

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
