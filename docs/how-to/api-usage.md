# Use the API

The server exposes an OpenAI-compatible API on port `8000`.

| Parameter | Value |
|---|---|
| Base URL | `http://<host>:8000/v1` |
| Port | `8000` |
| Model name | `qwen3` |
| API Key | any string (not validated) |

---

## Chat — Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="qwen3",
    messages=[
        {"role": "user", "content": "What is a language model?"}
    ],
    max_tokens=512,
    temperature=0.7
)

print(response.choices[0].message.content)
```

---

## Chat — curl

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3",
    "messages": [
      {"role": "user", "content": "What is the capital of Brazil?"}
    ],
    "max_tokens": 256,
    "temperature": 0.7
  }'
```

---

## Streaming

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed")

stream = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "Tell me a short story."}],
    max_tokens=512,
    stream=True
)

for chunk in stream:
    delta = chunk.choices[0].delta
    if delta.content:
        print(delta.content, end="", flush=True)
print()
```

```bash
# curl with streaming
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3","messages":[{"role":"user","content":"Hello!"}],"stream":true}'
```

---

## System Prompt

```python
response = client.chat.completions.create(
    model="qwen3",
    messages=[
        {
            "role": "system",
            "content": "You are a Python expert. Always answer with code examples."
        },
        {
            "role": "user",
            "content": "How do I make an HTTP request in Python?"
        }
    ],
    max_tokens=512
)
```

---

## Thinking Mode (Extended Reasoning)

Qwen3.6 supports **thinking mode**: the model reasons internally before responding, which improves answer quality for complex problems.

**Thinking mode is enabled automatically** by the v18 template. The thinking content comes in the `reasoning_content` field:

```python
response = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "What is 17 × 23?"}],
    max_tokens=300
)

# Internal reasoning
print("Reasoning:", response.choices[0].message.reasoning_content)

# Final answer
print("Answer:   ", response.choices[0].message.content)
```

**Disable thinking** for faster responses:

```python
response = client.chat.completions.create(
    model="qwen3",
    messages=[
        {"role": "system", "content": "<|think_off|>"},
        {"role": "user", "content": "What is the capital of France?"}
    ],
    max_tokens=50
)
```

---

## Tool Calling (Function Calling)

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Returns the current temperature for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name"
                    }
                },
                "required": ["city"]
            }
        }
    }
]

response = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "What's the weather in São Paulo?"}],
    tools=tools,
    tool_choice="auto",
    max_tokens=256
)

if response.choices[0].message.tool_calls:
    tool_call = response.choices[0].message.tool_calls[0]
    print(f"Function:  {tool_call.function.name}")
    print(f"Arguments: {tool_call.function.arguments}")
```

---

## List Available Models

```bash
curl http://localhost:8000/v1/models
# → {"object":"list","data":[{"id":"qwen3",...}]}
```

---

## Limits

| Parameter | Value |
|---|---|
| Total context | 63,488 tokens |
| Effective input space | ~55,296 tokens (63,488 − output headroom) |
| Recommended `max_tokens` | 512–8,192 |
| Minimum `max_tokens` (thinking mode) | 300 |
