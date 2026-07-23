# Qwen3.6-35B-A3B (MoE) Benchmark — q5_1 KV Cache (MTP n=2)

**Model:** `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` (~22.6 GB, MoE: 256 experts, 8 ativos/token, 1 MTP head)
**Source:** [unsloth/Qwen3.6-35B-A3B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF)
**Template:** froggeric v21.3 (`data/templates/custom/chat_template_v21.jinja`)
**MTP:** enabled, 2 draft tokens (`--spec-type draft-mtp --spec-draft-n-max 2`)
**KV Cache:** q5_1 (requer llama.cpp com `GGML_CUDA_FA_ALL_QUANTS=ON`)

> **q4_0 é a recomendação final para este modelo** — mais rápido em contexto longo e com teto de 104k vs 88k deste cache. Ver [reports/35b-a3b/q4_0/README-a3b.md](../q4_0/README-a3b.md). Este relatório é mantido como dado de comparação.

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

All measurements: **Q4_K_M (UD)** · `--n-gpu-layers -1` · `--parallel 1` · `--cache-type-k q5_1` · `--cache-type-v q5_1` · `--batch-size 4096` · `--ctx-checkpoints 8` · `--cache-ram 10240` · **MTP enabled (2 draft tokens)** · Debian 12 · Driver 590.48.01 · CUDA 12.8.
Inference: ~250k token PDF (Reinforcement Learning book) truncated to 90% of N_CTX.
Benchmark: `usage.completion_tokens` do servidor via `stream_options.include_usage`.

| `N_CTX` | Context | tok/s | TTFT | Prefill t/s | MTP acceptance | VRAM used | VRAM free | Status |
|---|---|---|---|---|---|---|---|---|
| 8,192 | 8k | **151.7** | 1.45s | 2.527,7 | 66,7% | 21,856 MiB | 2,270 MiB | ok |
| 16,384 | 16k | 147.9 | 3.09s | 2.756,9 | 66,8% | 21,956 MiB | 2,170 MiB | ok |
| 24,576 | 24k | 141.2 | 5.22s | 2.767,3 | 65,0% | 22,056 MiB | 2,070 MiB | ok |
| 32,768 | 32k | 143.0 | 7.58s | 2.697,7 | 71,0% | 22,164 MiB | 1,962 MiB | ok |
| 40,960 | 40k | 133.0 | 10.26s | 2.662,5 | 65,8% | 22,268 MiB | 1,858 MiB | ok |
| 49,152 | 48k | 127.2 | 12.88s | 2.601,6 | 63,9% | 22,376 MiB | 1,750 MiB | ok |
| 57,344 | 56k | 124.7 | 15.67s | 2.536,3 | 66,1% | 22,484 MiB | 1,642 MiB | ok |
| 65,536 | 64k | 121.7 | 31.10s | 2.467,9 | 66,8% | 22,594 MiB | 1,532 MiB | ok |
| 73,728 | 72k | 115.8 | 21.64s | 2.416,0 | 65,4% | 22,700 MiB | 1,426 MiB | ok |
| 81,920 | 80k | 115.8 | 24.69s | 2.364,8 | 67,1% | 22,808 MiB | 1,318 MiB | ok |
| **90,112** | **88k** | **110.3** | **28.03s** | **2.300,2** | **67,5%** | **22,916 MiB** | **1,210 MiB** | **ok — candidato a produção** |
| 98,304 | 96k | 12.8 ⚠️ | 41.23s | 1.721,0 | 66,2% | 22,558 MiB | 1,568 MiB | ok (colapso de desempenho) |
| 106,496 | 104k | 12.7 ⚠️ | 44.38s | 1.744,4 | 65,3% | 22,666 MiB | 1,460 MiB | ok (colapso de desempenho) |
| 114,688 | 112k | 12.8 ⚠️ | 49.14s | 1.702,7 | 67,5% | 22,774 MiB | 1,352 MiB | ok (colapso de desempenho) |
| 122,880 | 120k | 14.0 ⚠️ | 53.20s | 1.691,2 | 70,3% | 22,882 MiB | 1,244 MiB | ok (colapso de desempenho) |
| 131,072 | 128k | 15.6 ⚠️ | 57.87s | 1.659,8 | 64,7% | 22,986 MiB | 1,140 MiB | ok — completou, mas inútil |

## Conclusões

- **8k-88k: 110-152 tok/s** — range útil maior que q8_0 (72k), menor que q4_0 (104k).
- **Colapso a partir de 96k** — mesmo padrão: queda abrupta (110.3 → 12.8 tok/s), acceptance MTP estável (63-71% em toda a faixa, inclusive pós-colapso), prefill cai ~25% no mesmo ponto.
- **q5_1 é competitivo em contextos pequenos** (8k: 151.7 tok/s, o maior dos três caches testados) mas perde terreno pra q4_0 conforme o contexto cresce — ver comparação abaixo.

## Comparação entre os 3 caches (MTP n=2)

| Contexto | q4_0 | q5_1 | q8_0 |
|---|---|---|---|
| 8k | 148.3 | **151.7** | 139.0 |
| 40k | **134.6** | 133.0 | 129.5 |
| 72k | **122.8** | 115.8 | 115.9 |
| Teto útil | **104k** (106,496) | 88k (90,112) | 72k (73,728) |

**q4_0 vence no que importa mais** (contexto longo e teto máximo). q5_1 é uma opção intermediária se por algum motivo q4_0 não estiver disponível (build sem `FA_ALL_QUANTS`, por exemplo — mas ambos precisam do mesmo flag de build, então isso não é um cenário real aqui).

## Configuração do servidor

Não recomendado como padrão — ver [reports/35b-a3b/q4_0/README-a3b.md](../q4_0/README-a3b.md) para a configuração final.

## MTP Sweep

Veja [README-mtp-sweep-a3b.md](README-mtp-sweep-a3b.md) — n=1 e n=2 ficam praticamente empatados neste cache específico.

**Tested on:** Zotac GeForce RTX 3090 Trinity OC · 24,576 MiB VRAM · Driver 590.48.01 · Debian 12 · CUDA 12.8
