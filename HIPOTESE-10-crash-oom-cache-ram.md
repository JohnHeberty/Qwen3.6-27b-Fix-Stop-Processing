# HIPÓTESE 10 — Crash do servidor por OOM de RAM do host (prompt cache)

**Status:** ✅ CONFIRMADO por `dmesg` + MITIGADO (VM 32 GB, servidor religado) · **Suspeita:** CONFIRMADA

## Confirmação (dmesg do host pve1)
- `[Sun Jul 26 16:40:50 2026] Memory cgroup out of memory: Killed process (llama-server)`,
  `oom_memcg=/lxc/139`, `anon-rss ~12.7 GB` — **é o crash que investigamos** (bate com o fim do
  server.log às 16:40). Foi o **limite de memória do container LXC 139**, não do host inteiro.
- Antes: `[Sat Jul 25 01:16:17 2026] global_oom ... llama-server`, `shmem-rss ~22 GB`.
- Aumentar o LXC 139 para 32 GB eleva justamente esse limite de cgroup → deve impedir a recorrência.
- **Nota:** o container LXC 200 (postgres em docker) sofre OOM recorrente (a cada poucas horas) —
  problema SEPARADO, não é o nosso serviço.

## Hipótese
O llama-server **caiu** durante o manejo do prompt cache em RAM do host. Com prompts de ~104k
tokens e `--cache-ram 10240` (10 GB) num host de **apenas 16 GB**, a pressão de memória levou a
um OOM/kill. Um subagente em loop (H01/H09) que reenvia contextos gigantes acelera o consumo até
estourar. Resultado visível: o agente "trava" porque o backend morreu.

## Evidência a favor
- **Servidor está DOWN agora**: sem processo `llama-server`, `:8000` responde HTTP 000.
- O `server.log` **termina abruptamente** logo após:
  `W srv alloc: - making room for prompt cache entry, removing oldest entry (size = 885.132 MiB)`
  — sem mensagem de shutdown limpo → cara de crash durante alocação.
- Config do processo: `--cache-ram 10240` (10 GB) + `--ctx-checkpoints 8`, host com **16 GB** RAM
  total. `CLAUDE.md` alerta explicitamente: roda em LXC/Proxmox "prone to OOM on long prompts".
- Prompts do run chegaram a **104.296 tokens** (perto do teto 106.496) → checkpoints/cache enormes.

## Evidência contra / a checar
- Não confirmei o **OOM killer** no `dmesg` (indisponível no ambiente). Pode ter sido outro sinal
  (ex.: kill externo). Precisa checar `dmesg`/`journalctl -k` no host real.
- Poderia ter sido encerrado por outra causa (mas não houve shutdown limpo no log).

## Como investigar
1. No host: `dmesg -T | grep -i oom` / `journalctl -k | grep -i "killed process"` para confirmar
   OOM do `llama-server`.
2. Monitorar RAM durante uso agêntico pesado (`free -h`, `nvidia-smi`) e ver se aproxima de 16 GB.
3. Recalcular orçamento: VRAM (modelo) + `cache-ram` (10 GB) + checkpoints + SO. Ver se cabe em 16 GB.

## Confirmação / refutação
- **Confirma** se `dmesg` mostrar o kernel matando o `llama-server` por OOM perto do timestamp do
  fim do log.
- **Refuta** se o processo caiu por outra razão (segfault, sinal externo) — aí investigar core/stderr.

## Correção provável (se confirmada)
- Reduzir `CACHE_RAM` (ex.: 10240 → 2048–4096) e/ou `CTX_CHECKPOINTS`; limitar o contexto efetivo
  (compactação no cliente, H01); adicionar supervisão (systemd com restart automático) para o
  servidor voltar sozinho após um crash. Considerar mais RAM no container.

## Ação imediata sugerida
O servidor está **fora do ar** — subir de novo (`make start-bg` / setsid) para restaurar produção,
e então aplicar as mitigações acima.
