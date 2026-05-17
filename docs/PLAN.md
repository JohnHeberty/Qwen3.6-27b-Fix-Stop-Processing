# Plano: Servidor vLLM — Qwen3.6 27B com Template Corrigido

Fonte: https://www.reddit.com/r/Qwen_AI/comments/1stt081/fixed_jinja_chat_templates_for_qwen_35_and_36/

## Contexto

O Qwen3.6 27B tem um bug crítico no template Jinja padrão (`tokenizer_config.json`):
- Tool calls geram `</think>` sem `<think>` aberto → engine trava
- `enable_thinking=false` é ignorado → sempre entra em modo raciocínio
- Filtros Jinja incompatíveis com o engine C++ do vLLM (`|items`, `map('string')`)

**Solução:** baixar o modelo do HuggingFace, substituir o `chat_template` no
`tokenizer_config.json` pelo template corrigido v16 (froggeric), e servir com vLLM.

**Ollama não é usado.** Ele roda na VM mas fica intocado — apenas o vLLM serve o Qwen3.6.

---

## Arquitetura

```
VM Linux (GPU NVIDIA)
│
├── Ollama  (porta 11434) ← intocado, outros modelos
│
└── vLLM    (porta 8000)  ← Qwen3.6 27B com template corrigido
        │
        ├── /opt/qwen-server/model/          ← modelo HF baixado do HuggingFace
        │       tokenizer_config.json        ← chat_template substituído pelo v16
        │
        └── /opt/qwen-server/templates/
                qwen3.6/chat_template-v16.jinja
```

---

## Pré-requisitos de Hardware

| Modelo HF                    | VRAM necessária | Observação                        |
|------------------------------|-----------------|-----------------------------------|
| `Qwen/Qwen3.6-27B-AWQ`       | ~16 GB          | **Recomendado** — quantizado AWQ  |
| `Qwen/Qwen3.6-27B-GPTQ-Int4` | ~16 GB          | alternativa GPTQ                  |
| `Qwen/Qwen3.6-27B`           | ~55 GB (BF16)   | apenas para H100/A100 80GB        |

SO: Ubuntu 22.04 / Debian 12. Python 3.10+. CUDA 12.x. Driver >= 525.

---

## Estrutura de Pastas (na VM)

```
/opt/qwen-server/
├── model/
│   ├── config.json
│   ├── tokenizer_config.json     ← chat_template substituído pelo v16
│   ├── model-00001-of-XXXXX.safetensors
│   └── ...
├── templates/
│   └── qwen3.6/
│       └── chat_template-v16.jinja
├── setup.sh          ← setup inicial (rodar 1x)
├── fix-template.py   ← substitui o template no tokenizer_config.json
├── start-server.sh   ← inicia vLLM
├── qwen-server.service
└── test-api.py
```

---

## Fase 1 — Instalar vLLM e dependências

```bash
# CUDA toolkit (se nao tiver)
sudo apt install -y nvidia-cuda-toolkit

# vLLM — instala junto com PyTorch CUDA
pip install vllm

# Ferramentas de download
pip install huggingface-hub

# Verificar instalacao
python3 -c "import vllm; print(vllm.__version__)"
vllm --version
```

---

## Fase 2 — Baixar o Modelo do HuggingFace

```bash
sudo mkdir -p /opt/qwen-server/model
sudo chown -R $USER:$USER /opt/qwen-server

# Baixar modelo AWQ (~14-16 GB, recomendado)
huggingface-cli download Qwen/Qwen3.6-27B-AWQ \
    --local-dir /opt/qwen-server/model/

# Verificar arquivos baixados
ls -lh /opt/qwen-server/model/
```

> O `tokenizer_config.json` está nessa pasta — é ele que vamos corrigir na Fase 4.

---

## Fase 3 — Baixar o Template Corrigido

```bash
sudo mkdir -p /opt/qwen-server/templates
sudo chown -R $USER:$USER /opt/qwen-server/templates

git clone https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates \
    /opt/qwen-server/templates

# Verificar
ls /opt/qwen-server/templates/qwen3.6/chat_template-v16.jinja
```

---

## Fase 4 — Substituir o Template no Modelo

O script `fix-template.py` lê o `chat_template-v16.jinja` e sobrescreve o
campo `chat_template` dentro do `tokenizer_config.json` do modelo.

```bash
python3 /opt/qwen-server/fix-template.py

# Verificar que funcionou (deve mostrar o inicio do template v16)
python3 -c "
import json
cfg = json.load(open('/opt/qwen-server/model/tokenizer_config.json'))
print(cfg['chat_template'][:120])
"
```

**Por que editar o arquivo em vez de passar `--chat-template` no vLLM?**
O vLLM lê o template do `tokenizer_config.json` por padrão. Editar o arquivo
garante que qualquer cliente que carregue o tokenizer também use o template correto,
sem depender de flags na linha de comando que podem ser esquecidas.

---

## Fase 5 — Subir o Servidor vLLM

```bash
vllm serve /opt/qwen-server/model \
    --host 0.0.0.0 \
    --port 8000 \
    --served-model-name qwen3 \
    --gpu-memory-utilization 0.90 \
    --max-model-len 32768 \
    --enable-prefix-caching \
    --tool-call-parser qwen3_xml \
    --disable-log-requests
```

**Parâmetros críticos:**

| Parâmetro | Valor | Descrição |
|---|---|---|
| `--gpu-memory-utilization` | 0.90 | Reserva 90% da VRAM para o modelo + KV cache |
| `--max-model-len` | 32768 | Contexto máximo (reduzir se faltar VRAM) |
| `--enable-prefix-caching` | flag | Reutiliza KV cache para system prompts idênticos |
| `--tool-call-parser qwen3_xml` | flag | Parser correto para o formato XML do Qwen3 |
| `--served-model-name qwen3` | string | Nome do modelo nas chamadas de API |
| `--port 8000` | 8000 | Sem conflito com Ollama (:11434) |

### Usando o script:
```bash
chmod +x /opt/qwen-server/start-server.sh
/opt/qwen-server/start-server.sh
```

---

## Fase 6 — Serviço systemd (produção)

```bash
# Editar qwen-server.service: ajustar User= para o usuario da VM
sudo cp /opt/qwen-server/qwen-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable qwen-server
sudo systemctl start qwen-server

# Logs em tempo real
journalctl -u qwen-server -f
```

---

## Fase 7 — Testar

```bash
# Health
curl http://localhost:8000/health

# Modelos disponíveis
curl http://localhost:8000/v1/models

# Chat
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3",
    "messages": [{"role":"user","content":"Olá! Quanto é 7x8?"}],
    "max_tokens": 128,
    "temperature": 0.6
  }' | python3 -m json.tool

# Suite completa de testes
python3 /opt/qwen-server/test-api.py
```

---

## Convivência com o Ollama

| Serviço | Porta  | Usado para         |
|---------|--------|--------------------|
| Ollama  | 11434  | outros modelos     |
| vLLM    | 8000   | Qwen3.6 27B        |

Nenhum interfere no outro. Clientes OpenAI-compatible:
- `base_url = "http://<vm-ip>:8000/v1"` → Qwen3.6 via vLLM
- `base_url = "http://<vm-ip>:11434/v1"` → modelos Ollama

---

## Checklist

- [ ] `nvidia-smi` mostra GPU disponível
- [ ] `vllm --version` executa sem erro
- [ ] Modelo baixado em `/opt/qwen-server/model/`
- [ ] `fix-template.py` executado com sucesso
- [ ] `tokenizer_config.json` tem o template v16 (verificar primeiro 100 chars)
- [ ] `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] `python3 test-api.py` → todos os testes passam
- [ ] Ollama ainda responde em `:11434` (intocado)
