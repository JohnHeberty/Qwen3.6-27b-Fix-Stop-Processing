# Infrastructure & Benchmarking

Production configuration and optimization reports for Qwen3.6 GGUF models on RTX 3090.

Reports are organized **by model first, then by KV cache data type** (`-ctk`/`-ctv`), since cache type affects all benchmarks.

## Active Config

See [configs/current.md](configs/current.md) for the current production parameters.

## Qwen3.6-35B-A3B-MTP-GGUF (MoE, 3B active/token) — active default

> **q4_0 is the best cache type for this model** — fastest at long context AND supports ~104k vs ~88k (q5_1) / ~72k (q8_0) before the performance collapse. See the comparison table in [reports/35b-a3b/q4_0/README-a3b.md](reports/35b-a3b/q4_0/README-a3b.md). Production config not finalized yet — check [configs/current.md](configs/current.md) for what's actually running.

### q4_0 (4-bit) — recommended for this model

Sweeps and benchmarks using `CACHE_TYPE_K/V=q4_0`, llama.cpp built with `GGML_CUDA_FA_ALL_QUANTS=ON`:

| Report | Model | Description |
|---|---|---|
| [MTP Sweep](reports/35b-a3b/q4_0/README-mtp-sweep-a3b.md) | Q4_K_M (UD) | MTP n=1-6 optimization, n=2 @ 155.7 tok/s (8k) |
| [Context Sweep](reports/35b-a3b/q4_0/README-a3b.md) | Q4_K_M (UD) | Context 8k→104k with MTP n=2 (111-150 tok/s), collapses at 112k+ |

### q5_1 (5-bit) — intermediate, kept for comparison

Sweeps and benchmarks using `CACHE_TYPE_K/V=q5_1`:

| Report | Model | Description |
|---|---|---|
| [MTP Sweep](reports/35b-a3b/q5_1/README-mtp-sweep-a3b.md) | Q4_K_M (UD) | MTP n=1-6 optimization, n=1/n=2 tied @ ~148 tok/s (8k) |
| [Context Sweep](reports/35b-a3b/q5_1/README-a3b.md) | Q4_K_M (UD) | Context 8k→88k with MTP n=2 (110-152 tok/s), collapses at 96k+ |

### q8_0 (8-bit) — superseded by q4_0 for this model, kept for comparison

Sweeps and benchmarks using `CACHE_TYPE_K/V=q8_0`:

| Report | Model | Description |
|---|---|---|
| [MTP Sweep](reports/35b-a3b/q8_0/README-mtp-sweep-a3b.md) | Q4_K_M (UD) | MTP n=1-6 optimization, n=2 @ 142.7 tok/s (8k) |
| [Context Sweep](reports/35b-a3b/q8_0/README-a3b.md) | Q4_K_M (UD) | Context 8k→72k with MTP n=2 (112-143 tok/s), collapses at 80k+ |

## Qwen3.6-27B-MTP-GGUF (dense) — legacy, still supported

### q8_0 (8-bit)

Sweeps and benchmarks using `CACHE_TYPE_K/V=q8_0`:

| Report | Model | Description |
|---|---|---|
| [Q5 Full Sweep](reports/27b-dense/q8_0/README-q5.md) | Q5_K_M | Context 8k→80k with MTP n=2 |
| [Q4 Full Sweep](reports/27b-dense/q8_0/README-q4.md) | Q4_K_M | Context 8k→131072 with MTP n=2 |
| [Q6 Full Sweep](reports/27b-dense/q8_0/README-q6.md) | Q6_K | Context 8k→56k (no MTP) |
| [MTP Sweep Q5](reports/27b-dense/q8_0/README-mtp-sweep-q5.md) | Q5_K_M | MTP n=1-6 optimization |
| [MTP Sweep Q4](reports/27b-dense/q8_0/README-mtp-sweep-q4.md) | Q4_K_M | MTP n=1-6 optimization |

### q5_1 (5-bit) — reconstruído com FA_ALL_QUANTS=ON

Sweeps e benchmarks usando `CACHE_TYPE_K/V=q5_1`:

| Report | Model | Description |
|---|---|---|
| [MTP Sweep Q4](reports/27b-dense/q5_1/README-mtp-sweep-q4.md) | Q4_K_M | MTP n=1-6 optimization, pós-rebuild |
| [Context Sweep Q4](reports/27b-dense/q5_1/README-context-sweep-q4.md) | Q4_K_M | Context 8k→131k, MTP n=2, q5_1 (35.2 tok/s @128k) |
| [Q5 Sweep](reports/27b-dense/q5_1/README-q5-sweep.md) | Q5_K_M | MTP + Context, q5_1, colapso VRAM >104k |

### q4_0 (4-bit) — reconstruído com FA_ALL_QUANTS=ON

Sweeps e benchmarks usando `CACHE_TYPE_K/V=q4_0`:

| Report | Model | Description |
|---|---|---|
| [MTP Sweep Q4](reports/27b-dense/q4_0/README-mtp-sweep-q4.md) | Q4_K_M | MTP n=1-6 optimization, n=2 @ 56.6 tok/s |
| [Context Sweep Q4](reports/27b-dense/q4_0/README-context-sweep-q4.md) | Q4_K_M | Context 8k→131k, MTP n=2, q4_0 (37.7 tok/s @128k) |
| [Q5 Sweep](reports/27b-dense/q4_0/README-q5-sweep.md) | Q5_K_M | MTP + Context, q4_0, suporta 128k (36.1 tok/s) |

## Raw Data

- `data/` — Raw benchmark JSON/CSV output (TODO)
- `images/` — Graphs and comparison charts (TODO)
