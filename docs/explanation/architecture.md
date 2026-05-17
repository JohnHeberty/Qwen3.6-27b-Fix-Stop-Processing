# Arquitetura

---

## O que é este projeto

Um servidor de inferência local para o **Qwen3.6 27B** com API compatível com OpenAI. Qualquer cliente que fala com a OpenAI (SDK Python, LiteLLM, OpenCode, curl) funciona sem modificação — basta trocar o `base_url` para `http://localhost:8000/v1`.

---

## Decisões técnicas

### Por que llama-server em vez de vLLM?

| Aspecto | vLLM (anterior) | llama-server (atual) |
|---|---|---|
| Formato do modelo | AWQ (safetensors, ~20 GB) | GGUF Q4_K_M (~16 GB) |
| Contexto na RTX 3090 | 6.272 tokens | 63.488 tokens |
| Template customizável | não (limitado) | sim (patch binário direto no GGUF) |
| Compilação necessária | não | sim (com CUDA) |

O modelo AWQ safetensors com a arquitetura DeltaNet+Mamba do Qwen3_5 deixava apenas ~6.272 tokens de contexto disponíveis na RTX 3090. O GGUF Q4_K_M ocupa 16 GB de VRAM, deixando ~8 GB para KV cache — suficiente para 63.488 tokens.

### Por que GGUF Q4_K_M?

- Quantização de alta qualidade com iMatrix — boa relação qualidade/tamanho
- 16 GB de VRAM para pesos, ~8 GB restantes para KV cache na RTX 3090 (24 GB)
- Sem dependência de Python para inferência (llama-server é C++)
- Template Jinja2 patchável diretamente no binário

### Por que o template v18 (froggeric)?

O template oficial do Qwen3.6 tem bugs críticos em KV cache, tool calling e thinking mode. O v18 corrige todos eles. O patch é feito diretamente no GGUF (binário) via `src/fix_template.py` para garantir que o template correto é usado independente de como o servidor é iniciado.

Veja detalhes em [explanation/template-v18.md](template-v18.md).

### Por que llama.cpp compilado do fonte?

A versão pip (`llama-cpp-python`) usa um binário pré-compilado genérico. Compilar do fonte com `-DGGML_CUDA=ON` garante:
- Uso total da GPU (todos os layers offloadados)
- Patches aplicados ao código-fonte (desabilitar fused GDN — necessário para a arquitetura híbrida do Qwen3_5 na SM 8.6)
- Otimizações específicas para a placa

---

## Arquitetura do Qwen3_5

O Qwen3.6 27B usa arquitetura **híbrida Qwen3_5**: 64 layers total, sendo 48 de atenção linear (DeltaNet/GDN) e 16 de atenção completa (full attention). O kernel CUDA de **Fused Gated Delta Net** tem um bug em GPUs SM 8.6 (RTX 3090) que produz output inválido. O Makefile aplica um patch no fonte do llama.cpp para desabilitar esse kernel antes de compilar.

---

## Estrutura de pastas

```
qwen3/
├── .env                    configuração local (não versionado)
├── .env.example            template de configuração (versionado)
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
│   ├── setup.sh            instalação (chamado pelo Makefile)
│   └── start-server.sh     inicialização do servidor
│
├── src/
│   └── fix_template.py     patch binário do GGUF com template v18
│
├── tests/
│   └── test_api.py         testes de integração da API (6 endpoints)
│
├── infra/
│   ├── qwen-server.service unidade systemd para autostart
│   ├── litellm_config.yaml config do LiteLLM proxy
│   └── opencode.json       config do OpenCode terminal assistant
│
└── docs/                   documentação (Diátaxis)
    ├── index.md
    ├── tutorials/
    ├── how-to/
    ├── reference/
    └── explanation/
```

---

## Fluxo de dados

```
Cliente (Python SDK / curl / OpenCode)
    │
    ▼  HTTP POST /v1/chat/completions
llama-server (porta 8000)
    │  lê
    ▼
data/models/Qwen3.6-27B-Q4_K_M.gguf   ← template v18 patchado dentro do arquivo
    │  offload
    ▼
GPU (RTX 3090, 24 GB VRAM)
    │  gera tokens
    ▼
llama-server → resposta streaming/completa → Cliente
```
