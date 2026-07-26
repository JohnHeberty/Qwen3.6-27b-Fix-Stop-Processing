# HIPÓTESE 07 — Retry/timeout do framework com `N_PARALLEL=1`

**Status:** NÃO INVESTIGADO · **Suspeita:** MÉDIA

## Hipótese
Com `N_PARALLEL=1`, o llama-server atende **uma requisição por vez**; as demais **enfileiram**. Se o
MoltBot dispara chamadas concorrentes ou o turno demora (raciocínio longo + geração), o cliente
**estoura o timeout** e considera "no response" — e o aviso "some tool actions may have already been
executed" indica que houve **retry** (a ação chegou a rodar, mas a resposta não voltou a tempo).

## O que explicaria
- A frase literal do erro ("actions may have already been executed") = clássico de timeout + retry.
- Intermitência sob carga / quando o modelo demora mais.

## Evidência a favor
- `scripts/start-server.sh`: `--parallel 1` (obrigatório pelo bug de KV cache — ver CLAUDE.md).
- Requisições grandes + MTP + raciocínio podem levar dezenas de segundos; timeouts de cliente
  costumam ser curtos.
- `server.log` tem muitas linhas de fila/停 (`stop processing`), consistente com serialização.

## Evidência contra
- Se fosse só timeout, não haveria o padrão "pensa e falha" (02/03) nem os overflows (01).

## Como investigar
1. Medir latência real de um turno com tools (do request ao primeiro token e ao fim) e comparar com
   o timeout do MoltBot/OpenClaw.
2. Verificar se o MoltBot faz chamadas concorrentes (ex.: heartbeat + turno) contra o mesmo slot.
3. Olhar `server.log` por requests que começam mas não completam perto dos timestamps de falha.

## Confirmação / refutação
- **Confirma** se as falhas coincidem com latência > timeout do cliente e/ou requisições
  enfileiradas no server.log.
- **Refuta** se as falhas ocorrem rápido, sem espera/fila.

## Correção provável (se confirmada)
- Aumentar o timeout do cliente; evitar chamadas concorrentes ao slot único; considerar streaming
  (mantém a conexão viva); avaliar se dá para relaxar `N_PARALLEL` sem reintroduzir o bug de KV.
