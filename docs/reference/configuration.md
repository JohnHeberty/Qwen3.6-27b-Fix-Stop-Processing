# Referência — Configuração (`.env`)

Copie `.env.example` para `.env` e edite conforme necessário.

```bash
cp .env.example .env
```

---

## Variáveis

| Variável | Padrão | Obrigatório | Descrição |
|---|---|---|---|
| `HUGGINGFACE_TOKEN` | — | **sim** | Token de acesso ao HuggingFace. Obtenha em https://huggingface.co/settings/tokens |
| `MODEL_HF` | `unsloth/Qwen3.6-27B-MTP-GGUF` | não | Repositório HuggingFace do modelo GGUF |
| `MODEL_FILE` | `Qwen3.6-27B-Q4_K_M.gguf` | não | Nome do arquivo GGUF a baixar e servir |
| `TEMPLATE_FILE` | `data/templates/archive/qwen3.6/chat_template-v18.jinja` | não | Template Jinja2 a aplicar no GGUF |
| `LLAMA_CPP_DIR` | `~/llama.cpp` | não | Diretório onde llama.cpp será clonado e compilado |
| `LLAMA_SERVER` | `~/llama.cpp/build/bin/llama-server` | não | Caminho do binário compilado |
| `CUDA_HOME` | `/usr/local/cuda` | não | Raiz do CUDA toolkit |
| `PORT` | `8000` | não | Porta em que o servidor escuta |
| `SERVED_NAME` | `qwen3` | não | Nome do modelo exposto na API (`/v1/models`) |
| `N_GPU_LAYERS` | `-1` | não | Layers a offloar para GPU. `-1` = todos |
| `N_CTX` | `63488` | não | Tamanho máximo do contexto em tokens |
| `N_BATCH` | `512` | não | Batch size para processamento de prompts |

---

## Exemplo de `.env` completo

```bash
# Credenciais
HUGGINGFACE_TOKEN=hf_seu_token_aqui

# Modelo GGUF
MODEL_HF=unsloth/Qwen3.6-27B-MTP-GGUF
MODEL_FILE=Qwen3.6-27B-Q4_K_M.gguf
TEMPLATE_FILE=data/templates/archive/qwen3.6/chat_template-v18.jinja

# llama.cpp
LLAMA_CPP_DIR=/root/llama.cpp
LLAMA_SERVER=/root/llama.cpp/build/bin/llama-server

# CUDA
CUDA_HOME=/usr/local/cuda

# Servidor
PORT=8000
SERVED_NAME=qwen3
N_GPU_LAYERS=-1
N_CTX=63488
N_BATCH=512
```

---

## Sobrescrever sem editar o arquivo

Qualquer variável pode ser passada inline para um comando `make`:

```bash
N_CTX=32768 make start     # contexto menor (usa menos VRAM)
PORT=9000 make start       # porta diferente
SERVED_NAME=llm make start # nome diferente na API
```

---

## Segurança

O arquivo `.env` contém o `HUGGINGFACE_TOKEN` e está no `.gitignore` — nunca é commitado. O `.env.example` tem um token placeholder (`hf_XXXXX`) e é o único arquivo de configuração versionado.
