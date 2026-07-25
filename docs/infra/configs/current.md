# Current Production Configuration

**Status:** Active — Qwen3.6-35B-A3B MoE promoted to default (~2.5x faster than the 27B dense model at equal settings) + q4_0 KV cache (fastest and highest context ceiling of the 3 caches tested for this model), see [reports/35b-a3b/q4_0/README-a3b.md](../reports/35b-a3b/q4_0/README-a3b.md)

## Model

| Parameter | Value |
|---|---|
| `MODEL_FILE` | `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` |
| Quantization | Q4_K_M, Unsloth Dynamic (~22.6 GB on disk, ~21.5 GB VRAM for weights) |
| Architecture | MoE (`qwen35moe`): 41 layers, 256 experts, 8 routed/token (~3B active params/token) |
| Source | [unsloth/Qwen3.6-35B-A3B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF) |
| MTP heads (embedded) | 1 (`qwen35moe.nextn_predict_layers = 1`) — llama.cpp drafts recursively above n=1 |
| Legacy alternative | `Qwen3.6-27B-Q5_K_M.gguf` (dense, 27B active/token) — see [reports/27b-dense/](../reports/27b-dense/) |

## Server

| Parameter | Value |
|---|---|
| Engine | `llama-server` (`e8f19cc` + grammar patches) |
| GPU | RTX 3090 (24,576 MiB) |
| `N_CTX` | 106,496 (104k — performance collapses to 11-13 tok/s above this, see benchmark report) |
| `N_BATCH` | 4096 |
| `N_UBATCH` | 512 |
| `CACHE_TYPE_K` | `q4_0` |
| `CACHE_TYPE_V` | `q4_0` |
| `ENABLE_MTP` | `true` |
| `MTP_TOKENS` | 2 (142.7 tok/s @ 8k, 71.6% acceptance) |
| `CTX_CHECKPOINTS` | 8 |
| `CACHE_RAM` | 10240 |
| `BENCHMARK` | `null` (disabled) |
| Threading | `-t 28` (CPU threads for prompt processing) |

## Template

- **File:** `data/templates/custom/chat_template_v21.jinja`
- **Fork:** froggeric v21.3
- **Features:** `<thinking>` reasoning_content, tool_call handling, `requiresStringContent` passthrough

## Request Chain

```
Cliente → LiteLLM (:4000) → llama-server (:8000)
```

Os clientes falam direto com o LiteLLM (ou com o llama-server em `:8000`). O antigo
`force-proxy.py` (bridge Responses↔ChatCompletions na porta 4002) foi **descontinuado**:
reescrevia conversas, sanitizava schemas de ferramentas e perdia campos da Responses API,
degradando o tool-calling. Nenhuma camada intermediária altera mais requisições.

## Draft Model Experiments

Testamos draft externo com 3 modelos como alternativa ao MTP interno (experimentos feitos com o 27B dense; MTP interno também venceu no 35B-A3B, ver [reports/35b-a3b/q4_0/README-mtp-sweep-a3b.md](../reports/35b-a3b/q4_0/README-mtp-sweep-a3b.md)). Nenhum superou o MTP n=2:

| Draft model | tok/s | Veredito |
|---|---|---|
| Qwen3-0.6B-Q4_K_M | 36 | Overhead do draft anula ganho |
| Qwen3.5-0.8B-Q4_K_M | 33-34 | Todos n_max=1..7 dão mesmo resultado |
| Qwen3.5-2B-Q4_K_M | 19 | Muito pesado para RTX 3090 |

MTP interno é superior porque as MTP heads são camadas extras no mesmo forward pass, sem carregar modelo separado.

## `--ubatch-size` (batch físico) — testado, mantido no padrão

Testamos `-ub/--ubatch-size` no contexto de produção fixo (106,496, q4_0, MTP n=2), variando 256/512/1024/2048 (padrão llama.cpp: 512, nunca exposto no `.env`):

| `ubatch-size` | tok/s (decode) | Prefill t/s | TTFT | VRAM free |
|---|---|---|---|---|
| 256 | 111.8 | 1.742,5 | 44.5s | 1.336 MiB |
| **512 (padrão, mantido)** | **107.9** | **2.205,4** | **35.1s** | 1.188 MiB |
| 1024 | 13.4 ⚠️ colapso | 2.185,5 | 35.5s | 1.330 MiB |
| 2048 | 7.5 ⚠️ colapso | 2.495,9 | 31.1s | 1.146 MiB |

**256 ganha ~4% em tok/s de decode mas perde ~27% em TTFT** — não compensa trocar o padrão. **1024+ colapsa o decode** (13.4/7.5 tok/s) mesmo com *mais* VRAM livre que o 512 — sinal de que não é falta de VRAM, é algo na forma como o llama.cpp monta o compute graph por passo de decode quando o batch físico é grande (hipótese: com MTP draftando só 2-3 tokens por passo, um `ubatch` grande pode forçar overhead de graph desproporcional ao trabalho real, já que prefill — que usa lotes grandes de verdade — não sofre, só decode). Diferente do colapso visto no sweep de contexto (onde prefill *e* decode caem juntos) — mecanismos aparentemente distintos. Não investigado a fundo no código do llama.cpp.

## `--n-cpu-moe` (offload de experts pra CPU) — testado, descartado

A ideia original em `docs/DICA` era descarregar alguns experts MoE pra CPU pra liberar VRAM (e talvez destravar mais contexto). Testamos no contexto de produção (106,496, q4_0, MTP n=2):

| `n-cpu-moe` | tok/s (decode) | VRAM used | VRAM free | Δ tok/s |
|---|---|---|---|---|
| **0 (padrão, mantido)** | **108.1** | 22,938 MiB | 1,188 MiB | — |
| 2 | 33.8 | 22,198 MiB | 1,928 MiB | **-69%** |
| 4 (interrompido, dado parcial) | ~20 | — | — | **-81%** |

Só 2 das 41 camadas offloadadas já custam 69% de throughput pra liberar ~740 MiB de VRAM — troca péssima. Cada camada offloadada roda inteira na CPU a cada passo de decode (não só quando um expert específico é ativado), mais o overhead de transferência CPU↔GPU a cada passo. Sweep interrompido em n=4 porque a tendência (queda monotônica e acelerada) já estava clara — não vale a pena continuar testando 8/16. **`--n-cpu-moe` não é recomendado neste hardware para este modelo.**

## `--spec-type ngram-simple` (Prompt Lookup Decoding) — testado, MTP continua vencendo

Testamos `--spec-type ngram-simple` (drafta via n-gramas repetidos no próprio prompt, em vez da MTP head) como alternativa ao MTP, num prompt de edição de código real (arquivo de 203 linhas do próprio repo, tarefa: adicionar docstrings sem alterar o resto — tarefa desenhada pra maximizar repetição literal entre prompt e saída). Contexto 16k, q4_0, 2 execuções por config:

| `spec-type` | tok/s | Aceitação |
|---|---|---|
| `none` (baseline) | 125.9 / 125.8 | — |
| **`draft-mtp` n=2 (padrão, mantido)** | **170.6 / 173.0** | **82.1% / 84.1%** |
| `ngram-simple` (defaults) | 159.3 / **107.6** | 52.3% / **17.7%** |

MTP venceu com boa margem e foi consistente entre execuções. `ngram-simple` variou muito entre as duas rodadas do mesmo prompt (52% → 18% de aceitação) — na segunda execução ficou até pior que não usar especulação. Faz sentido: n-gram lookup só acerta quando o texto *gerado* bate literalmente com trechos já vistos no prompt; como a tarefa pedia texto livre (docstrings), a correspondência variou bastante conforme a formulação exata que o modelo escolheu a cada execução — diferente do MTP, que prevê a partir da própria distribuição do modelo, não depende de match literal. Também notável: mesmo em código (alta repetição estrutural), a aceitação do MTP subiu bastante em relação ao prompt de resumo de texto (82-84% vs 65-71% no benchmark padrão de PDF) — o tipo de tarefa afeta a aceitação mais que qualquer parâmetro de configuração testado até agora.

`ngram-simple` pode se sair melhor em tarefas de cópia mais literal (reformatação pura, sem texto novo) — não testado. **Mantido `draft-mtp` n=2 como padrão.**

## `--cache-reuse N` (KV-shifting para prefixo em multi-turn) — testado, sem efeito no padrão comum

Hipótese: como todos os benchmarks acima são de uma tacada só (single-shot), nenhum deles mede reaproveitamento de cache em conversas multi-turn — que é o padrão real de uso via OpenCode. Testamos simulando o `compaction.prune` do OpenCode: turno 1 (contexto longo de ~5.100 tokens + pergunta) → turno 2 (pergunta de acompanhamento, histórico completo) → turno 3 com o **turno 1 removido do histórico** (contexto longo + turno 2 + pergunta nova), comparando `--cache-reuse 0` vs `256`:

```
cache-reuse=0:   turn3 → prompt_n=537  cache_n=4602/5139 (89.6% reaproveitado)
cache-reuse=256: turn3 → prompt_n=537  cache_n=4602/5139 (89.6% reaproveitado) — idêntico
```

**Zero diferença.** O motivo: o bloco grande (contexto/arquivo) fica sempre na posição 0 do prompt, com ou sem a "poda" do turno 1 — o cache de prefixo *padrão* do llama-server (sem KV-shifting) já reconhece que esse bloco não mudou de posição e reaproveita ele inteiro. `--cache-reuse` só ganharia relevância se o bloco reaproveitável fosse deslocado de posição (algo removido *antes* dele) — não é o padrão típico de poda (que remove turnos antigos, deixando o contexto/system inicial intacto). **Não recomendado ativar** para o padrão de uso atual (system/contexto fixo no início, histórico podado depois).

## Qualidade: q4_0 vs q8_0 (needle-in-haystack) — sem diferença, q4_0 confirmado

Todos os benchmarks anteriores mediram só velocidade. Testamos qualidade de recall em contexto longo: inserimos 3 códigos únicos (`ALPHA-7734-Q`, `BRAVO-2291-X`, `CHARLIE-5568-M`) em ~10%/50%/90% de um contexto de ~45.760 tokens, e pedimos pro modelo listar todos. Contexto/MTP/modelo idênticos, só o cache variando.

Primeira tentativa usou decodificação greedy pura (`temp=0`) pra determinismo — o `q8_0` travou num loop de auto-correção e nunca emitiu resposta final (esgotou 2500 tokens só "pensando"), enquanto `q4_0` concluiu limpo. Repetindo com o sampling real de produção (`temp=0.3, top_k=40, top_p=0.95, min_p=0.05`), **2 execuções por cache**:

| Cache | Run 1 | Run 2 |
|---|---|---|
| q8_0 | ✅ 3/3, concluiu (1.882 tokens) | ✅ 3/3, concluiu (1.484 tokens) |
| q4_0 | ✅ 3/3, concluiu (1.445 tokens) | ✅ 3/3, concluiu (1.809 tokens) |

**4/4 execuções corretas nos dois caches.** O travamento do teste com `temp=0` foi um artefato de decodificação greedy (conhecido por entrar em loop de repetição), não um problema de qualidade do cache — a produção nunca usa `temp=0`. **Confirmado: `q4_0` não perde recall em contexto longo vs `q8_0`.** Sem motivo pra não usar q4_0 como padrão (já era o mais rápido e com maior teto de contexto).

## Cache RAM para 2+ projetos simultâneos — testado, config atual já é suficiente

Objetivo: rodar 2 projetos (sessões OpenCode) ao mesmo tempo sem que trocar de projeto force reprocessar o contexto inteiro do zero (o servidor só tem 1 slot ativo por causa de `N_PARALLEL=1`, mas `--cache-idle-slots` + `--cache-ram` salvam o estado do slot ocioso em RAM quando uma tarefa nova chega).

Testado simulando 2 "projetos" alternando (contextos de ~83k e ~85k tokens, quase o teto de 106.496):

| Chamada | Tempo | Detalhe |
|---|---|---|
| Projeto A (1ª vez) | 38.4s | processa 82.938 tokens do zero |
| Projeto B (1ª vez) | 40.5s | processa 85.444 tokens do zero |
| **Projeto A (2ª vez)** | **1.9s** | restaura 82.934/82.938 tokens do cache RAM (só 4 novos) |
| **Projeto B (2ª vez)** | **2.0s** | restaura 85.440/85.444 tokens do cache RAM |

**RAM consumida pra manter os dois projetos completos em cache simultaneamente: ~1,9 GB** (de 27,8 GB livres para 25,9 GB, numa máquina com 32 GB total). Ou seja, `CACHE_RAM=10240` (10 GB) já comporta uns 5-8 projetos desse tamanho antes de estourar — **não precisa aumentar nada**. `CTX_CHECKPOINTS=8` também já é suficiente (os 2 checkpoints foram criados sem problema). Config atual (`CACHE_RAM=10240`, `CTX_CHECKPOINTS=8`, `CACHE_IDLE_SLOTS=1`) já entrega exatamente o que foi pedido: múltiplos projetos com contexto quase cheio, trocando entre si com restauração quase instantânea (~2s em vez de ~40s).

## Build** `e8f19cc` (llama.cpp)
- **Patches:** `llama-cpp-grammar-patches.patch` (MAX_REPETITION_THRESHOLD=100000, auto-anchor, regex shorthands)
- **CMake flags:** `GGML_CUDA=ON`, `GGML_CUDA_FA=ON`, `GGML_CUDA_FA_ALL_QUANTS=ON`, `GGML_CUDA_GRAPHS=ON`, `CMAKE_CUDA_ARCHITECTURES=86`, `CMAKE_BUILD_TYPE=Release`
- **Note:** Build otimizado para RTX 3090 (sm_86) com FA_ALL_QUANTS para suporte a KV cache q5_1/q4_0.
