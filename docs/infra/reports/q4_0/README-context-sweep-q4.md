# Context Sweep — Q4_K_M / q4_0 KV Cache (MTP n=2)

**Model:** `Qwen3.6-27B-Q4_K_M.gguf` (~17.1 GB)
**Source:** [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)
**Template:** froggeric v21.3 (`data/templates/custom/chat_template_v21.jinja`)
**MTP:** enabled, 2 draft tokens (`--spec-type draft-mtp --spec-draft-n-max 2`)

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

All measurements: **Q4_K_M** · `--n-gpu-layers -1` · `--parallel 1` · `--cache-type-k q4_0` · `--cache-type-v q4_0` · `--batch-size 4096` · `--ctx-checkpoints 8` · **MTP enabled (2 draft tokens)** · Debian 12 · Driver 590.48.01 · CUDA 12.8.

llama.cpp rebuild com `CUDA_ARCHITECTURES=86` + `GGML_CUDA_FA_ALL_QUANTS=ON`.

Inference: ~250k token PDF (Reinforcement Learning book) truncated to 90% of N_CTX.

| N_CTX | Context | tok/s | TTFT | Prefill t/s | VRAM used | VRAM free | Status |
|---|---|---|---|---|---|---|---|
| 8,192 | 8k | **56.2** | 3.41s | 1065.2 | 16,854 MiB | 7,272 MiB | ok |
| 16,384 | 16k | **56.0** | 66.55s* | 1152.3 | 17,048 MiB | 7,078 MiB | ok |
| 24,576 | 24k | 52.2 | 12.63s | 1138.4 | 17,272 MiB | 6,854 MiB | ok |
| 32,768 | 32k | 50.4 | 18.04s | 1121.1 | 17,496 MiB | 6,630 MiB | ok |
| 40,960 | 40k | 51.4 | 25.01s | 1090.1 | 17,716 MiB | 6,410 MiB | ok |
| 49,152 | 48k | 48.2 | 31.43s | 1061.6 | 17,940 MiB | 6,186 MiB | ok |
| 57,344 | 56k | 47.4 | 38.48s | 1029.9 | 18,168 MiB | 5,958 MiB | ok |
| 65,536 | 64k | 45.6 | 45.74s | 1000.9 | 18,362 MiB | 5,764 MiB | ok |
| 73,728 | 72k | 44.7 | 53.55s | 973.8 | 18,586 MiB | 5,540 MiB | ok |
| 81,920 | 80k | 43.6 | 61.62s | 944.3 | 18,810 MiB | 5,316 MiB | ok |
| 90,112 | 88k | 42.5 | 69.82s | 921.1 | 19,034 MiB | 5,092 MiB | ok |
| 98,304 | 96k | 41.9 | 79.18s | 895.2 | 19,254 MiB | 4,872 MiB | ok |
| 106,496 | 104k | 41.3 | 88.63s | 872.9 | 19,482 MiB | 4,644 MiB | ok |
| 114,688 | 112k | 39.1 | 98.37s | 849.4 | 19,706 MiB | 4,420 MiB | ok |
| 122,880 | 120k | 38.8 | 108.42s | 828.7 | 19,930 MiB | 4,196 MiB | ok |
| 131,072 | 128k | **37.7** | 151.51s | 807.7 | 20,156 MiB | 3,970 MiB | ok **max** |

*TTFT alto em 16k é artefato (primeira execução após restart).

## Comparação q4_0 vs q5_1 vs q8_0 (Q4_K_M, MTP n=2)

| Contexto | q4_0 | q5_1 | q8_0 | Δ q4_0→q8_0 | q4_0 VRAM | q8_0 VRAM |
|---|---|---|---|---|---|---|
| 8k | **56.2** | 55.7 | 56.5 | -0.5% | 16,854 | 16,986 |
| 40k | **51.4** | 48.0 | 49.1 | +4.7% | 17,716 | 18,356 |
| 80k | **43.6** | 41.3 | 44.4 | -1.8% | 18,810 | 20,090 |
| 128k | **37.7** | 35.2 | 39.0 | -3.3% | **20,156** | **22,202** |

**q4_0 é a melhor KV cache de baixa bit:** mais rápida que q5_1 (37.7 vs 35.2 @128k) e economiza **2.046 MiB** vs q8_0, com apenas 3.3% de penalidade em tok/s.

## Configuração recomendada (q4_0)

```
N_CTX=131072
ENABLE_MTP=true
MTP_TOKENS=2
CACHE_TYPE_K=q4_0
CACHE_TYPE_V=q4_0
CTX_CHECKPOINTS=8
CACHE_RAM=10240
```

q4_0 é o melhor custo-benefício para contexto longo: economia de ~2 GB VRAM vs q8_0 com perda mínima de desempenho (0.5-3%).
