# Integrate with LiteLLM

The project includes a ready-to-use config at [infra/litellm_config.yaml](../../infra/litellm_config.yaml).

---

## Start the proxy

```bash
make litellm-start
# → LiteLLM proxy at http://localhost:4000
# → use model_name="qwen" in your projects
```

The Makefile installs `litellm` into `.venv` automatically if not already present.

---

## Full config (`infra/litellm_config.yaml`)

```yaml
model_list:
  - model_name: qwen
    litellm_params:
      model: openai/qwen3
      api_base: http://192.168.1.139:8000/v1
      api_key: "not-needed"
    model_info:
      context_window: 63488        # tells LiteLLM the real window size
      max_input_tokens: 55296      # 63488 - 8192 (output headroom)
      max_output_tokens: 8192
      input_cost_per_token: 0
      output_cost_per_token: 0

litellm_settings:
  drop_params: true
```

> Update the IP if needed. The file is at `infra/litellm_config.yaml`.

---

## Using in your projects

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:4000/v1",   # LiteLLM proxy port
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="qwen",                          # model_name defined in config
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=512
)
```

---

## Error "Context size has been exceeded"

`litellm.MidStreamFallbackError: Context size has been exceeded` occurs when the accumulated conversation history exceeds 63,488 tokens. Without the `context_window` and `max_input_tokens` keys, LiteLLM doesn't know the window size and lets the request through without validation — the llama-server then returns the error mid-stream.

### Fix 1 — Via proxy (recommended)

Make sure `infra/litellm_config.yaml` has both keys under `model_info`:

```yaml
model_info:
  context_window: 63488
  max_input_tokens: 55296
```

### Fix 2 — Via SDK directly (no proxy)

```python
import litellm

litellm.register_model({
    "openai/qwen3": {
        "max_tokens": 63488,
        "max_input_tokens": 55296,
        "max_output_tokens": 8192,
        "litellm_provider": "openai",
        "mode": "chat",
    }
})

response = litellm.completion(
    model="openai/qwen3",
    api_base="http://192.168.1.139:8000/v1",
    api_key="not-needed",
    messages=messages,
    max_tokens=4096,
)
```

### Fix 3 — Trim conversation history before sending

```python
import litellm

# Check token count
token_count = litellm.token_counter(model="openai/qwen3", messages=messages)
print(f"Tokens: {token_count} / 63488")

# Trim if needed (keeps system prompt + last N messages)
if token_count > 55000:
    messages = [messages[0]] + messages[-10:]

# Or let LiteLLM trim automatically
messages = litellm.utils.trim_messages(messages, model="openai/qwen3")
```

### Fix 4 — Always set `max_tokens`

Never leave `max_tokens=None` with long contexts — llama-server interprets it as "generate up to the window limit", which may exceed the available space:

```python
response = client.chat.completions.create(
    model="qwen",
    messages=messages,
    max_tokens=4096,   # always set this
)
```
