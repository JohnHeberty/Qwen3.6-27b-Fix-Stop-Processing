# Ornith-1.0-35B — local inference server

**Modelo:** Ornith-1.0-35B Q4_K_M (MoE, ~3B ativos/token) via llama-server (llama.cpp)
**GPU:** RTX 3090 (24 GB) | **API:** `http://localhost:8080/v1` | **Contexto:** 128k

## ⚠️ CRÍTICO: parâmetros que NÃO devem ser alterados

Estes parâmetros **quebraram tool calling** em 30 Jul 2026 e exigiram rollback. Não mexa.

| Parâmetro | Valor obrigatório | Motivo |
|---|---|---|
| `TEMPLATE_FILE` | **vazio** (template GGUF embutido) | Template custom fez modelo narrar em vez de chamar ferramentas |
| `DRY_MULTIPLIER` | **0** (desligado) | DRY penalizou repetições naturais de `<tool_call>` |
| `REPEAT_PENALTY` | **1.0** (desligado) | Penalidade cortou saídas longas, modelo "desistia" |
| `REPEAT_LAST_N` | **64** (janela mínima) | Janela grande + penalty fez modelo repetir infinitamente |
| `REASONING_BUDGET_MESSAGE` | **vazio** (flag omitida) | Mensagem cortava raciocínio antes do modelo gerar `<tool_call>` |
| `thinkingDefault` (OpenClaw) | **medium** | `low` reduziu profundidade de raciocínio |
| `runRetries.max` (OpenClaw) | **10** | `2` deu poucas chances de recuperação |

Commits de referência: `2c96270` (rollback) / `defeb63` (quebrou).

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
