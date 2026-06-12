# Integrate with OpenCode

[OpenCode](https://opencode.ai) is a terminal AI coding assistant. The project includes a ready-to-use config at [infra/opencode/config.json](../../infra/opencode/config.json).

---

## Use the config

```bash
# For a specific project (opencode reads from the project root)
cp /root/qwen3/infra/opencode/config.json ~/your-project/opencode.json

# For global use
cp /root/qwen3/infra/opencode/config.json ~/.config/opencode/config.json
```

---

## Config (`infra/opencode/config.json`)

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
        "apiKey": "not-needed"
      },
      "models": {
        "qwen3": {
          "name": "Qwen3.6 27B Q5_K_M",
          "limit": {
            "context": 77824,
            "output": 4096
          }
        }
      }
    }
  }
}
```

| Field | Value | Description |
|---|---|---|
| `model` | `qwen-local/qwen3` | Default model when opening opencode |
| `baseURL` | `http://192.168.1.139:8000/v1` | llama-server address |
| `limit.context` | `77824` | Total context window (81,920 − 4,096 output) |
| `limit.output` | `4096` | Maximum generated tokens per response |

> Update `baseURL` if the server is on a different machine or port.

---

## Context limits

The `limit.context` field tells OpenCode the effective input budget. The server runs at `--ctx-size 81920` (zero-penalty ceiling on RTX 3090); subtracting 4,096 output tokens gives `77,824` usable input tokens.
