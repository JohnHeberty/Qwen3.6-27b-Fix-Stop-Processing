# Ornith-1.0-35B — local inference server

**Modelo:** Ornith-1.0-35B Q4_K_M (MoE, ~3B ativos/token) via llama-server (llama.cpp)
**GPU:** RTX 3090 (24 GB) | **API:** `http://localhost:8080/v1` | **Contexto:** 128k

## Configuração

Configuração baseada na [receita oficial do Ornith](https://huggingface.co/deepreinforce-ai/Ornith-1.0-35B):
- **Template:** embutido no GGUF (sem `--chat-template-file`)
- **Sampling:** `temp=0.6, top_p=0.95, top_k=20` — sem penalidades (repeat/frequency/presence = off)
- **DRY:** desligado (`DRY_MULTIPLIER=0`)
- **Reasoning:** `on`, formato `deepseek`, budget `4096`

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
