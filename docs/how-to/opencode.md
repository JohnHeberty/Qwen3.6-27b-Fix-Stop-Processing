# Integrar com OpenCode

[OpenCode](https://opencode.ai) é um terminal AI coding assistant. O projeto inclui uma config pronta em [infra/opencode.json](../../infra/opencode.json).

---

## Usar a config

```bash
# Para um projeto específico (opencode lê da raiz do projeto)
cp /root/qwen3/infra/opencode.json ~/seu-projeto/opencode.json

# Para uso global
cp /root/qwen3/infra/opencode.json ~/.config/opencode/config.json
```

---

## Config (`infra/opencode.json`)

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "qwen-local/qwen3",
  "provider": {
    "qwen-local": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Qwen Local (llama-server)",
      "options": {
        "baseURL": "http://192.168.1.139:8000/v1",
        "apiKey": "nao-precisa"
      },
      "models": {
        "qwen3": {
          "name": "Qwen3.6 27B Q4_K_M",
          "limit": {
            "context": 63488,
            "output": 4096
          }
        }
      }
    }
  }
}
```

| Campo | Valor | Descrição |
|---|---|---|
| `model` | `qwen-local/qwen3` | Modelo padrão ao abrir o opencode |
| `baseURL` | `http://192.168.1.139:8000/v1` | Endereço do llama-server |
| `limit.context` | `63488` | Janela de contexto total |
| `limit.output` | `4096` | Máximo de tokens gerados por resposta |

> Altere `baseURL` se o servidor estiver em outra máquina ou porta.

---

## Limites de contexto

O campo `limit.context` corresponde ao `--ctx-size` do llama-server (63.488). O opencode usa isso para não enviar mais tokens do que a janela suporta. O espaço efetivo para input é `context − output = 63.488 − 4.096 = 59.392 tokens`.
