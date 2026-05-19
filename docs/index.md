# Documentation — Qwen3.6 27B Local Server

Documentation organized following the **[Diátaxis](https://diataxis.fr)** framework: each section serves a different reader intent.

---

## Tutorials — learning by doing

For those setting up the project for the first time.

| Document | Covers |
|---|---|
| [Getting Started](tutorials/getting-started.md) | Requirements, `.env` setup, `make setup` step by step, verification |

---

## How-To — completing tasks

For those who already have the server running and need to do something specific.

| Document | Covers |
|---|---|
| [Use the API](how-to/api-usage.md) | Chat, streaming, system prompt, thinking mode, tool calling |
| [Integrate with LiteLLM](how-to/litellm.md) | Proxy config, fix "context size exceeded" |
| [Integrate with OpenCode](how-to/opencode.md) | Ready-to-use config for the terminal AI assistant |
| [Production & operations](how-to/production.md) | systemd, Ollama coexistence, troubleshooting |

---

## Reference — looking things up

For quick lookup of values, commands and variables.

| Document | Covers |
|---|---|
| [`make` commands](reference/make-commands.md) | All targets with descriptions |
| [Configuration variables](reference/configuration.md) | All `.env` variables with defaults |

---

## Explanation — understanding

For those who want to understand the technical decisions behind the project.

| Document | Covers |
|---|---|
| [Architecture](explanation/architecture.md) | Why GGUF, llama-server, folder structure |
| [Template v18 (froggeric)](explanation/template-v18.md) | What the template fixes and author credits |

---

*Server running at `http://localhost:8000/v1` · model `qwen3` · 98,304 token context*
