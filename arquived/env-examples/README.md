# env-examples

Um `.env.example` por modelo, já com os parâmetros benchmarkados daquele modelo.
Não existe `.env.example` na raiz — escolha o do modelo que vai rodar.

```bash
cp env-examples/<modelo>/.env.example .env
# preencha HUGGINGFACE_TOKEN e ajuste o que precisar
make setup && make start
```

## Modelos

| Pasta | Modelo | Arquivo | tok/s @104k | Quando usar |
|---|---|---|---|---|
| `qwen3.6-35b-a3b/` | 35B-A3B (MoE, ~3B ativos/token) | `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` (22,6 GB) | ~100 | **Velocidade.** Padrão do projeto. |
| `qwen3.6-27b-dense/` | 27B denso | `Qwen3.6-27B-Q5_K_M.gguf` (19,8 GB) | ~41 | **Qualidade.** Melhor em coding agent, terminal e reasoning. |

Ambos usam cache KV `q4_0`, `MTP_TOKENS=2` e `N_CTX=106496` — os três foram
benchmarkados como ótimos para cada modelo separadamente e coincidiram.

## Trocar de modelo

O que muda entre os dois é só `MODEL_HF` e `MODEL_FILE`. Para alternar sem
reescrever o `.env` inteiro:

```bash
# para o 27B denso
sed -i -e 's|^MODEL_HF=.*|MODEL_HF=unsloth/Qwen3.6-27B-MTP-GGUF|' \
       -e 's|^MODEL_FILE=.*|MODEL_FILE=Qwen3.6-27B-Q5_K_M.gguf|' .env

# para o 35B-A3B
sed -i -e 's|^MODEL_HF=.*|MODEL_HF=unsloth/Qwen3.6-35B-A3B-MTP-GGUF|' \
       -e 's|^MODEL_FILE=.*|MODEL_FILE=Qwen3.6-35B-A3B-UD-Q4_K_M.gguf|' .env

make restart   # ou: systemctl restart qwen-server
```

O `SERVED_NAME` continua `qwen3` nos dois, então **LiteLLM, OpenCode e OpenClaw
não precisam de nenhuma alteração** ao trocar.

## Ao mudar `N_CTX`

Se alterar `N_CTX`, revise junto (ver "Context Window Math" em `infra/README.md`):

- `infra/litellm/config.yaml` → `context_window`, `max_input_tokens`
- `infra/opencode/config.json` → `limit.context`
- `infra/openclaw/openclaw.json` → `contextWindow`, `contextTokens`, `compaction.*`

Benchmarks completos por modelo: [`docs/infra/index.md`](../docs/infra/index.md).
