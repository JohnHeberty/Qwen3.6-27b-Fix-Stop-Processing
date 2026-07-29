# Qwen3.6-35B-A3B (MoE) Benchmark (MTP n=2)

**Model:** `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` (~22.6 GB, MoE: 256 experts, 8 ativos/token, 1 MTP head)
**Source:** [unsloth/Qwen3.6-35B-A3B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF)
**Template:** froggeric v21.3 (`data/templates/custom/chat_template_v21.jinja`)
**MTP:** enabled, 2 draft tokens (`--spec-type draft-mtp --spec-draft-n-max 2`)

> **q4_0 KV cache outperforms q8_0 for this model** — faster at every context tested AND stable up to ~104k instead of ~72k. See [reports/35b-a3b/q4_0/README-a3b.md](../q4_0/README-a3b.md) for the full comparison. This q8_0 report is kept for reference.

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

All measurements: **Q4_K_M (UD)** · `--n-gpu-layers -1` · `--parallel 1` · `--cache-type-k q8_0` · `--cache-type-v q8_0` · `--batch-size 4096` · `--ctx-checkpoints 8` · `--cache-ram 10240` · **MTP enabled (2 draft tokens)** · Debian 12 · Driver 590.48.01 · CUDA 12.8.
Inference: ~250k token PDF (Reinforcement Learning book) truncated to 90% of N_CTX.
Benchmark: `usage.completion_tokens` do servidor via `stream_options.include_usage`.

| `N_CTX` | Context | tok/s | TTFT | Prefill t/s | MTP acceptance | VRAM used | VRAM free | Status |
|---|---|---|---|---|---|---|---|---|
| 8,192 | 8k | **139.0** | 1.56s | 2.367,8 | 65,6% | 21,882 MiB | 2,244 MiB | ok |
| 16,384 | 16k | 135.2 | 3.24s | 2.650,2 | 64,8% | 22,006 MiB | 2,120 MiB | ok |
| 24,576 | 24k | 137.6 | 5.40s | 2.692,7 | 71,4% | 22,132 MiB | 1,994 MiB | ok |
| 32,768 | 32k | 129.4 | 7.68s | 2.662,5 | 63,8% | 22,264 MiB | 1,862 MiB | ok |
| 40,960 | 40k | 129.5 | 10.55s | 2.598,8 | 69,8% | 22,394 MiB | 1,732 MiB | ok |
| 49,152 | 48k | 121.5 | 13.19s | 2.552,0 | 66,4% | 22,526 MiB | 1,600 MiB | ok |
| 57,344 | 56k | 121.7 | 16.04s | 2.486,9 | 65,9% | 22,660 MiB | 1,466 MiB | ok |
| 65,536 | 64k | 112.1 | 18.94s | 2.429,6 | 63,3% | 22,792 MiB | 1,334 MiB | ok |
| **73,728** | **72k** | **115.9** | **22.03s** | **2.373,3** | **71,2%** | **22,926 MiB** | **1,200 MiB** | **ok — padrão de produção** |
| 81,920 | 80k | 10.6 ⚠️ | 35.05s | 1.663,0 | 65,8% | 22,592 MiB | 1,534 MiB | ok (colapso de desempenho) |
| 90,112 | 88k | 11.0 ⚠️ | 40.23s | 1.600,7 | 66,4% | 22,726 MiB | 1,400 MiB | ok (colapso de desempenho) |
| 98,304 | 96k | 10.5 ⚠️ | 42.58s | 1.666,3 | 67,1% | 22,858 MiB | 1,268 MiB | ok (colapso de desempenho) |
| 106,496 | 104k | 12.0 ⚠️ | 48.22s | 1.606,1 | 66,2% | 22,992 MiB | 1,134 MiB | ok (colapso de desempenho) |
| 114,688 | 112k | 6.7 ⚠️ | 55.29s | 1.513,9 | 64,1% | 23,036 MiB | 1,090 MiB | ok (colapso de desempenho) |
| 122,880 | 120k | 6.4 ⚠️ | 63.09s | 1.426,6 | 71,4% | 23,008 MiB | 1,118 MiB | ok (colapso de desempenho) |
| 131,072 | 128k | 7.6 ⚠️ | 66.30s | 1.449,5 | 61,5% | 22,976 MiB | 1,150 MiB | ok — completou, mas inútil |

## Conclusões

- **8k-72k: 112-143 tok/s** — MTP n=2 funciona consistentemente em todo o range útil.
- **72k (73,728) é o teto de produção** — a partir de 80k o tok/s despenca para **6-12 tok/s** (10-20x mais lento), apesar de o script nunca reportar `vram_exhausted` (sempre fica acima de 1,000 MiB livres — o limiar de parada automática é 200 MiB).
- **O colapso não é causado pelo MTP nem pela VRAM técnica:**
  - **MTP acceptance rate:** 61-78% em toda a faixa, inclusive nos contextos com colapso — a queda de tok/s **não** é causada por queda de aceitação do MTP.
  - **Prefill também cai no mesmo ponto:** ~2.370-2.690 t/s até 72k → ~1.450-1.660 t/s de 80k em diante (queda de ~30-40%), então o gargalo afeta prefill *e* decode simultaneamente, não é algo específico do speculative decoding.
  - **TTFT sobe de forma desproporcional:** de 72k (22.0s) para 80k (35.1s) o TTFT quase dobra, um salto muito maior que o aumento de ~10% no tamanho do prompt sugeriria — sinal de que algo estrutural muda nesse ponto (provável spillover de cache de prompt para RAM via `CTX_CHECKPOINTS`/`CACHE_RAM`, não esgotamento de VRAM). Mesmo padrão observado historicamente no modelo 27B denso.
- **VRAM cresce lentamente com contexto:** 21.9 GB (8k) → 23.0 GB (128k) — só ~1.1 GB de crescimento em 120k tokens adicionais, muito menos que o modelo denso, porque o overhead de KV cache por token é pequeno comparado ao peso fixo dos experts (~21.5 GB carregados independente do contexto).
- **~2.5x mais rápido que o 27B dense** no range útil (72k: 115.9 vs ~41.7-46.4 tok/s do 27B Q4_K_M/Q5_K_M — ver [reports/27b-dense/q8_0/README-q4.md](../../27b-dense/q8_0/README-q4.md)), consistente com o modelo MoE ativar só ~3B parâmetros por token contra 27B do modelo denso.

## Configuração do servidor

**Padrão (produção):**
```
MODEL_FILE=Qwen3.6-35B-A3B-UD-Q4_K_M.gguf
N_CTX=73728            # 72k — teto de desempenho útil, ver tabela acima
ENABLE_MTP=true
MTP_TOKENS=2
CACHE_TYPE_K=q8_0
CACHE_TYPE_V=q8_0
CTX_CHECKPOINTS=8
CACHE_RAM=10240
TEMPLATE_FILE=data/templates/custom/chat_template_v21.jinja
```

> **Não aumente `N_CTX` além de 73728 sem testar primeiro** — o sweep completo mostra colapso de desempenho (não crash) a partir de 80k. Ver tabela completa acima.

## MTP Sweep

Veja [README-mtp-sweep-a3b.md](README-mtp-sweep-a3b.md) para o sweep completo de MTP n=1-6 (mesmas colunas: tok/s, prefill, TTFT, aceitação, VRAM).

## Hardware

| Component | Minimum | Tested/Validated |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | **Zotac GeForce RTX 3090 Trinity OC — 24,576 MiB VRAM** ✓ |
| RAM | 16 GB | 32 GB |
| Free disk space | 25 GB | 30 GB |

> O modelo Q4_K_M (UD) usa ~21.5 GB de VRAM só para os pesos (todos os 256 experts carregados na GPU, apesar de só 8/token estarem ativos na inferência). Com 24,576 MiB (RTX 3090) e KV cache q8_0, restam ~1.2-2.2 GB para KV cache, suficiente para até **72k tokens** de contexto com MTP n=2 speculative decoding a ~112-143 tok/s (benchmarked).

**Tested on:** Zotac GeForce RTX 3090 Trinity OC · 24,576 MiB VRAM · Driver 590.48.01 · Debian 12 · CUDA 12.8
