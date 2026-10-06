# Qwen3.8-27B — servidor local de inferência

Stack de produção: **vLLM TP=2 + AutoRound INT4 + DFlash2** em 2× RTX 3090 (48 GB VRAM),
expondo uma API compatível com OpenAI na porta 18020.

- Modelo: `qwen3.8-27b` — denso 27B, híbrido Gated DeltaNet + Atenção
- Engine: vLLM (fork em `qwen38-27b-rtx3090/`, linhagem v0.27.1) + modelo draft
  `z-lab/Qwen3.8-27B-DFlash2` (7 drafts paralelos), alvo `Frozenlock/Qwen3.8-27B-int4-AutoRound`
- Contexto: 96k (pool validado de 96.538 tokens nesta VRAM), ~22 GB VRAM por GPU
- Medido: **~173 tok/s wall / ~177 tok/s decode** (código), ~97 tok/s (narrativo),
  TTFT ~90 ms, 68,3% de aceitação de draft (código)
- Raciocínio: thinking ligado, effort `low`, `preserve_thinking` desligado
- Tool calling: validado (OpenCode/LiteLLM funcionam contra :8080)

## Execução

```bash
systemctl start qwen38-27b        # unidade systemd, habilitada na inicialização
# ou
bash qwen38-27b-rtx3090/single-user/start_qwen.sh  # primeiro plano
```

- Perfil: clone em `qwen38-27b-rtx3090/` (start_qwen.sh + variáveis de ambiente)
- Unidade: `infra/qwen38-27b.service` (instalada como `qwen38-27b.service`)
- Logs: `data/logs/qwen38-27b.log`

Notas:
- A primeira inicialização leva 3-4 min (perfis CUDA das duas GPUs).
- Sem WebUI e sem suporte a visão neste stack — esse é o trade-off pela velocidade
  (llama.cpp oferecia ambos; ver `arquived/`).
- `MAX_MODEL_LEN=96000` é o teto: 100k falhou por ~30 MiB e 128k+ requer
  a revisão custom do repositório original.

## `arquived/` — a era do llama.cpp

O engine anterior, **llama.cpp (b10502)** com GGUF Q4_K_XL e decodificação especulativa MTP,
foi arquivado em 2026-08-19 porque era **lento comparado ao stack vLLM**:

| Engine | 1 cliente | 2 clientes (combinado) | Contexto | Visão | WebUI |
|---|---|---|---|---|---|
| llama.cpp b10502 (arquivado) | ~56-58 tok/s | ~71-74 tok/s | 2×256k | nativa (mmproj) | sim |
| vLLM + DFlash2 (atual) | ~97-177 tok/s | 2 curtos concorrentes | 96k | não | não |

O setup do llama.cpp foi extensivamente ajustado antes de ser aposentado: construção de
CUDA-graphs (+3,8% sobre a construção anterior), varredura MTP (n=2, p_min=0.5 → 82,9% de
aceitação), split de 2 slots entre GPUs com `TENSOR_SPLIT`, visão offloadada para CPU,
métricas Prometheus, e um benchmark completo em `docs/llama-cpp-b10502-benchmark.md`.

Tudo dessa era está preservado em `arquived/` (versionado neste repositório, exceto
dezenas de GB de GGUFs, logs e segredos `.env`, que ficam no `.gitignore`):

- `.env` + `Makefile` + `scripts/start-server.sh` + `tests/` — o pipeline do llama.cpp
- `data/models/` — checkpoints GGUF (Q6_K_XL, UD-Q4_K_XL, Q5_K_M, mmproj)
- `infra/llama-server/` — unidades systemd + watchdog do servidor antigo
- `env-examples/` — perfis `.env.example` por modelo (Ornith, Qwen3.6, Qwen3.8)
- `llama-cpp-grammar-patches.patch`, `docs/`, benchmarks e resultados da varredura MTP

Para restaurar o stack antigo, mova o conteúdo de volta para a raiz do repositório e reconstrua:
`make setup && make start` (o Makefile está em `arquived/`).
