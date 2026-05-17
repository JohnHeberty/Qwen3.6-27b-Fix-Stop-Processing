# Integrar com LiteLLM

O projeto já inclui uma config pronta em [infra/litellm_config.yaml](../../infra/litellm_config.yaml).

---

## Subir o proxy

```bash
make litellm-start
# → LiteLLM proxy em http://localhost:4000
# → use model_name="qwen" nos seus projetos
```

O Makefile instala `litellm` no `.venv` automaticamente se não estiver presente.

---

## Config completa (`infra/litellm_config.yaml`)

```yaml
model_list:
  - model_name: qwen
    litellm_params:
      model: openai/qwen3
      api_base: http://192.168.1.139:8000/v1
      api_key: "nao-precisa"
    model_info:
      context_window: 63488        # informa o LiteLLM o tamanho real da janela
      max_input_tokens: 55296      # 63488 - 8192 (headroom para saída)
      max_output_tokens: 8192
      input_cost_per_token: 0
      output_cost_per_token: 0

litellm_settings:
  drop_params: true
```

> Substitua o IP se necessário. O arquivo está em `infra/litellm_config.yaml`.

---

## Usar nos projetos

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:4000/v1",   # porta do proxy LiteLLM
    api_key="nao-precisa"
)

response = client.chat.completions.create(
    model="qwen",                          # model_name definido no config
    messages=[{"role": "user", "content": "Olá!"}],
    max_tokens=512
)
```

---

## Erro "Context size has been exceeded"

`litellm.MidStreamFallbackError: Context size has been exceeded` ocorre quando o histórico da conversa ultrapassa 63.488 tokens. O LiteLLM **não sabe** o tamanho da janela sem as chaves `context_window` e `max_input_tokens` — sem elas ele deixa a requisição passar sem validar e o llama-server retorna o erro no meio do stream.

### Fix 1 — Via proxy (recomendado)

Certifique-se de que o `infra/litellm_config.yaml` tem as duas chaves em `model_info`:

```yaml
model_info:
  context_window: 63488
  max_input_tokens: 55296
```

### Fix 2 — Via SDK direto (sem proxy)

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
    api_key="nao-precisa",
    messages=messages,
    max_tokens=4096,
)
```

### Fix 3 — Truncar histórico antes de enviar

```python
import litellm

# Verificar contagem de tokens
token_count = litellm.token_counter(model="openai/qwen3", messages=messages)
print(f"Tokens: {token_count} / 63488")

# Truncar se necessário (mantém system prompt + últimas mensagens)
if token_count > 55000:
    messages = [messages[0]] + messages[-10:]

# Ou deixar o LiteLLM truncar automaticamente
messages = litellm.utils.trim_messages(messages, model="openai/qwen3")
```

### Fix 4 — Sempre definir `max_tokens`

Nunca deixe `max_tokens=None` com contextos longos — o llama-server interpreta como "gere até o limite da janela", o que pode exceder o espaço disponível:

```python
response = client.chat.completions.create(
    model="qwen",
    messages=messages,
    max_tokens=4096,   # sempre definir
)
```
