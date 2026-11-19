# Qwen3.8-27B — servidor local de inferência

Stack de produção: **vLLM TP=2 + AutoRound W4A16 (lm_head INT8) + DFlash2** em 2× RTX 3090 (48 GB VRAM),
expondo uma API compatível com OpenAI na porta 18020.

- Modelo: `qwen3.8-27b` — denso 27B, híbrido Gated DeltaNet + Atenção
- Engine: vLLM **0.33.0** (fork em `qwen38-27b-rtx3090/`, 61 patches aplicados: série de 57 + 4 do
  KVarN) + modelo draft `syvai/Qwen3.8-27B-DFlash2-W4A16` (7 drafts paralelos), alvo
  `dbirks/Qwen3.8-27B-W4A16-AutoRound` (variante base, lm_head INT8 — a `-fast` INT4 travou mais em
  loop no A/B de 2026-11-19; ver CLAUDE.md)
- Contexto: **142k** (`max_model_len=142080`, via `DFLASH_MAX_LEN` no `.env`), ~15,6 GB VRAM por GPU
  (pool de KV 5,52 GiB/GPU com `GPU_UTIL=0.62`)
- Medido em 2026-11-19 (vLLM 0.33.0, lm_head INT8, `presence_penalty` 1.0): **~136 tok/s** (código),
  ~62 tok/s (narrativo), 600 tokens de saída em prompt curto ([scripts/bench_tps.py](scripts/bench_tps.py))
- Raciocínio: thinking ligado, effort `medium`, `preserve_thinking` desligado
- Tool calling: validado (`--tool-call-parser qwen3_coder` + `--tool-strict-level parameter`;
  OpenCode/LiteLLM apontam para :18020)

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
- A primeira inicialização leva ~1,5 min (torch.compile + captura de cudagraph das duas GPUs).
- Sem WebUI. Visão: desligada por `--language-model-only`, mas o 0.33 traz o patch
  `vision-tower-cpu-offload` (`VISION_OFFLOAD`), então deixou de ser impossível neste stack.
- O contexto efetivo é 142080, definido por `DFLASH_MAX_LEN` no `.env`. Isso **sobrescreve** o
  default de 65536 do modo `CTX=fast` (bf16 KV), que é o modo em uso. A nota antiga de que
  "96k é o teto" está superada.

## `arquived/` — a era do llama.cpp

O engine anterior, **llama.cpp (b10502)** com GGUF Q4_K_XL e decodificação especulativa MTP,
foi arquivado em 2026-08-19 porque era **lento comparado ao stack vLLM**:

| Engine | 1 cliente | 2 clientes (combinado) | Contexto | Visão | WebUI |
|---|---|---|---|---|---|
| llama.cpp b10502 (arquivado) | ~56-58 tok/s | ~71-74 tok/s | 2×256k | nativa (mmproj) | sim |
| vLLM 0.33 + DFlash2 (atual) | ~67-133 tok/s | 2 curtos concorrentes | 142k | possível (VISION_OFFLOAD) | não |

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
