# Ornith-1.0-35B — local inference server

**Modelo:** Ornith-1.0-35B Q4_K_M (MoE, ~3B ativos/token) via llama-server (llama.cpp)
**GPU:** RTX 3090 (24 GB) | **API:** `http://localhost:8080/v1` | **Contexto:** 128k

## ⚠️ CRÍTICO: parâmetros sensíveis

Estes parâmetros quebraram tool calling quando combinados com o template GGUF nativo (30 Jul 2026). Com `chat_template_local.jinja` funcionam normalmente.

| Parâmetro | Valor atual | Observação |
|---|---|---|
| `TEMPLATE_FILE` | **`data/templates/custom/chat_template_local.jinja`** | Obrigatório. GGUF nativo permite "natural language BEFORE tool_call" — o custom proíbe |
| `DRY_MULTIPLIER` | **0.7** | Só funciona com o template custom (que não gera texto antes de tool_call) |
| `REPEAT_PENALTY` | **1.05** | Idem — template correto evita a narração que o penalty puniria |
| `REPEAT_LAST_N` | **4096** | — |
| `REASONING_BUDGET_MESSAGE` | **vazio** | Não mexer. Mensagem corta raciocínio antes do modelo gerar `<tool_call>` |
| `thinkingDefault` (OpenClaw) | **medium** | `low` reduz profundidade de raciocínio |
| `runRetries.max` (OpenClaw) | **3** | `2` dá poucas chances de recuperação |

Commit do rollback: `2c96270`. Commit que quebrou: `defeb63`.

## Comandos

```bash
make start       # foreground
make start-bg    # background, logs em data/logs/server.log
make stop        # para o servidor
make test        # 14 testes (API, tool calling, streaming)
make logs        # acompanha log
```

Setup completo: `make setup` (pipelines zero-dependência).
Mais alvos: `make help`.
