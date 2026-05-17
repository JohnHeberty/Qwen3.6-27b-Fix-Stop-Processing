# Produção e Operação

---

## Serviço systemd

### Instalar (sem auto-start)

```bash
make install-service
```

Registra o serviço `qwen-server` no systemd. Por padrão **não** habilita auto-start no boot — use os targets abaixo para controlar isso.

### Auto-start no boot

```bash
make enable-service    # habilita auto-start + inicia agora
make disable-service   # desabilita auto-start + para o serviço
```

> **Atenção:** auto-start conflita com o Ollama se ambos usam a GPU. Veja a seção [Coexistência com Ollama](#coexistência-com-ollama) abaixo.

### Gerenciar o serviço manualmente

```bash
sudo systemctl status qwen-server       # estado atual
sudo systemctl start qwen-server        # iniciar
sudo systemctl stop qwen-server         # parar
sudo systemctl restart qwen-server      # reiniciar
sudo journalctl -u qwen-server -f       # logs em tempo real
```

### Instalar manualmente (sem Makefile)

```bash
sudo cp infra/qwen-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qwen-server
```

---

## Coexistência com Ollama

O llama-server e o Ollama competem pelos 24 GB de VRAM da GPU. O `make start` já descarrega modelos do Ollama automaticamente antes de iniciar. Para ajuste permanente:

```bash
make configure-ollama
# → reduz OLLAMA_KEEP_ALIVE de 30 min para 5 min
# → Ollama libera a VRAM 5 min após o último uso (em vez de 30)
```

Para liberar VRAM do Ollama manualmente a qualquer momento:

```bash
make ollama-unload
```

---

## Solução de Problemas

### Servidor não sobe — "model not found"

```bash
ls -lh data/models/*.gguf
# Se vazio:
make download-model
make fix-template
```

### "CUDA out of memory"

```bash
nvidia-smi   # verificar uso atual
make stop    # parar llama-server
make ollama-unload   # liberar Ollama
make start   # tentar novamente
```

O Q4_K_M usa ~21 GB de VRAM. Outros processos CUDA devem ser encerrados antes de iniciar.

### "CUDA não encontrado" — `[2] setup-cuda FAIL`

```bash
nvcc --version   # deve mostrar versão 12.x

# Se não encontrado:
wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt-get update && apt-get install -y cuda-toolkit-12-8
```

### Compilação llama.cpp falha — "mathcalls error"

O Makefile aplica os patches necessários para Debian trixie (glibc 2.40+) automaticamente. Se ainda falhar:

```bash
rm -rf ~/llama.cpp/build
make build-llama-server
```

### Modelo corrompido ou template não aplicado

```bash
rm data/models/*.gguf
make download-model
make fix-template
```

### Respostas vazias ou thinking mode não finaliza

Use `max_tokens` ≥ 300–500 — o modelo consome tokens para o raciocínio interno antes de responder:

```python
response = client.chat.completions.create(
    model="qwen3",
    messages=[...],
    max_tokens=500
)
```
