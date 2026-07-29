# Baseline llama.cpp — medido antes da migração para vLLM

Medido em **2026-07-29**, imediatamente antes do corte, para que a migração possa ser julgada
contra um número real em vez de estimativa.

## Configuração medida

| | |
|---|---|
| Engine | `llama-server` (llama.cpp), build 865 / e8f19cc |
| Modelo | `Qwen3.6-27B-Q5_K_M.gguf` (19,8 GB) |
| KV cache | `q4_0` (K e V) |
| MTP | ligado, `n=2` |
| Contexto | `N_CTX=106496` |
| Sampling | temp 0.6 · top_k 20 · top_p 0.95 · presence 1.5 · reasoning-budget 2048 |
| GPU | RTX 3090 24 GB (Ampere sm_86), driver 590.48.01, CUDA 12.8 |

## Resultados

Ferramenta: `tests/bench_decode.py` — conta `usage.completion_tokens` do servidor (nunca chunks
SSE), nonce por execução para invalidar o prefix cache, 1 warm-up + 3 medidas, mediana.

| Prompt | decode tok/s | TTFT | prefill tok/s |
|---|---|---|---|
| 7.761 tok (~8k) | **58,27** (56,83–60,01) | 7,17 s | 1.156,6 |
| 23.191 tok (~24k) | **55,95** (53,04–56,52) | 22,14 s | 1.088,4 |

A medição do cliente bateu **exatamente** com o `predicted_per_second` reportado pelo próprio
llama.cpp nas duas faixas — o método está correto.

## Correção de duas afirmações do repositório

**1. O benchmark não estava quebrado.** O `MAXIMIZE-TOKS.md` e o `CLAUDE.md` afirmavam que
`tests/benchmark.py` contava chunks SSE (`if content: token_count += 1`). O arquivo já usava
`stream_options.include_usage` e `tok_per_sec = completion_tokens / gen_time`. A crítica era válida
quando foi escrita, mas foi corrigida antes desta medição — os dois documentos é que ficaram
desatualizados.

**2. O baseline real é bem melhor que o assumido.** O `MAXIMIZE-TOKS.md` partia de "47,6–50 tok/s".
Aqueles números vinham do *sweep* de contexto, que preenche 90% da janela — carga muito mais pesada
que o uso típico. Na faixa comparável ao número publicado pelo devnen (~24k), estamos em **55,95**.

## O gap real contra o alvo da migração

| Cenário | tok/s |
|---|---|
| devnen, prompt curto (~200 tok) | 72,5 |
| devnen, ~24k, MTP n=6 | 64,5 |
| **este servidor, ~24k, MTP n=2** | **55,95** |

Comparando o que é comparável (~24k contra ~24k): **+15%**, não os ~+44% que a comparação
72,5 × 50 sugeria.
