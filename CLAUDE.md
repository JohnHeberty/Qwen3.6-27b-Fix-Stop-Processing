# CLAUDE.md

Este arquivo fornece orientações ao Claude Code (claude.ai/code) ao trabalhar com código neste repositório.

## O que este projeto é

Um servidor local de inferência para **Qwen3.8-27B** (denso 27B, híbrido Gated DeltaNet + Atenção, GGUF via
`llama-server` do llama.cpp) expondo uma API compatível com OpenAI em `http://localhost:8080/v1`.
Roda em 2x RTX 3090 (48 GB VRAM). Pipeline zero-dependência, dirigido por `make`: clone,
copie uma config de `env-examples/` para `.env`, `make setup`, `make start`.

Recursos do Qwen3.8-27B:
- **Visão nativa** (entendimento de imagem + vídeo via mmproj-F16.gguf, sem servidor de visão separado)
- **MTP nativo** (Multi-Token Prediction) para decodificação especulativa (MTP n=3; 36-40 tok/s decode em
  contexto curto, 24-26 tok/s no regime real de agente de contexto longo; 355-715 tok/s processamento de prompt)
- **Arquitetura híbrida**: 16×(3×Gated DeltaNet + FFN) + 1×(Atenção Gated + FFN) por bloco
- **Contexto nativo de 262K** (extensível a 1M com escala RoPE)
- **Modo de raciocínio/thinking** (ligado por padrão, controlado via REASONING_BUDGET)

Modelos anteriores testados e arquivados (ainda disponíveis como configs .env):
- Qwen3.6-27B Q4_K_M + MTP n=3 (16GB, ~56 tok/s)
- Qwen3.5-35B-A3B APEX MTP n=2 (Ornith, 24GB, ~85 tok/s)

O repositório é bilíngue: `Makefile`, scripts shell, comentários em `.env`, `README.md` e
`CLAUDE.md` estão em português (pt-BR). Mantenha o idioma existente ao editar um dado arquivo.
(`docs/` existe mas está vazio — notas antigas citam caminhos `docs/...` que não mais existem.)

## Comandos

Tudo é dirigido pelo `Makefile` (`make help` para a lista completa). Variáveis vêm de
`.env` (comece de um dos arquivos `env-examples/<gpu-count>/<config>/`) e podem ser sobrescritas
inline, ex.: `N_CTX=106496 make start`.

**Setup** (idempotente — cada etapa tem sentinel, seguro reexecutar):
```bash
make setup                    # pipeline completo: deps -> CUDA -> venv -> build llama-server -> download modelo
make build-llama-server       # compila llama-server com CUDA (clona llama.cpp se não existir, aplica grammar patch)
                              # patch = llama-cpp-grammar-patches.patch (regex de âncora auto + eleva
                              # MAX_REPETITION_THRESHOLD 2000 -> 100000). Sumiu do repositório
                              # e foi recuperado da árvore de trabalho ~/llama.cpp em 2026-08-17;
                              # sem ele uma rebuild silenciosamente dropa as duas mudanças (só um WARN é impresso).
make rebuild-llama-server     # force clean rebuild
make update-llama-server      # git pull llama.cpp + reaplica patches + rebuild
make download-model           # baixa GGUF do HuggingFace (precisa HUGGINGFACE_TOKEN no .env)
```

**Ciclo de vida do servidor:**
```bash
make start        # primeiro plano (Ctrl+C para parar)
make start-bg     # segundo plano, logs em data/logs/server.log
make stop / restart / status / logs
```
`make start`/`start-bg` descarrega automaticamente modelos Ollama da VRAM primeiro (GPU é compartilhada).

**Testes / benchmarks** (requerem o servidor rodando em :8080):
```bash
make test                       # tests/test_api.py — testes de integração
python3 tests/test_api.py       # idem, executado diretamente
python3 tests/bench_decode.py   # throughput de decode
python3 tests/test-128k.py      # smoke test de contexto longo
```
NOTA: `make benchmark` e `make benchmark-sweep` estão **quebrados** — ambos invocam `tests/benchmark.py`,
que não existe no repositório. Use `tests/bench_decode.py` ou `scripts/bench-speed.sh`
(o último ainda referencia caminhos de modelos da era Qwen3.6 e precisa de atualização antes de rodar).

**Integrações:**
```bash
make litellm-start                  # proxy LiteLLM em :4000 (infra/litellm/config.yaml)
```

**Limpeza:**
```bash
make clean            # remove modelo GGUF, logs, .venv (mantém código/templates)
make clean-logs       # apaga logs com mais de LOG_RETENTION_DAYS
make cron-clean-logs  # instala cron diário para o acima
```

## Arquitetura

**Fluxo de config:** `.env` → `Makefile` (lê variáveis `.env`, aplica fallbacks, dirige alvos de build/setup)
→ `scripts/start-server.sh` (re-lê `.env`, aplica seus próprios fallbacks, traduz cada variável
em uma flag CLI do `llama-server`) → o binário `llama-server` compilado. Ao alterar um parâmetro de runtime
(tamanho de contexto, quant de cache, sampling, MTP), a fonte da verdade é `.env`; `start-server.sh`
só repassa.

**Alavancas de runtime principais (todas no `.env`):**
- `MODEL_FILE` / escolha de quantização (Q8_0/Q4_K_M) — trade-off entre contexto máximo e tok/s.
  Atual: Q8_0 (28GB) com KV q8_0 em 262k de contexto.
- `ENABLE_MTP` + `MTP_TOKENS` — decodificação especulativa Multi-Token Prediction usando as
  cabeças MTP embutidas do modelo (sem modelo draft separado). Atual: MTP n=3 (~36-40 tok/s decode medido).
- `CACHE_TYPE_K` / `CACHE_TYPE_V` — quantização do KV cache. Atual: q8_0 (f16 não cabe com modelo Q8_0).
- `N_CTX` — janela de contexto. Atual: 262144 (262k). KV f16 requer reduzir a 131k ou quant menor.
- `N_PARALLEL` — deve permanecer `1` (evita bugs de split do KV cache).
- `TEMPLATE_FILE` — vazio = usa template embutido no GGUF (arquitetura qwen35 do Qwen3.8, sem custom necessário).
- `MMPROJ` — caminho para o arquivo mmproj para visão nativa. Atual: `mmproj-F16.gguf`.
- `REASONING_BUDGET` — teto duro de tokens de thinking (8192; -1 = off). É uma **guilhotina, não um freio**:
  ao atingi-lo o llama.cpp força-fecha `</think>` e faz o modelo responder no meio do pensamento,
  o que destrói a qualidade de tool calls. Não aperte para reduzir verbosidade — aperte
  `REASONING_EFFORT` em vez disso. (Aprenda na marra: 4096 foi tentado em 2026-08-17 e 90 de 674
  requisições reais o atingiram.)
- `REASONING_MODE` / `REASONING_FORMAT` — `on` / `deepseek` para suporte a reasoning_content.
- `REASONING_EFFORT` — repassado como `--chat-template-kwargs '{"reasoning_effort":"..."}'` (não há
  flag `--reasoning-effort`). Válido: `low`|`medium`|`xhigh`; `high` é um **alias de `xhigh`**,
  qualquer outra coisa faz o template lançar exceção e a requisição falhar. Leia o template
  (`GET /props`) antes de confiar nesses nomes — o que cada valor *injeta* não é o que os nomes sugerem:
  - `xhigh` (padrão do template) → "think carefully, validate key assumptions, consider alternatives…"
  - `medium` → **nada**. Não há ramo `medium` no template, então
    `reasoning_instructions` permanece vazio. É "sem orientação", não "esforço médio".
  - `low` → "Keep your thinking brief and focused, moving directly to the conclusion."
  Atual: `low` — o único valor que efetivamente pede thinking curto. `medium` foi usado brevemente
  e produziu thinking longo que depois atingiu `REASONING_BUDGET`.
- `REASONING_PRESERVE` — `false` aqui → `--no-reasoning-preserve`. O template do Qwen3.8 mantém
  `preserve_thinking` ligado por padrão, então cada bloco `</think>` anterior permanece no histórico e
  cada passo do agente re-alimenta todo o raciocínio acumulado, inflando o tamanho do prompt e a latência
  ao longo de uma sessão. Vazio = padrão do template.
- `DRY_MULTIPLIER` — OFF por padrão (0). Não habilite para coding (trunca caminhos de arquivo).
- `CAPTURE_LOG` — `false` por padrão. `true` loga conteúdo de request/response para depuração.
- `WEBUI` — `true` → `--webui`, `false` → `--no-webui`. O llama-server serve uma UI de chat SvelteKit em
  `GET /` na mesma porta da API, então `http://localhost:8080` é um client de chat funcional sem
  instalação extra. Habilitado por padrão upstream; fixado explicitamente aqui. Duas pegadinhas: ele
  compartilha o slot único (`N_PARALLEL=1`), então um chat da UI entra na fila atrás de qualquer
  requisição de agente em andamento; e ele é servido **apenas gzip**, então `curl` sem
  `--compressed` recebe `HTTP 415 Error: gzip is not supported by this browser` — navegadores não
  são afetados. Útil para testar `reasoning_effort`, `enable_thinking` e sampling por requisição
  (a UI os envia no body, sobrescrevendo o servidor) sem restart.

**O sampling do servidor é apenas um padrão — o body da requisição ganha, mas apenas para os campos
que o client efetivamente envia.** Medido precisamente em 2026-08-18 lendo `GET /slots` enquanto
uma requisição real do OpenCode estava em voo (sem capture nem restart — essa é a forma mais barata
de ver o sampling efetivo por requisição):
- `temperature`, `top_k`, `min_p`, `presence_penalty`, `frequency_penalty`, `repeat_penalty`
  chegaram com os **valores do `.env`** → o client não os envia, `.env` governa.
- `top_p` chegou como **1.0** enquanto `.env` dizia 0.80, e `max_tokens` como **32000** enquanto
  `N_PREDICT` dizia 65536 → esses dois são **do client** e sobrescrevem o servidor.

Uma nota anterior aqui afirmava que o OpenCode também enviava `temperature=0.6` e
`presence_penalty=1.0`. Isso estava errado: na época o próprio `.env` tinha 0.6 e 1.0,
então esses valores casavam por coincidência, não por override. Apenas `top_p` e `max_tokens`
foram fornecidos pelo client. Consequência: ajustar sampling no `.env` *chega* ao tráfego real
de agente — exceto `top_p`, que deve ser alterado no client para ter qualquer efeito.
Corrigir os próprios overrides de um client é uma mudança naquele client, fora do escopo aqui.
(Para referência, se isso um dia surgir: o OpenCode mantém sampling **por agente** —
`agent.<name>.{temperature,top_p}` mais um objeto `options` livre — não por modelo; sua chave
`temperature` no nível de *modelo* é uma flag booleana de capability, então colocar um número ali
não faz nada.)

**Depurando o que um client efetivamente enviou:** com `CAPTURE_LOG=true`, prompts renderizados
caem em `data/logs/capture/prompts/<date>/` (é assim que o client OpenCode Windows/PowerShell
foi identificado, e como você pode confirmar que o template renderizou "Reasoning effort is set to X").
O sampling efetivo por requisição aparece no `server.log` nas linhas `launching slot`.

**Camada de integração downstream** (`infra/`): config do gateway LiteLLM (`infra/litellm/config.yaml`)
e config do OpenCode (`infra/opencode/config.json`) ambos referenciam `qwen3.8-27b` na porta 8080 e
devem permanecer em sync com `.env`. Também aqui: unidades systemd + watchdog
(`infra/llama-server/`), config logrotate, e arquivos do workspace OpenClaw.

**Hardware:** 2x RTX 3090 (48 GB). GPU 0: ~21.4GB, GPU 1: ~22.7GB com Q8_0 + KV q8_0 + ctx 262k —
pouca folga restante.

## Config atual de produção

Modelo: **Qwen3.8-27B Q8_0** (29.0 GB em disco / como reportado pelo servidor)
- Porta: 8080, Contexto: 262k, Saída: 65k, KV cache: q8_0
- MTP: draft-mtp, n=3
- Visão: nativa (mmproj-F16.gguf)
- Sampling — perfil oficial **thinking-mode** do model card HF (verificado 2026-08-17):
  temp=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, repeat_penalty=1.0.
  O card dá apenas dois perfis (thinking / non-thinking) e **nenhum específico para coding**; a
  receita anterior `temp=0.6 + presence_penalty=1.0` neste repositório era uma recipe herdada
  do Qwen3.6 mal rotulada como oficial. Eleve presence_penalty rumo a 2.0 apenas se repetição
  interminável aparecer (o card avisa que pode causar mistura de idiomas).
- Raciocínio: REASONING_MODE=on, REASONING_FORMAT=deepseek, REASONING_EFFORT=low,
  REASONING_BUDGET=8192 (apenas rede de segurança), REASONING_PRESERVE=false
- Decode medido: **24-26 tok/s no regime real de agente** (contexto longo, gerações ~4k tokens
  levando 140-175s por passo); 36-40 tok/s apenas em contexto curto. Processamento de prompt 355-715 tok/s.
