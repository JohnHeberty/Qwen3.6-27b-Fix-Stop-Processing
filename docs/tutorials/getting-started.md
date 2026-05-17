# Primeiros Passos

Do zero ao servidor rodando.

---

## Requisitos

### Hardware

| Componente | Mínimo | Testado |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | RTX 3090 (24 GB) |
| RAM | 16 GB | 32 GB |
| Disco livre | 25 GB | 30 GB |

> O modelo Q4_K_M ocupa ~16 GB de VRAM. Com 24 GB, sobram ~8 GB para KV cache — suficiente para 63.488 tokens de contexto.

### Software

| Requisito | Versão mínima | Como verificar |
|---|---|---|
| OS | Debian 12 / Ubuntu 22.04+ | `lsb_release -a` |
| Driver NVIDIA | ≥ 590 | `nvidia-smi` |
| CUDA Toolkit | 12.x em `/usr/local/cuda` | `nvcc --version` |
| Git | qualquer | `git --version` |

O `make setup` instala automaticamente Python, cmake e build-essential. O único pré-requisito manual é o driver NVIDIA com CUDA toolkit.

**Instalar CUDA toolkit se necessário (Debian/Ubuntu):**
```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt-get update && apt-get install -y cuda-toolkit-12-8
```

---

## Passo 1 — Clonar o repositório

```bash
git clone https://github.com/JohnHeberty/Qwen3.6-27b-Fix-Stop-Processing.git qwen3
cd qwen3
```

---

## Passo 2 — Configurar `.env`

```bash
cp .env.example .env
```

Edite `.env` e preencha o token obrigatório:

```bash
HUGGINGFACE_TOKEN=hf_seu_token_aqui
```

Obtenha seu token em: https://huggingface.co/settings/tokens

Os outros valores já têm padrões adequados. Consulte a [referência de configuração](../reference/configuration.md) para ajustes.

---

## Passo 3 — Executar `make setup`

```bash
make setup
```

O setup executa **8 etapas** com sentinel — cada uma verifica se já foi feita antes de agir. Rodar duas vezes é seguro.

| Etapa | Target | O que faz |
|---|---|---|
| `[1]` | `make install-system-deps` | apt: python3, cmake, git, build-essential, curl |
| `[2]` | `make setup-cuda` | Verifica CUDA toolkit, registra libcudart no sistema |
| `[3]` | `make create-venv` | Cria `.venv` Python isolado |
| `[4]` | `make install-python-deps` | pip: gguf, huggingface-hub, openai, requests |
| `[5]` | `make build-llama-server` | Clona llama.cpp, aplica patches Debian trixie, compila com CUDA |
| `[6]` | `make build-llama-cpp-python` | Compila llama-cpp-python com GPU offload |
| `[7]` | `make download-model` | Baixa `Qwen3.6-27B-Q4_K_M.gguf` (~16 GB) do HuggingFace |
| `[8]` | `make fix-template` | Patcha o GGUF com o template v18 (patch binário com alinhamento correto) |

Tempo estimado: **20–40 minutos** (depende da velocidade de download e da CPU para compilação).

---

## Passo 4 — Iniciar o servidor

```bash
make start
```

Aguarde a mensagem `llama server listening` (30–60 segundos para carregar o modelo).

Para rodar em background:
```bash
make start-bg
make logs   # acompanhar
```

---

## Passo 5 — Verificar

```bash
make status
# Servidor: RODANDO em http://localhost:8000/v1 (modelo: qwen3)
# GPU:     NVIDIA GeForce RTX 3090, 21000 MiB used, 3100 MiB free

make test
# → 6/6 testes passaram
```

---

## Próximos passos

- [Usar a API](../how-to/api-usage.md) — exemplos de chat, streaming, thinking mode e tool calling
- [Referência de comandos](../reference/make-commands.md) — todos os targets disponíveis
