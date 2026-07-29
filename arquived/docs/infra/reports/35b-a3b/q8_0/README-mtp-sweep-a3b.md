# MTP Sweep — Qwen3.6-35B-A3B (MoE) no llama.cpp

## Metodologia

- **Modelo:** `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` (~22.6 GB, MoE: 256 experts, 8 ativos/token)
- **GPU:** RTX 3090 (24,576 MiB VRAM)
- **Engine:** llama.cpp (`--spec-type draft-mtp`)
- **Contexto:** 8k (prompt ~7,372 tokens, 90% fill)
- **Geração:** ~2,048 tokens, temperatura 0.3
- **Benchmark:** `usage.completion_tokens` do servidor via `stream_options.include_usage`
- **KV cache:** q8_0, CTX_CHECKPOINTS=8, CACHE_RAM=10240

> **Nota:** este sweep é com cache q8_0. O cache q4_0 é mais rápido em todo `MTP_TOKENS` testado (ex.: n=2 155.7 vs 142.7 tok/s) — ver [reports/35b-a3b/q4_0/README-mtp-sweep-a3b.md](../q4_0/README-mtp-sweep-a3b.md).

O GGUF deste modelo embute apenas **1 MTP head** (`qwen35moe.nextn_predict_layers=1`), contra 3 no modelo 27B denso. O llama.cpp ainda aceita `--spec-draft-n-max` acima de 1 e drafta de forma recursiva com esse único head — não há erro, apenas queda de aceitação mais rápida que no modelo denso.

## Resultados

| `MTP_TOKENS` | tok/s | Prefill t/s | TTFT | Draft total | Aceitos | % aceitação | tok/call | VRAM used | VRAM free |
|---|---|---|---|---|---|---|---|---|---|
| n=1 | 133,3 | 2.334,4 | 1,60s | 1.086 | 848 | 78,1% | 0,78 | 21.818 MiB | 2.308 MiB |
| **n=2** | **142,7** | **2.313,1** | **1,58s** | **1.682** | **1.205** | **71,6%** | **1,43** | **21.882 MiB** | **2.244 MiB** |
| n=3 | 134,3 | 2.334,8 | 1,60s | 1.938 | 1.046 | 54,0% | 1,62 | 21.976 MiB | 2.150 MiB |
| n=4 | 129,2 | 2.389,9 | 1,55s | 2.592 | 1.164 | 44,9% | 1,80 | 22.044 MiB | 2.082 MiB |
| n=5 | 125,2 | 2.463,9 | 1,51s | 2.875 | 1.156 | 40,2% | 2,01 | 22.108 MiB | 2.018 MiB |
| n=6 | 118,1 | 2.379,4 | 1,55s | 3.956 | 1.387 | 35,1% | 2,11 | 22.170 MiB | 1.956 MiB |

`tok/call = % aceitação × MTP_TOKENS` — tokens extras aceitos, em média, por rodada de draft. Note que **tok/call sobe continuamente** de n=1 a n=6 (0,78 → 2,11) mesmo com tok/s caindo — cada rodada aceita mais tokens em termos absolutos, mas o overhead de gerar/validar drafts maiores cresce mais rápido que esse ganho, por isso o throughput final piora.

## Análise

**MTP n=2 é o ótimo** (142,7 tok/s, +7,1% sobre n=1). O padrão é idêntico ao observado no modelo 27B denso — cada token de draft adicional reduz a aceitação mais rápido do que o ganho marginal compensa:

- n=1 → n=2: +7,1% (133,3 → 142,7)
- n=2 → n=3: -5,9% (142,7 → 134,3)
- n=3 → n=4: -3,8% (134,3 → 129,2)
- n=4 → n=5: -3,1% (129,2 → 125,2)
- n=5 → n=6: -5,7% (125,2 → 118,1)

TTFT e prefill t/s ficam praticamente constantes em toda a faixa (1,51-1,60s / 2.313-2.464 t/s) — o custo do MTP é todo na fase de *decode*, não no *prefill* do prompt, como esperado (o draft só entra em ação depois do primeiro token).

Notável: mesmo com só 1 MTP head embutida (vs 3 no 27B denso), o llama.cpp consegue draftar recursivamente e ainda assim n=2 vence — o mecanismo de draft recursivo funciona, mas com aceitação caindo mais cedo que no modelo com múltiplos heads nativos.

## Comparação com o modelo 27B denso (mesma metodologia, mesmo cache q8_0)

| `MTP_TOKENS` | 35B-A3B tok/s | 27B Q4_K_M tok/s | Δ |
|---|---|---|---|
| n=1 | 133,3 | 53,3 | +150% |
| **n=2** | **142,7** | **55,4** | **+158%** |
| n=3 | 134,3 | 53,5 | +151% |

O MoE é **~2,5x mais rápido** que o modelo denso em qualquer configuração de MTP — consistente com apenas ~3B parâmetros ativos por token contra os 27B do modelo denso. Decode single-user é limitado por banda de memória (bytes lidos por token), não por FLOPs, então menos parâmetros ativos por token se traduz quase linearmente em mais tok/s.

## Conclusão

Para **llama.cpp + Qwen3.6-35B-A3B (Q4_K_M) + RTX 3090**, o MTP ótimo é **n=2** (142,7 tok/s, +7,1% sobre n=1) — mesmo padrão do modelo denso, apesar de ter só 1 MTP head nativa. Ver [README-a3b.md](README-a3b.md) para o sweep completo de contexto com essa configuração.
