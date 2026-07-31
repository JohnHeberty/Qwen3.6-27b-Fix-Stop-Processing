# env-examples/

Cada subpasta contém um `.env.example` otimizado para aquele modelo específico.
Copie o arquivo correspondente para a raiz como `.env` e ajuste os paths.

| Pasta | Modelo | Engine | Contexto | Obs |
|---|---|---|---|---|
| `ornith/` | Ornith-1.0-35B Q4_K_M | llama.cpp | 128k (96k+32k) | **Em uso.** Config oficial Ornith. |
| `qwen3.6-27b-dense/` | Qwen3.6-27B Q5_K_M | llama.cpp | 104k | Denso, mais lento mas melhor reasoning. |
| `qwen3.6-35b-a3b/` | Qwen3.6-35B-A3B Q4_K_M | llama.cpp | 104k | MoE, rápido (~100 tok/s). MTP habilitado. |
