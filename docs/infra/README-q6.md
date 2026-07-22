# Qwen3.6 27B — Q6_K Benchmark

**Model:** `Qwen3.6-27B-Q6_K.gguf` (22.9 GB)
**Source:** [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

**Without MTP** (MTP disabled — recommended for Q6_K due to VRAM constraints):

| `N_CTX` | Context | VRAM used | VRAM free | tok/s | Prompt time | Status |
|---|---|---|---|---|---|---|
| 8,192 | 8k | 21,704 MiB | 2,422 MiB | 29.4 | 3.4 s | ✓ |
| 16,384 | 16k | 22,010 MiB | 2,116 MiB | 28.7 | 70.9 s | ✓ |
| 24,576 | 24k | 22,320 MiB | 1,806 MiB | 27.9 | 13.0 s | ✓ |
| 32,768 | 32k | 22,632 MiB | 1,494 MiB | 27.5 | 19.0 s | ✓ |
| 40,960 | 40k | 22,942 MiB | 1,184 MiB | 26.7 | 25.8 s | ✓ |
| 49,152 | 48k | 23,024 MiB | 1,102 MiB | 4.7 | 37.7 s | ✓ **cliff** |
| 57,344 | 56k | — | — | — | — | ~4 tok/s (KV spill) |

**With MTP** (3 draft tokens — NOT recommended for Q6_K):

| `N_CTX` | Context | VRAM used | VRAM free | tok/s | Status |
|---|---|---|---|---|---|
| 8,192 | 8k | 22,360 MiB | 1,766 MiB | 50.0 | ✓ |
| 16,384 | 16k | 22,410 MiB | 1,716 MiB | 9.3 | ✓ **cliff** |

## Conclusões

- **Q6_K occupies 93% of RTX 3090 VRAM** just for model weights (22.9 GB / 24 GB).
- **Without MTP:** 8k-40k works at ~27-29 tok/s. Cliff at 48k (KV cache spills to system RAM → 4.7 tok/s).
- **With MTP:** Only 8k works well (50 tok/s). 16k already drops to 9.3 tok/s — MTP draft heads consume the last ~650 MiB of VRAM headroom.
- **No context above 48k is usable** — performance collapses completely.
- **Q6_K is SLOWER than Q4_K_M at every context size** despite better weight precision, because:
  - Less VRAM headroom → KV cache pressure
  - MTP acceptance rate drops (more weight precision ≠ more MTP hits on a tight VRAM budget)
  - The "quality advantage" of Q6 over Q4 is minimal for most tasks

## Comparação: Q6_K vs Q5_K_M vs Q4_K_M

| Métrica | Q6_K | Q5_K_M | Q4_K_M |
|---|---|---|---|
| Modelo | 22.9 GB | 19.8 GB | 17.1 GB |
| VRAM livre (após load, 8k) | 2,422 MiB | ~4,200 MiB | 6,962 MiB |
| tok/s @ 8k (MTP on) | 50.0 | ~73 | 53.5 |
| tok/s @ 8k (MTP off) | 29.4 | ~48 | ~35 |
| tok/s @ 40k | 26.7 (no MTP) | ~60 | 47.6 |
| Contexto max (usável) | 40k | 88k | 120k |
| VRAM livre @ 40k | 1,184 MiB | ~2,000 MiB | 5,588 MiB |

## Recomendações

**RTX 3090 (24 GB): Use Q4_K_M ou Q5_K_M — NÃO Q6_K.**

Q6_K é um downgrade na prática:
- **20-30% mais lento** que Q4_K_M em qualquer contexto
- **Contexto máximo 40k** vs 120k no Q4
- **MTP inútil** acima de 8k (VRAM insuficiente)
- A diferença de qualidade Q6→Q4 é imperceptível para a maioria das tarefas

Q6_K só faz sentido com GPUs de **48+ GB** (A6000, A100, H100).

## Hardware

| Component | Minimum | Tested/Validated |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | **Zotac GeForce RTX 3090 Trinity OC — 24,576 MB VRAM** ✓ |
| RAM | 16 GB | 32 GB |
| Free disk space | 25 GB | 30 GB |

> The Q6_K model uses ~23 GB of VRAM. With 24,576 MB (RTX 3090), only ~1,100-2,400 MiB remain for KV cache. Without MTP, 40k context works at ~27 tok/s. With MTP, only 8k is usable. **For RTX 3090, use Q4_K_M or Q5_K_M instead.**

**Tested on:** Zotac GeForce RTX 3090 Trinity OC · 24,576 MB VRAM · Driver 590.48.01 · Debian 12 · CUDA 12.8
