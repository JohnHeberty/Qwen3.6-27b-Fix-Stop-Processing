# infra/ — configuração dos clientes

Configs dos três consumidores do servidor. **Todos precisam concordar sobre a janela de contexto** —
se divergirem, o cliente calcula a compactação errado e o turno morre no meio.

| Arquivo | Onde roda | O que ajustar ao mudar `MAX_MODEL_LEN` |
|---|---|---|
| `litellm/config.yaml` | máquina do LiteLLM | `context_window`, `max_input_tokens`, `max_output_tokens` |
| `opencode/config.json` | máquina do OpenCode | `limit.context`, `limit.output` |
| `openclaw/openclaw.json` | máquina do OpenClaw | `contextWindow`, `contextTokens`, `maxTokens`, `compaction.*` |

O OpenClaw e o OpenCode rodam em **outras máquinas** — as cópias aqui são a referência versionada;
aplicar exige copiar para lá (ou usar `openclaw config set`).

## Context Window Math (engine atual: vLLM)

```
MAX_MODEL_LEN (.env)                49.152   janela TOTAL
  − reserva de saída                 8.192
  = orçamento de entrada            40.960
```

**De onde vem o 49.152.** Com `KV_CACHE_DTYPE=fp8_e5m2` o vLLM aloca **56.631** tokens de KV nesta
RTX 3090 (pesos INT4 ocupam ~18 GB dos 24 GB). O 49.152 é o valor medido a **82,44 tok/s** — ver
[`docs/vllm-vs-llamacpp.md`](../docs/vllm-vs-llamacpp.md). Dá para subir até ~56k, mas não foi medido.

## ⚠️ Duas mudanças em relação ao llama.cpp

**A janela caiu de 106.496 para 49.152.** Consequência prática: a compactação vai disparar com muito
mais frequência. Os prompts medidos em produção em 28/07 iam de 69k a 101k — **acima desta janela**.
Espere compactação em quase toda tarefa de pesquisa longa.

Sobrando ~41k de entrada, e descontando o prompt de sistema (~20k com `workspace-AGENTS.md` e
`workspace-TOOLS.md` enxutos + schemas das ferramentas), restam **~20k para a conversa em si**. Por
isso `keepRecentTokens` caiu para 8.000: com 32.000 a compactação não conseguiria caber no orçamento.

**A saída caiu de 16.384 para 8.192.** Com 49k de janela, reservar 16k para saída deixaria pouco para
entrada. Isso reintroduz o limite que quebrava a escrita de HTML numa tacada — o agente precisa gerar
arquivo grande em partes (`write` inicial + `edit`), o que o `workspace-AGENTS.md` já orienta.

## ⚠️ O campo do raciocínio mudou de nome

| Engine | Campo |
|---|---|
| llama.cpp (`--reasoning-format deepseek`) | `reasoning_content` |
| **vLLM 0.26** (`--reasoning-parser qwen3`) | **`reasoning`** |

Não há flag de compatibilidade no vLLM. O `opencode/config.json` já aponta para `reasoning`.
**Falta confirmar se o LiteLLM normaliza** — se não normalizar, os clientes param de exibir o
raciocínio. Teste:

```bash
curl -s localhost:4000/v1/chat/completions -H 'Authorization: Bearer <key>' \
  -d '{"model":"qwen","messages":[{"role":"user","content":"oi"}],"max_tokens":300}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["choices"][0]["message"].keys())'
```

## Ollama não convive mais

O llama-server descarregava o Ollama e dividia a placa. O vLLM **pré-aloca 97% da VRAM** — o Ollama
precisa ficar parado enquanto o vLLM roda. O `scripts/start-vllm.sh` avisa e tenta descarregar, mas
não mata o serviço.
