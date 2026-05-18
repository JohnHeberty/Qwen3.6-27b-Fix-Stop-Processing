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

| Field | Value | Description |
|---|---|---|
| `model` | `qwen-local/qwen3` | Default model when opening opencode |
| `baseURL` | `http://192.168.1.139:8000/v1` | llama-server address |
| `limit.context` | `63488` | Total context window |
| `limit.output` | `4096` | Maximum generated tokens per response |

> Update `baseURL` if the server is on a different machine or port.

---

## Context limits

The `limit.context` field corresponds to the `--ctx-size` of llama-server (63,488). OpenCode uses this to avoid sending more tokens than the window supports. The effective input space is `context − output = 63,488 − 4,096 = 59,392 tokens`.
