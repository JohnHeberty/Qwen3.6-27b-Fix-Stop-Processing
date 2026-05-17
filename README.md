# Qwen3.6 27B — Servidor Local GGUF · API OpenAI-compatible

> Servidor de inferência local para o **Qwen3.6 27B** usando [llama-server](https://github.com/ggml-org/llama.cpp) com modelo GGUF Q4_K_M.  
> API 100% compatível com OpenAI · Thinking mode · Tool calling · 63.488 tokens de contexto

---

## O que é isso

Este projeto serve o **Qwen3.6 27B** (modelo da Alibaba, lançado em Abril 2026) localmente com:

- **llama-server** (llama.cpp) compilado com CUDA — inferência GPU nativa
- **Modelo GGUF Q4_K_M** (~16 GB) — quantização de alta qualidade com iMatrix
- **Template v18** (froggeric) patchado diretamente no GGUF — corrige bugs do template oficial (KV cache, tool calls, thinking mode)
- **API OpenAI-compatible** na porta `8000` — drop-in replacement para clientes OpenAI

O setup completo é automatizado via `make setup` — instala tudo do zero incluindo Python, cmake, llama.cpp e o modelo.

---

## Requisitos de Hardware e Software

### Hardware
| Componente | Mínimo | Recomendado |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | 24 GB (testado em RTX 3090) |
| RAM | 16 GB | 32 GB |
| Disco | 25 GB livres | 30 GB |

> O modelo Q4_K_M ocupa ~16 GB de VRAM. Com 24 GB, sobram ~8 GB para KV cache (63.488 tokens de contexto).

### Software
- **OS**: Debian 12 (Bookworm) ou Ubuntu 22.04+ (recomendado)
- **Driver NVIDIA**: ≥ 590 (suporta CUDA 12.8)
- **CUDA Toolkit**: 12.x instalado em `/usr/local/cuda`
- **Git**: para clonar o repositório

> O `make setup` instala automaticamente Python, cmake, build-essential e compila o llama.cpp. O único pré-requisito manual é o driver NVIDIA e o CUDA toolkit.

---

## Quick Start

```bash
# 1. Clonar e configurar
git clone https://github.com/JohnHeberty/Qwen3.6-27b-Fix-Stop-Processing.git qwen3
cd qwen3
cp .env.example .env
# Editar .env e preencher HUGGINGFACE_TOKEN

# 2. Setup completo (instala tudo do zero ~20-30 min)
make setup

# 3. Iniciar servidor
make start

# 4. Testar
make test
# → 6/6 testes passam
```

O servidor estará disponível em `http://localhost:8000/v1`.

---

## Instalação Detalhada

### 1. Pré-requisitos

**Driver NVIDIA** (instale manualmente se não tiver):
```bash
# Verificar driver
nvidia-smi

# Se não instalado, siga: https://www.nvidia.com/Download/index.aspx
```

**CUDA Toolkit** (necessário para compilar llama.cpp):
```bash
# Verificar CUDA
nvcc --version

# Se não instalado (Debian/Ubuntu):
wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt-get update && apt-get install -y cuda-toolkit-12-8
```

### 2. Configurar `.env`

```bash
cp .env.example .env
```

Edite `.env` e preencha obrigatoriamente:

```bash
HUGGINGFACE_TOKEN=hf_seu_token_aqui   # ← obrigatório
```

Obtenha seu token em: https://huggingface.co/settings/tokens

### 3. Executar `make setup`

O `make setup` executa **8 etapas** automaticamente, cada uma com sentinel (não repete o que já foi feito):

| Etapa | Comando | O que faz |
|---|---|---|
| `[1]` | `make install-system-deps` | apt: python3, cmake, git, build-essential, curl |
| `[2]` | `make setup-cuda` | Verifica CUDA toolkit e registra libcudart no sistema |
| `[3]` | `make create-venv` | Cria `.venv` Python isolado |
| `[4]` | `make install-python-deps` | pip: gguf, huggingface-hub, openai, requests |
| `[5]` | `make build-llama-server` | Clona llama.cpp, aplica patches, compila llama-server com CUDA |
| `[6]` | `make build-llama-cpp-python` | Compila llama-cpp-python com suporte a GPU offload |
| `[7]` | `make download-model` | Baixa `Qwen3.6-27B-Q4_K_M.gguf` (~16 GB) do HuggingFace |
| `[8]` | `make fix-template` | Patcha o GGUF com o template v18 (patch binário com alinhamento correto) |

Cada etapa verifica se já foi executada antes de agir — rodar `make setup` duas vezes é seguro.

### 4. Verificar instalação

```bash
make status
# → Servidor: RODANDO em http://localhost:8000/v1
# → GPU:     NVIDIA GeForce RTX 3090, 21000 MiB, 3100 MiB

make test
# → 6/6 testes passaram
```

---

## Uso da API

### Endpoint e Autenticação

| Parâmetro | Valor |
|---|---|
| Base URL | `http://<host>:8000/v1` |
| Porta | `8000` |
| Model name | `qwen3` |
| API Key | qualquer string (não validada) |

### Chat — Python (SDK OpenAI)

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

### Chat — curl

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

### Streaming

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

### System Prompt

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

### Thinking Mode (Raciocínio Estendido)

O Qwen3.6 suporta **thinking mode**: o modelo "pensa" antes de responder, mostrando o raciocínio interno. Isso aumenta a qualidade das respostas para problemas complexos.

**O thinking mode é ativado automaticamente** pelo template v18. O conteúdo do pensamento vem no campo `reasoning_content`:

```python
response = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "Quanto é 17 × 23?"}],
    max_tokens=300
)

# Pensamento interno
print("Reasoning:", response.choices[0].message.reasoning_content)

# Resposta final
print("Answer:", response.choices[0].message.content)
```

**Desabilitar thinking** para respostas mais rápidas:

```python
# Via system prompt
response = client.chat.completions.create(
    model="qwen3",
    messages=[
        {"role": "system", "content": "<|think_off|>"},
        {"role": "user", "content": "Qual é a capital da França?"}
    ],
    max_tokens=50
)
```

### Tool Calling (Function Calling)

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

# Verificar se houve chamada de ferramenta
if response.choices[0].message.tool_calls:
    tool_call = response.choices[0].message.tool_calls[0]
    print(f"Função: {tool_call.function.name}")
    print(f"Argumentos: {tool_call.function.arguments}")
```

### Listar Modelos Disponíveis

```bash
curl http://localhost:8000/v1/models
# → {"object":"list","data":[{"id":"qwen3",...}]}
```

---

## Referência de Comandos (`make`)

| Comando | Descrição |
|---|---|
| `make setup` | Pipeline completa: instala tudo do zero (8 etapas) |
| `make install-system-deps` | [1] Instala Python, cmake, git, build-essential |
| `make setup-cuda` | [2] Verifica / configura CUDA toolkit |
| `make create-venv` | [3] Cria virtualenv Python |
| `make install-python-deps` | [4] Instala gguf, huggingface-hub, etc. |
| `make build-llama-server` | [5] Compila llama-server com CUDA |
| `make build-llama-cpp-python` | [6] Compila llama-cpp-python com CUDA |
| `make download-model` | [7] Baixa modelo GGUF do HuggingFace |
| `make fix-template` | [8] Aplica template v18 no GGUF |
| `make start` | Sobe o servidor em foreground (Ctrl+C para parar) |
| `make start-bg` | Sobe em background (log em `data/logs/server.log`) |
| `make stop` | Para o servidor |
| `make restart` | Para e sobe em background |
| `make status` | Estado do servidor + uso de VRAM |
| `make logs` | Acompanha log em tempo real |
| `make test` | Roda suite de testes da API (6 endpoints) |
| `make install-service` | Instala como serviço systemd (inicia no boot) |
| `make clean` | Remove modelo, logs e venv (mantém código) |

---

## Configuração (`.env`)

Copie `.env.example` para `.env` e edite conforme necessário:

| Variável | Padrão | Descrição |
|---|---|---|
| `HUGGINGFACE_TOKEN` | — | **Obrigatório.** Token de acesso ao HuggingFace |
| `MODEL_HF` | `unsloth/Qwen3.6-27B-MTP-GGUF` | Repositório HuggingFace do modelo |
| `MODEL_FILE` | `Qwen3.6-27B-Q4_K_M.gguf` | Nome do arquivo GGUF |
| `TEMPLATE_FILE` | `data/templates/.../chat_template-v18.jinja` | Template Jinja2 a aplicar |
| `LLAMA_CPP_DIR` | `~/llama.cpp` | Diretório onde llama.cpp será clonado/compilado |
| `LLAMA_SERVER` | `~/llama.cpp/build/bin/llama-server` | Caminho do binário compilado |
| `CUDA_HOME` | `/usr/local/cuda` | Raiz do CUDA toolkit |
| `PORT` | `8000` | Porta do servidor |
| `SERVED_NAME` | `qwen3` | Nome do modelo na API |
| `N_GPU_LAYERS` | `-1` | Layers na GPU (`-1` = todos) |
| `N_CTX` | `63488` | Contexto máximo em tokens |
| `N_BATCH` | `512` | Batch size para prompts |

Exemplo para sobrescrever via linha de comando:
```bash
N_CTX=32768 make start
PORT=9000 make start
```

---

## Integração com LiteLLM

Para usar via [LiteLLM Gateway](https://github.com/BerriAI/litellm), adicione ao `config.yaml`:

```yaml
- model_name: qwen
  litellm_params:
    model: openai/qwen3
    api_base: http://192.168.1.xxx:8000/v1
    api_key: "nao-precisa"
    max_tokens: 4096
  model_info:
    input_cost_per_token: 0
    output_cost_per_token: 0
```

> Substitua `192.168.1.xxx` pelo IP da máquina onde o servidor está rodando.

---

## Produção (systemd)

### Instalar como serviço

```bash
make install-service
```

Isso instala e ativa o serviço `qwen-server` que:
- Inicia automaticamente no boot
- Reinicia automaticamente em caso de falha (após 15 segundos)
- Loga em `data/logs/server.log`

### Gerenciar o serviço

```bash
sudo systemctl status qwen-server     # ver estado
sudo systemctl stop qwen-server       # parar
sudo systemctl start qwen-server      # iniciar
sudo systemctl restart qwen-server    # reiniciar
sudo journalctl -u qwen-server -f     # acompanhar logs do systemd
```

### Instalar manualmente

```bash
sudo cp infra/qwen-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qwen-server
```

---

## Estrutura do Projeto

```
qwen3/
├── .env                    configuração (não versionado)
├── .env.example            template de configuração
├── Makefile                pipeline completa de setup e operação
├── requirements.txt        dependências Python
│
├── data/
│   ├── models/             modelo GGUF (~16 GB, gitignored)
│   ├── templates/          templates Jinja2 do froggeric (v8–v18)
│   ├── logs/               logs de runtime (gitignored)
│   └── backups/            backups do template original do GGUF (gitignored)
│
├── scripts/
│   ├── setup.sh            script de instalação (chamado pelo Makefile)
│   └── start-server.sh     script de inicialização do servidor
│
├── src/
│   └── fix_template.py     patch binário do GGUF com template v18
│
├── tests/
│   └── test_api.py         testes de integração da API (6 endpoints)
│
├── infra/
│   └── qwen-server.service unidade systemd para autostart
│
└── docs/
    └── PLAN.md             documentação técnica detalhada do projeto
```

---

## Solução de Problemas

### Servidor não sobe — "model not found"
```bash
# Verificar se o modelo foi baixado
ls -lh data/models/*.gguf

# Se não existir, baixar manualmente
make download-model
```

### Erro de VRAM — "CUDA out of memory"
```bash
# Verificar uso atual
nvidia-smi

# Parar outros processos que usam GPU
make stop
sudo systemctl stop ollama  # se Ollama estiver rodando
```

O Qwen3.6 27B Q4_K_M usa ~21 GB de VRAM. Em GPUs com 24 GB (RTX 3090/4090), outros processos CUDA devem ser encerrados antes de iniciar.

### CUDA não encontrado — "[2] setup-cuda FAIL"
```bash
# Verificar nvcc
nvcc --version

# Instalar CUDA toolkit (Debian/Ubuntu)
wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt-get update && apt-get install -y cuda-toolkit-12-8
```

### Compilação llama.cpp falha — "mathcalls error"
O Makefile já aplica automaticamente os patches necessários para Debian trixie (glibc 2.40+). Se ainda falhar:
```bash
# Limpar e recompilar
rm -rf ~/llama.cpp/build
make build-llama-server
```

### Modelo corrompido
```bash
# Remover e rebaixar
rm data/models/*.gguf
make download-model
make fix-template
```

### Respostas vazias / thinking mode não finaliza
Aumente o `max_tokens` — o modelo usa tokens para o raciocínio interno antes da resposta:
```python
# Para respostas complexas, use pelo menos 300-500 tokens
response = client.chat.completions.create(
    model="qwen3",
    messages=[...],
    max_tokens=500  # mínimo para thinking mode
)
```

---

## Agradecimentos

### Template v18 — froggeric

Este projeto utiliza o **Jinja2 chat template v18** criado por [**froggeric**](https://huggingface.co/froggeric), disponível em:

> **[huggingface.co/froggeric/Qwen-Fixed-Chat-Templates](https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates)**

O template v18 é um **drop-in replacement** para o template oficial Qwen3.6 que corrige múltiplos bugs críticos:

- **KV Cache invalidation** — o template oficial invalida o cache a cada turno em conversas multi-turno, causando re-processamento completo do prompt. O v18 normaliza o whitespace de forma a manter 100% de hit rate no KV cache
- **Tool calling loops** — detecção de erros baseada em estrutura estrita (em vez de substring) elimina falsos positivos em respostas JSON que contêm a palavra "error"
- **Compatibilidade com engines legados** — substituição de `loop.previtem` por indexação de array, corrigindo crashes em builds antigos de llama.cpp e minijinja
- **Thinking mode bypass** — correção de `enable_thinking=false` que não era respeitado em certos fluxos
- **Escalada de erros em tool chains** — sistema de dois níveis com contador `consecutive_failures` para agentic workflows

O template é compatível com LM Studio, llama.cpp, vLLM, MLX e qualquer engine que suporte templates HuggingFace Jinja2.

---

*Modelo base: [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) (Alibaba, Apache 2.0)*  
*Quantização GGUF: [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)*
