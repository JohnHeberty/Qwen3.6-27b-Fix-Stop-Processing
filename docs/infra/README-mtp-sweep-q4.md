# MTP Sweep — Q4_K_M no llama.cpp

## Metodologia

- **Modelo:** `Qwen3.6-27B-Q4_K_M.gguf` (17.1 GB)
- **GPU:** RTX 3090 (24,576 MiB VRAM)
- **Engine:** llama.cpp (`--spec-type draft-mtp`)
- **Contexto:** 8k (prompt ~7,372 tokens, 90% fill)
- **Geração:** 2,048 tokens, temperatura 0.3
- **Benchmark:** `usage.completion_tokens` do servidor via `stream_options.include_usage`
- **KV cache:** q8_0, CTX_CHECKPOINTS=8, CACHE_RAM=10240

## Resultados

| `MTP_TOKENS` | tok/s | Draft total | Aceitos | % aceitação | tok/call |
|---|---|---|---|---|---|
| n=1 | 53.3 | 1.133 | 913 | 80,6% | 0,81 |
| **n=2** | **55.4** | **1.596** | **1.115** | **69,9%** | **1,40** |
| n=3 | 53.5 | 2.168 | 1.324 | 61,1% | 1,83 |
| n=4 | 49.0 | 2.774 | 1.352 | 48,7% | 2,05 |
| n=5 | 45.1 | 3.245 | 1.396 | 43,0% | 2,13 |
| n=6 | 44.9 | 3.451 | 1.471 | 42,6% | 2,44 |

## Análise

**MTP n=2 é o ótimo para Q4_K_M no llama.cpp** (55,4 tok/s, +3,9% sobre n=1). Assim como no Q5, a aceitação cai rapidamente após n=2:

- n=1 → n=2: +3,9% (53,3 → 55,4)
- n=2 → n=3: -3,4% (55,4 → 53,5)
- n=3 → n=4: -8,4% (53,5 → 49,0)
- n=4 → n=5: -8,0% (49,0 → 45,1)
- n=5 → n=6: -0,4% (45,1 → 44,9) — ruído

O padrão é idêntico ao Q5: cada token draft adicional reduz a aceitação mais que o ganho marginal compensa.

## Comparação Q4_K_M vs Q5_K_M (MTP sweep)

| `MTP_TOKENS` | Q4 tok/s | Q5 tok/s | Δ |
|---|---|---|---|
| n=1 | 53,3 | 46,6 | +14,4% |
| **n=2** | **55,4** | **52,3** | **+5,9%** |
| n=3 | 53,5 | 51,2 | +4,5% |
| n=4 | 49,0 | 48,2 | +1,7% |
| n=5 | 45,1 | 42,7 | +5,6% |
| n=6 | 44,9 | 43,5 | +3,2% |

Q4_K_M é **4-14% mais rápido** que Q5_K_M em todos os MTP n. O ganho é maior em n=1 (14%) porque o modelo menor tem menos overhead de computação por step.

## Comparação com vLLM devnen

Os resultados do [devnen](https://github.com/devnen/qwen3.6-windows-server) mostram n=6 como ótimo (64,5 tok/s), mas com engine vLLM + INT4:

| Engine | Modelo | Ótimo MTP | tok/s @ 8k | Razão |
|---|---|---|---|---|
| llama.cpp | Q4_K_M (17.1 GB) | n=2 | 55,4 | — |
| vLLM (devnen) | INT4 (16.9 GB) | n=6 | 64,5 | +16% |

A diferença deve-se a:
1. **vLLM integra MTP ao scheduler** — menor overhead por call speculative
2. **Triton Attention + CUDA Graphs** — kernels mais eficientes
3. **KV FP8 E4M3** — cache mais compacto

## Conclusão

Para **llama.cpp + Q4_K_M + RTX 3090**, o MTP ótimo é **n=2** (55,4 tok/s, +3,9% sobre n=1). O comportamento é idêntico ao Q5_K_M — n=2 é o ponto ótimo em ambos. Q4_K_M é ~6% mais rápido que Q5_K_M em todas as configurações de MTP.
