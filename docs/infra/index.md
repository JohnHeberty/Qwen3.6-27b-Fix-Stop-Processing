# Infrastructure & Benchmarking

Production configuration and optimization reports for Qwen3.6-27B-MTP-GGUF on RTX 3090.

## Active Config

See [configs/current.md](configs/current.md) for the current production parameters.

## Reports by KV Cache Type

Reports are organized by KV cache data type (`-ctk`/`-ctv`), since cache type affects all benchmarks.

### q8_0 (8-bit) — active default

Sweeps and benchmarks using `CACHE_TYPE_K/V=q8_0`:

| Report | Model | Description |
|---|---|---|
| [Q5 Full Sweep](reports/q8_0/README-q5.md) | Q5_K_M | Context 8k→80k with MTP n=2 |
| [Q4 Full Sweep](reports/q8_0/README-q4.md) | Q4_K_M | Context 8k→131072 with MTP n=2 |
| [Q6 Full Sweep](reports/q8_0/README-q6.md) | Q6_K | Context 8k→56k (no MTP) |
| [MTP Sweep Q5](reports/q8_0/README-mtp-sweep-q5.md) | Q5_K_M | MTP n=1-6 optimization |
| [MTP Sweep Q4](reports/q8_0/README-mtp-sweep-q4.md) | Q4_K_M | MTP n=1-6 optimization |

### q5_1 (5-bit) — reconstruído com FA_ALL_QUANTS=ON

Sweeps e benchmarks usando `CACHE_TYPE_K/V=q5_1`:

| Report | Model | Description |
|---|---|---|
| [MTP Sweep Q4](reports/q5_1/README-mtp-sweep-q4.md) | Q4_K_M | MTP n=1-6 optimization, pós-rebuild |
| [Context Sweep Q4](reports/q5_1/README-context-sweep-q4.md) | Q4_K_M | Context 8k→131k, MTP n=2, q5_1 (35.2 tok/s @128k) |
| [Q5 Sweep](reports/q5_1/README-q5-sweep.md) | Q5_K_M | MTP + Context, q5_1, colapso VRAM >104k |

### q4_0 (4-bit) — reconstruído com FA_ALL_QUANTS=ON

Sweeps e benchmarks usando `CACHE_TYPE_K/V=q4_0`:

| Report | Model | Description |
|---|---|---|
| [MTP Sweep Q4](reports/q4_0/README-mtp-sweep-q4.md) | Q4_K_M | MTP n=1-6 optimization, n=2 @ 56.6 tok/s |
| [Context Sweep Q4](reports/q4_0/README-context-sweep-q4.md) | Q4_K_M | Context 8k→131k, MTP n=2, q4_0 (37.7 tok/s @128k) |
| [Q5 Sweep](reports/q4_0/README-q5-sweep.md) | Q5_K_M | MTP + Context, q4_0, suporta 128k (36.1 tok/s) |

## Raw Data

- `data/` — Raw benchmark JSON/CSV output (TODO)
- `images/` — Graphs and comparison charts (TODO)
