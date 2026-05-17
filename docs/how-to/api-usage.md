# Usar a API

O servidor expõe uma API 100% compatível com OpenAI na porta `8000`.

| Parâmetro | Valor |
|---|---|
| Base URL | `http://<host>:8000/v1` |
| Porta | `8000` |
| Model name | `qwen3` |
| API Key | qualquer string (não validada) |

---

## Chat — Python (SDK OpenAI)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="nao-precisa"
)

response = client.chat.completions.create(
    model="qwen3",
    messages=[
        {"role": "user", "content": "Explique o que é um modelo de linguagem."}
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
      {"role": "user", "content": "Qual é a capital do Brasil?"}
    ],
    "max_tokens": 256,
    "temperature": 0.7
  }'
```

---

## Streaming

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="nao-precisa")

stream = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "Conte uma história curta."}],
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
# curl com streaming
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3","messages":[{"role":"user","content":"Olá!"}],"stream":true}'
```

---

## System Prompt

```python
response = client.chat.completions.create(
    model="qwen3",
    messages=[
        {
            "role": "system",
            "content": "Você é um especialista em Python. Responda sempre com exemplos de código."
        },
        {
            "role": "user",
            "content": "Como fazer uma requisição HTTP em Python?"
        }
    ],
    max_tokens=512
)
```

---

## Thinking Mode (Raciocínio Estendido)

O Qwen3.6 suporta **thinking mode**: o modelo raciocina internamente antes de responder. Ativado automaticamente pelo template v18. O conteúdo do pensamento vem no campo `reasoning_content`.

```python
response = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "Quanto é 17 × 23?"}],
    max_tokens=300
)

print("Reasoning:", response.choices[0].message.reasoning_content)
print("Answer:   ", response.choices[0].message.content)
```

**Desabilitar thinking** para respostas mais rápidas:

```python
response = client.chat.completions.create(
    model="qwen3",
    messages=[
        {"role": "system", "content": "<|think_off|>"},
        {"role": "user", "content": "Qual é a capital da França?"}
    ],
    max_tokens=50
)
```

> Para respostas complexas com thinking mode, use `max_tokens` ≥ 300–500. O modelo usa parte dos tokens para o raciocínio interno antes de gerar a resposta.

---

## Tool Calling (Function Calling)

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Retorna a temperatura atual de uma cidade",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Nome da cidade"
                    }
                },
                "required": ["city"]
            }
        }
    }
]

response = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "Qual é o clima em São Paulo?"}],
    tools=tools,
    tool_choice="auto",
    max_tokens=256
)

if response.choices[0].message.tool_calls:
    tool_call = response.choices[0].message.tool_calls[0]
    print(f"Função:     {tool_call.function.name}")
    print(f"Argumentos: {tool_call.function.arguments}")
```

---

## Listar modelos

```bash
curl http://localhost:8000/v1/models
# → {"object":"list","data":[{"id":"qwen3",...,"meta":{"n_ctx":63488,...}}]}
```

---

## Limites

| Parâmetro | Valor |
|---|---|
| Contexto total | 63.488 tokens |
| Espaço para input | ~55.296 tokens (63.488 − headroom de saída) |
| `max_tokens` recomendado | 512–8.192 |
| `max_tokens` mínimo (thinking mode) | 300 |
