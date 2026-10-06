# Qwen3.8-27B — servidor local de inferência

**Modelo:** Qwen3.8-27B Q8_0 (denso 27B, híbrido Gated DeltaNet + Atenção, MTP nativo + visão nativa)
**GPU:** 2x RTX 3090 (48 GB) | **API:** `http://localhost:8080/v1` | **Contexto:** 262k (input 192k + saída 65k)

## Configuração

- **Template:** embutido no GGUF (sem `--chat-template-file`)
- **Sampling:** valores oficiais de thinking-mode — `temp=1.0, top_p=0.95, top_k=20, min_p=0.0`,
  sem penalidades (`presence=0.0, repeat=1.0, frequency=0.0`)
- **Raciocínio:** `on`, formato `deepseek` (expõe `message.reasoning_content`).
  A profundidade do thinking é definida por `REASONING_EFFORT=low` — o único valor cujo ramo de template
  efetivamente pede thinking breve (`medium` injeta *nada*, `xhigh` é o padrão do próprio modelo e
  pede deliberação exaustiva). `REASONING_BUDGET=8192` é uma rede de segurança contra loops de
  pensamento, não um freio de verbosidade: atingi-lo corta o raciocínio no meio e degrada tool calls.
  `REASONING_PRESERVE=false` mantém blocos `</think>` antigos fora do histórico.
- **Decodificação especulativa:** MTP nativo, `n=3` (`--spec-type draft-mtp`)
- **KV cache:** `q8_0` (f16 não cabe junto com um modelo Q8_0 de 29 GB em 262k)
- **Visão:** nativa, via `mmproj-F16.gguf` do mesmo repositório
- **Sampler DRY:** off (`DRY_MULTIPLIER=0`) — nunca re habilite para coding, corrompe caminhos de arquivo longos
- **WebUI de chat:** on (`WEBUI=true`) — a UI de chat embutida do llama-server é servida em
  `GET /`, ou seja, a mesma porta da API. Sem instalação extra, sem segundo processo.

Referência completa de parâmetros: [`.env`](.env). Configs alternativas de modelo/GPU:
[`env-examples/`](env-examples/).

## Comandos

```bash
make start       # primeiro plano
make start-bg    # segundo plano, logs em data/logs/server.log
make stop        # para o servidor
make status      # está rodando, e em qual modelo
make test        # tests/test_api.py — API, tool calling, streaming
make logs        # tail do log
```

Setup completo: `make setup` (pipeline zero-dependência: deps do sistema → CUDA → venv → build
`llama-server` → download do GGUF). Mais alvos: `make help`.

## Desempenho medido

| Métrica | Q8_0 + MTP n=3 + KV q8_0 @ 262k |
|---|---|
| Decode, contexto curto | 36-40 tok/s |
| Decode, regime real de agente (contexto longo) | 24-26 tok/s |
| Processamento de prompt | 355-715 tok/s |
| VRAM | ~21.4 GB (GPU 0) + ~22.7 GB (GPU 1) |

## Downstream

`infra/` contém a camada de integração: gateway LiteLLM (`:4000`, `make litellm-start`), config
do OpenCode, unidades systemd + watchdog, e logrotate. Todos apontam para `:8080` / modelo
`qwen3.8-27b` e devem ser mantidos em sync com `.env`.
