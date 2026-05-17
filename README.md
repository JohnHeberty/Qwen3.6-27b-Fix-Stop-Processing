# qwen3 — Servidor vLLM Qwen3.6 27B

Serve o modelo **Qwen3.6 27B AWQ** via vLLM com API 100% compatível com OpenAI.

## Quick start

```bash
make setup      # instala tudo e baixa o modelo (~20 GB) — rodar 1x
make start      # sobe o servidor
make test       # valida os 6 endpoints
```

---

## API OpenAI-compatible

| Item | Valor |
|---|---|
| Base URL | `http://<ip>:8000/v1` |
| Porta | `8000` |
| Model name | `qwen3` |
| API key | qualquer string (não validada) |

### Python

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="nao-precisa")

resp = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "Olá!"}],
    max_tokens=256,
    temperature=0.6,
)
print(resp.choices[0].message.content)
```

### curl

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3",
    "messages": [{"role": "user", "content": "Olá!"}],
    "max_tokens": 256
  }'
```

### Thinking mode (raciocínio estendido)

```python
resp = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "Resolva: ..."}],
    extra_body={"enable_thinking": True},
)
```

---

## Comandos disponíveis

```
make setup            Instala dependencias e baixa o modelo (rodar 1x)
make start            Sobe o servidor em foreground (Ctrl+C para parar)
make start-bg         Sobe em background (log em data/logs/vllm.log)
make stop             Para o servidor
make restart          Para e sobe em background
make status           Mostra se esta rodando e uso de VRAM
make logs             Acompanha o log em tempo real
make test             Roda a suite de testes da API
make fix-template     Aplica o template froggeric no tokenizer
make install-service  Instala como servico systemd (inicia no boot)
```

---

## Configuração (variáveis de ambiente)

| Variável | Padrão | Descrição |
|---|---|---|
| `PORT` | `8000` | Porta do servidor |
| `GPU_MEM` | `0.948` | Fração da VRAM usada (otimizado para 3090 24GB) |
| `MAX_MODEL_LEN` | `6272` | Contexto máximo em tokens (máximo possível na placa) |
| `SERVED_NAME` | `qwen3` | Nome do modelo na API |

Sobrescreva na linha de comando:
```bash
MAX_MODEL_LEN=4096 make start
```

---

## Produção (systemd — inicia no boot)

```bash
make install-service
# ou manualmente:
sudo cp infra/qwen-server.service /etc/systemd/system/
sudo systemctl enable --now qwen-server
sudo journalctl -u qwen-server -f
```

---

## Estrutura do projeto

```
qwen3/
├── Makefile
├── requirements.txt
├── data/
│   ├── models/      modelo QuantTrio/Qwen3.6-27B-AWQ (~20 GB, gitignored)
│   ├── templates/   templates jinja froggeric
│   ├── logs/        logs de runtime (gitignored)
│   └── backups/     backups do tokenizer_config.json (gitignored)
├── scripts/
│   ├── setup.sh     instalação completa (rodar 1x)
│   └── start-server.sh
├── src/
│   └── fix_template.py
├── tests/
│   └── test_api.py
├── infra/
│   └── qwen-server.service
└── docs/
    └── PLAN.md      documentação detalhada
```

---

## Requisitos de hardware

- GPU NVIDIA com ≥ 24 GB VRAM (testado na RTX 3090)
- Driver ≥ 590 (CUDA 13.x)
- Python 3.13+
- ~25 GB de espaço em disco

Documentação detalhada: [docs/PLAN.md](docs/PLAN.md)
