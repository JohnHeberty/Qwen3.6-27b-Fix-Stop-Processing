# Twinny (VSCode) — autocomplete FIM contra o vLLM

Config feita na UI do Twinny (Manage providers), na máquina do VSCode. Não é arquivo deste servidor.

Problema observado nos logs (`data/logs/qwen38-27b.log`, cliente 100.69.147.96):
o chat funciona (`POST /v1/chat/completions` 200), mas o FIM bate em
`POST /completion` (caminho do provider **llama.cpp**) -> 404. Também há `GET /api/tags` e
`GET /props` -> 404, que são só sondagens inofensivas de Ollama/llama.cpp.

## Provider de FIM
- **Type:** um provider que use `/v1/completions` (ex.: `lmstudio` ou `oobabooga`), **não** `llamacpp`/`ollama`
- **Protocol:** http · **Hostname:** 100.102.127.47 · **Port:** 18020
- **API path (FIM):** `/v1/completions`
- **Model:** `qwen3.8-27b` · **API key:** qualquer valor
- **FIM template:** `custom-template` (ou o do Qwen/Codeqwen se o Twinny oferecer)

Template custom (tokens do tokenizer do Qwen3.8, com os pipes):
```
<|fim_prefix|>{{prefix}}<|fim_suffix|>{{suffix}}<|fim_middle|>
```
Se o Twinny gerar `<fim_prefix>` SEM pipes, o modelo não reconhece os tokens: use o custom acima.

Teste do servidor (funciona, completou `r = a + b`):
```
curl localhost:18020/v1/completions -H 'Content-Type: application/json' -d '{"model":"qwen3.8-27b",
 "prompt":"<|fim_prefix|>def soma(a, b):\n    <|fim_suffix|>\n    return r\n<|fim_middle|>",
 "max_tokens":32,"temperature":0,"stop":["<|endoftext|>","<|fim_pad|>"]}'
```
Depois de configurar, confira: `grep "POST /v1/completions" data/logs/qwen38-27b.log | tail`
(o `/completion` com 404 deve parar de aparecer).
