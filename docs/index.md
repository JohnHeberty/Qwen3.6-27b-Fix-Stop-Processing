# Documentação — Qwen3.6 27B Servidor Local

Documentação organizada segundo o framework **[Diátaxis](https://diataxis.fr)**: cada seção serve uma intenção diferente do leitor.

---

## Tutorials — aprender fazendo

Para quem está configurando o projeto pela primeira vez.

| Documento | O que cobre |
|---|---|
| [Primeiros Passos](tutorials/getting-started.md) | Requisitos, configuração do `.env`, `make setup` passo a passo, verificação |

---

## How-To — executar tarefas

Para quem já tem o servidor rodando e precisa fazer algo específico.

| Documento | O que cobre |
|---|---|
| [Usar a API](how-to/api-usage.md) | Chat, streaming, system prompt, thinking mode, tool calling |
| [Integrar com LiteLLM](how-to/litellm.md) | Config do proxy, fix "context size exceeded" |
| [Integrar com OpenCode](how-to/opencode.md) | Config pronta para o terminal AI assistant |
| [Produção e operação](how-to/production.md) | systemd, Ollama coexistência, solução de problemas |

---

## Reference — consultar

Para lookup rápido de valores, comandos e variáveis.

| Documento | O que cobre |
|---|---|
| [Comandos `make`](reference/make-commands.md) | Todos os targets com descrição |
| [Variáveis de configuração](reference/configuration.md) | Todas as variáveis do `.env` com padrões |

---

## Explanation — entender

Para quem quer entender as decisões técnicas por trás do projeto.

| Documento | O que cobre |
|---|---|
| [Arquitetura](explanation/architecture.md) | Por que GGUF, llama-server, estrutura de pastas |
| [Template v18 (froggeric)](explanation/template-v18.md) | O que o template corrige e créditos ao autor |

---

*Servidor rodando em `http://localhost:8000/v1` · modelo `qwen3` · contexto 63.488 tokens*
