# env-examples/

Cada subpasta contém um `.env.example` otimizado para aquele modelo específico.
Copie o arquivo correspondente para a raiz como `.env` e ajuste os paths.

O perfil atual de Qwen3.8 usa o llama.cpp `b10502` em
`/root/llama.cpp-b10502/build-cuda`. `LLAMA_BUILD_DIR` permite que os alvos de
build do Makefile preservem esse nome de diretório e o RPATH das bibliotecas.

| Pasta | Modelo | Engine | Contexto | Obs |
|---|---|---|---|---|
| `2xGPU/qwen38-27b-dflash2-tp2/` | Qwen3.8-27B Frozenlock INT4 + z-lab DFlash2 | vLLM TP=2 | 96k | Produção rápida para texto: 7 drafts, tools, reasoning low; prefix cache desligado. |
| `2xGPU/qwen38-27b-ud-q4-k-xl-mtp/` | Qwen3.8-27B UD-Q4_K_XL | llama.cpp | 2×256k | Perfil atual: KV q8, MTP n=3 e visão na CPU/RAM. |
| `2xGPU/qwen38-27b-q8-mtp/` | Qwen3.8-27B Q8_0 | llama.cpp | 256k | Uma requisição; visão nativa. |
| `ornith-q4kxl/` | Ornith-1.0-35B Q4_K_XL | llama.cpp | 128k (96k+32k) | **Em uso.** Q5/Q6 shared + Q4 experts. |
| `ornith/` | Ornith-1.0-35B Q4_K_M | llama.cpp | 128k (96k+32k) | Q4 tudo. Mais leve (21 GB). |
| `qwen3.6-27b-dense/` | Qwen3.6-27B Q5_K_M | llama.cpp | 104k | Denso, mais lento mas melhor reasoning. |
| `qwen3.6-35b-a3b/` | Qwen3.6-35B-A3B Q4_K_M | llama.cpp | 104k | MoE, rápido (~100 tok/s). MTP habilitado. |
