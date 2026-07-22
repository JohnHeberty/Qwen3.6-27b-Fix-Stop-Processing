# Qwen3.6 27B — Q4_K_M Benchmark

**Model:** `Qwen3.6-27B-Q4_K_M.gguf` (~17.1 GB)
**Source:** [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

> **⚠ BENCHMARK PENDENTE** — Modelo baixado, benchmark ainda não executado.
> Execute o benchmark e preencha a tabela abaixo.

All measurements: **Q4_K_M** · `--n-gpu-layers -1` · `--parallel 1` · `--cache-type-k q8_0` · `--cache-type-v q8_0` · `--batch-size 4096` · **MTP enabled (3 draft tokens)** · Debian · Driver 590.48.01.
Inference: ~250k token PDF (Reinforcement Learning book) truncated to 90% of N_CTX.

| `N_CTX` | Context | VRAM used | VRAM free | RAM Δ | tok/s | Prompt time | Status |
|---|---|---|---|---|---|---|---|
| 8,192 | 8k | — | — | — | — | — | — |
| 16,384 | 16k | — | — | — | — | — | — |
| 24,576 | 24k | — | — | — | — | — | — |
| 32,768 | 32k | — | — | — | — | — | — |
| 40,960 | 40k | — | — | — | — | — | — |
| 49,152 | 48k | — | — | — | — | — | — |
| 57,344 | 56k | — | — | — | — | — | — |
| 65,536 | 64k | — | — | — | — | — | — |
| 73,728 | 72k | — | — | — | — | — | — |
| 81,920 | 80k | — | — | — | — | — | — |
| 90,112 | 88k | — | — | — | — | — | — |
| 98,304 | 96k | — | — | — | — | — | — |
| 106,496 | 104k | — | — | — | — | — | — |
| 114,688 | 112k | — | — | — | — | — | — |
| 122,880 | 120k | — | — | — | — | — | — |
| 131,072 | 128k | — | — | — | — | — | — |

## Expected vs Q5_K_M

Q4_K_M é ~2GB menor que Q5_K_M (~17.1 GB vs ~19 GB). Isso deve liberar mais VRAM para KV cache, potencialmente permitindo:
- Contexto maior estável (possivelmente > 88k antes do ponto de inflexão)
- Mais margem para picos de VRAM
- Possível melhoria de tok/s devido ao menor modelo

## Como rodar o benchmark

```bash
# Parar servidor atual
make stop

# Editar .env para Q4
# MODEL_FILE=Qwen3.6-27B-Q4_K_M.gguf

# Iniciar e testar cada N_CTX
make start

# Para cada tamanho de contexto:
curl -s http://localhost:8000/health
# Registrar VRAM com: nvidia-smi

# Testar inference:
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3","messages":[{"role":"user","content":"Hello!"}],"max_tokens":256}'
```

## Hardware

| Component | Minimum | Tested/Validated |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | **Zotac GeForce RTX 3090 Trinity OC — 24,576 MB VRAM** ✓ |
| RAM | 16 GB | 32 GB |
| Free disk space | 25 GB | 30 GB |

> The Q4_K_M model uses ~17 GB of VRAM. With 24,576 MB (RTX 3090) and KV cache q8_0, ~7 GB remain for KV cache — potentially more context than Q5_K_M.

**Tested on:** Zotac GeForce RTX 3090 Trinity OC · 24,576 MB VRAM · Driver 590.48.01 · Debian 12 · CUDA 12.8
