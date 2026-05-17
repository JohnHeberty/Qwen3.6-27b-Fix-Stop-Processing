# Qwen3.6 27B — Servidor Local GGUF · API OpenAI-compatible

> Servidor de inferência local para o **Qwen3.6 27B** usando [llama-server](https://github.com/ggml-org/llama.cpp) com modelo GGUF Q4_K_M.  
> API 100% compatível com OpenAI · Thinking mode · Tool calling · **63.488 tokens de contexto**

**Testado e validado em: Zotac GeForce RTX 3090 Trinity OC · 24.576 MB VRAM · Driver 590.48.01 · Debian 12 · CUDA 12.8**

---

## Requisitos

### Hardware

| Componente | Mínimo | Testado/Validado |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | **Zotac GeForce RTX 3090 Trinity OC — 24.576 MB VRAM** ✓ |
| RAM | 16 GB | 32 GB |
| Disco livre | 25 GB | 30 GB |

> O modelo Q4_K_M ocupa ~16 GB de VRAM. Com 24.576 MB (RTX 3090), sobram ~8 GB para KV cache — suficiente para **63.488 tokens** de contexto.

### Software

| Requisito | Mínimo | Usado/Validado | Verificar |
|---|---|---|---|
| OS | Debian 12 / Ubuntu 22.04+ | Debian 12 (Bookworm) | `lsb_release -a` |
| Driver NVIDIA | ≥ 525 | **590.48.01** ✓ | `nvidia-smi` |
| CUDA Toolkit | 12.x | **12.8** em `/usr/local/cuda` | `nvcc --version` |
| Git | qualquer | — | `git --version` |

> Python, cmake e build-essential são instalados automaticamente pelo `make setup`. O único pré-requisito manual é o **driver NVIDIA + CUDA toolkit**.

**Instalar CUDA toolkit (se necessário):**
```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update && sudo apt-get install -y cuda-toolkit-12-8
```

---

## Instalação

### 1. Clonar e configurar

```bash
git clone https://github.com/JohnHeberty/Qwen3.6-27b-Fix-Stop-Processing.git qwen3
cd qwen3
cp .env.example .env
```

Edite `.env` e preencha o token obrigatório:

```bash
HUGGINGFACE_TOKEN=hf_seu_token_aqui   # https://huggingface.co/settings/tokens
```

### 2. Setup completo (uma vez)

```bash
make setup
```

Executa **8 etapas** automaticamente. Cada etapa verifica se já foi feita — rodar duas vezes é seguro.

| Etapa | O que faz |
|---|---|
| `[1]` install-system-deps | apt: python3, cmake, git, build-essential |
| `[2]` setup-cuda | Verifica CUDA toolkit, registra libcudart |
| `[3]` create-venv | Cria `.venv` Python isolado |
| `[4]` install-python-deps | pip: gguf, huggingface-hub, openai, requests |
| `[5]` build-llama-server | Clona e compila llama-server com CUDA |
| `[6]` build-llama-cpp-python | Compila llama-cpp-python com GPU offload |
| `[7]` download-model | Baixa `Qwen3.6-27B-Q4_K_M.gguf` (~16 GB) |
| `[8]` fix-template | Patcha o GGUF com template v18 (froggeric) |

Tempo estimado: **20–40 minutos** (compilação + download do modelo).

### 3. Iniciar e testar

```bash
make start     # servidor em foreground — aguarde "llama server listening"
make test      # em outro terminal — deve mostrar 6/6 testes passando
make status    # estado do servidor + uso de VRAM
```

O servidor estará disponível em `http://localhost:8000/v1`.

---

## Uso da API

A API é 100% compatível com o SDK OpenAI — basta trocar o `base_url`.

| Parâmetro | Valor |
|---|---|
| Base URL | `http://<host>:8000/v1` |
| Model name | `qwen3` |
| API Key | qualquer string (não validada) |

### Python

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="nao-precisa")

response = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "Explique o que é um modelo de linguagem."}],
    max_tokens=512,
    temperature=0.7
)
print(response.choices[0].message.content)
```

### curl

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3","messages":[{"role":"user","content":"Olá!"}],"max_tokens":256}'
```

### Streaming

```python
stream = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "Conte uma história curta."}],
    max_tokens=512,
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### Thinking mode (raciocínio estendido)

O Qwen3.6 raciocina internamente antes de responder. O conteúdo do pensamento vem em `reasoning_content`:

```python
response = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "Quanto é 17 × 23?"}],
    max_tokens=300   # mínimo 300 para thinking mode ter espaço
)
print("Raciocínio:", response.choices[0].message.reasoning_content)
print("Resposta:  ", response.choices[0].message.content)
```

Para **desabilitar** thinking (respostas mais rápidas):
```python
messages=[{"role": "system", "content": "<|think_off|>"}, {"role": "user", "content": "..."}]
```

---

## Coexistência com Ollama

Se o Ollama estiver instalado, ambos competem pelos 24 GB de VRAM. O `make start` já descarrega modelos do Ollama automaticamente. Para ajuste permanente:

```bash
make configure-ollama   # reduz OLLAMA_KEEP_ALIVE de 30 min → 5 min
make ollama-unload      # libera VRAM do Ollama manualmente
```

---

## Produção (systemd)

Para o servidor iniciar automaticamente no boot:

```bash
make install-service    # registra o serviço (não habilita ainda)
make enable-service     # habilita auto-start no boot + inicia agora
```

> **Atenção:** auto-start no boot conflita com Ollama se ambos usarem a GPU. Use `make disable-service` para reverter.

Gerenciar o serviço:
```bash
sudo systemctl status qwen-server      # estado
sudo systemctl restart qwen-server     # reiniciar
sudo journalctl -u qwen-server -f      # logs em tempo real
```

---

## Integração com LiteLLM

Config pronta em `infra/litellm_config.yaml`. Para subir o proxy na porta 4000:

```bash
make litellm-start
```

Nos seus projetos, aponte para `http://localhost:4000` com `model="qwen"`. O config já inclui `context_window: 63488` para evitar o erro `Context size has been exceeded`.

---

## Referência rápida de comandos

| Comando | Descrição |
|---|---|
| `make setup` | Pipeline completa: instala tudo do zero |
| `make start` | Sobe o servidor em foreground |
| `make start-bg` | Sobe em background (`make logs` para acompanhar) |
| `make stop` | Para o servidor |
| `make restart` | Para e sobe em background |
| `make status` | Estado + VRAM |
| `make test` | 6 testes de integração |
| `make install-service` | Registra serviço systemd |
| `make enable-service` | Habilita auto-start no boot |
| `make litellm-start` | Proxy LiteLLM na porta 4000 |
| `make clean` | Remove modelo, logs e `.venv` |

---

## Solução de problemas rápida

**Servidor não sobe — modelo não encontrado:**
```bash
make download-model && make fix-template
```

**CUDA out of memory:**
```bash
make ollama-unload && make start
```

**Compilação llama.cpp falha:**
```bash
rm -rf ~/llama.cpp/build && make build-llama-server
```

**Respostas vazias:** aumente `max_tokens` para ≥ 300 (thinking mode consome tokens internamente).

---

## Documentação completa

**[→ docs/index.md](docs/index.md)** — índice completo de toda a documentação

| | |
|---|---|
| [Primeiros Passos (detalhado)](docs/tutorials/getting-started.md) | Pré-requisitos, passo a passo, verificação |
| [Usar a API](docs/how-to/api-usage.md) | Todos os exemplos: chat, tools, thinking, streaming |
| [LiteLLM](docs/how-to/litellm.md) | Proxy, fix "context size exceeded" |
| [OpenCode](docs/how-to/opencode.md) | Terminal AI assistant |
| [Produção](docs/how-to/production.md) | systemd, Ollama, troubleshooting completo |
| [Comandos make](docs/reference/make-commands.md) | Todos os targets |
| [Variáveis .env](docs/reference/configuration.md) | Todas as variáveis com padrões |
| [Arquitetura](docs/explanation/architecture.md) | Decisões técnicas, por que GGUF vs vLLM |
| [Template v18](docs/explanation/template-v18.md) | froggeric — o que o template corrige |

---

## Agradecimentos

Template v18 por [**froggeric**](https://huggingface.co/froggeric) — corrige KV cache, tool calling loops e thinking mode do Qwen3.6:  
**[huggingface.co/froggeric/Qwen-Fixed-Chat-Templates](https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates)**

---

*Modelo: [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) (Alibaba, Apache 2.0) · GGUF: [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)*
