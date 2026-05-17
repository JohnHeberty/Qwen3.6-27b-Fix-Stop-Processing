# Referência — Comandos `make`

```bash
make help   # lista todos os targets com descrição
```

---

## Setup (zero-dependência)

| Comando | Descrição |
|---|---|
| `make setup` | Pipeline completa: executa as 8 etapas abaixo em ordem |
| `make install-system-deps` | `[1]` apt: python3, cmake, git, build-essential, curl |
| `make setup-cuda` | `[2]` Verifica CUDA toolkit, registra libcudart |
| `make create-venv` | `[3]` Cria `.venv` Python isolado |
| `make install-python-deps` | `[4]` pip: gguf, huggingface-hub, openai, requests |
| `make build-llama-server` | `[5]` Clona e compila llama-server com CUDA |
| `make build-llama-cpp-python` | `[6]` Compila llama-cpp-python com GPU offload |
| `make download-model` | `[7]` Baixa modelo GGUF do HuggingFace (~16 GB) |
| `make fix-template` | `[8]` Patcha o GGUF com template v18 |

Cada etapa usa um **sentinel** — verifica se já foi feita antes de agir. Rodar `make setup` duas vezes é seguro.

---

## Servidor

| Comando | Descrição |
|---|---|
| `make start` | Sobe o servidor em foreground (Ctrl+C para parar) |
| `make start-bg` | Sobe em background (log em `data/logs/server.log`) |
| `make stop` | Para o servidor (libera VRAM) |
| `make restart` | Para e sobe em background |
| `make status` | Estado do servidor + uso de VRAM |
| `make logs` | `tail -f data/logs/server.log` |
| `make test` | Roda os 6 testes de integração da API |

---

## Serviço systemd

| Comando | Descrição |
|---|---|
| `make install-service` | Registra `qwen-server.service` (sem auto-start) |
| `make enable-service` | Habilita auto-start no boot + inicia agora |
| `make disable-service` | Desabilita auto-start + para o serviço |
| `make start-service` | Inicia via systemd sem habilitar no boot |

---

## Ollama / GPU

| Comando | Descrição |
|---|---|
| `make configure-ollama` | Reduz `OLLAMA_KEEP_ALIVE` de 30 min para 5 min |
| `make ollama-unload` | Força Ollama a liberar todos os modelos da VRAM agora |

---

## LiteLLM

| Comando | Descrição |
|---|---|
| `make litellm-start` | Sobe proxy LiteLLM na porta 4000 com `infra/litellm_config.yaml` |

---

## Limpeza

| Comando | Descrição |
|---|---|
| `make clean` | Remove modelo GGUF, logs e `.venv` (mantém código e templates) |

---

## Sobrescrever variáveis

Qualquer variável do `.env` pode ser sobrescrita inline:

```bash
N_CTX=32768 make start
PORT=9000 make start
```
