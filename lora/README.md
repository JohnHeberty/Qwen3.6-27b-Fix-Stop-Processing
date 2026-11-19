# Kit de teste do LoRA `harness-hub/Qwen3.8-27B-opencode-adapted`

Tudo o que é preciso para testar o adaptador LoRA no servidor local **numa janela curta**,
sem tocar na produção fora dela. **Nada aqui foi executado na GPU.** O kit foi preparado
e verificado estaticamente em 2026-11-18/19, com o resultado registrado abaixo.

```bash
bash lora/window.sh --plan     # mostra o que vai acontecer (não executa nada)
bash lora/window.sh            # janela padrão: para produção -> testa -> religa (pede "STOP")
```

## 1. O que é o adaptador

| | |
|---|---|
| Repo / commit | `harness-hub/Qwen3.8-27B-opencode-adapted` @ `b4171c0069685320026d76eac96ccf716ca7e476` |
| Tipo | LoRA PEFT 0.21.2, **r=32, alpha=64** (scaling 2,0), sem DoRA/rsLoRA/bias/modules_to_save |
| Alvos | `mlp.{gate,up,down}_proj` nas 64 camadas + `self_attn.{q,k,v,o}_proj` só nas 16 de atenção plena (3, 7, …, 63). Não toca DeltaNet, lm_head nem embeddings |
| Pesos | 512 tensores **fp32**, 637.610.624 bytes (sha256 `668b9d7d…f4582`, conferido contra o LFS do HF) |
| Base do treino | `Qwen/Qwen3.8-27B` **BF16** (não o W4A16 que servimos) |
| Treino | AsyncGRPO (TRL), 150 passos (de 1000 planejados), lr 2e-5, rollouts no **OpenCode 2.x (`@opencode/cli` 2.2.7)**, **thinking OFF**, temperatura 0.8 / top_p 1.0, até 50 passos / 1800 s / 65.536 tokens por rollout, recompensa = corretude + 0,1 de bônus de eficiência em ferramentas |
| Card: como servir | `vllm serve Qwen/Qwen3.8-27B --enable-lora --max-lora-rank 32 --lora-modules qwen3.8-opencode=… --language-model-only --enable-prefix-caching --mamba-cache-mode align --enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking": false}' --max-model-len 131072` |
| Card: amostragem | temperature 0.8, top_p 1.0 (não cita top_k nem presence_penalty; num `vllm serve` sem override valem top_k=20 do `generation_config.json` e presence 0) |
| Card: OpenCode | config mínima (`provider.local` com `@ai-sdk/openai-compatible`, `models: {"qwen3.8-opencode": {}}`); `opencode run --standalone`; sem system prompt próprio (o do OpenCode 2); web search desligado; só texto |

**O que o card afirma** (OpenCode 2, 1 tentativa por tarefa, thinking off): SWE-bench Pro hard-51
35,3% → 51,0%; Terminal-Bench 2.1 46,4% → 52,4%; ~1/4 dos turnos do base no SWE-bench Pro
(13 vs 48) e 3,5x menos tokens gerados; empata com o base em thinking `xhigh` gastando 6–8x
menos tokens.

**Ressalvas:**
- **Estatística fraca.** Os p-valores do próprio card: SWE-bench Pro p=0,057 (11 ganhos / 3
  perdas em 51), Terminal-Bench 2.1 inteiro p=0,38; só o subconjunto de 66 tarefas "não usadas
  para escolher o checkpoint" dá p=0,035. O checkpoint foi escolhido olhando esses benchmarks.
- **Treinado sobre BF16**, e aqui roda sobre W4A16 (ver §2.3: o erro de quantização por peso é
  ~100x maior que o próprio delta do LoRA).
- **Treinado no OpenCode 2.x.** O cliente do usuário é o OpenCode **1.18.34**, que tem outro
  system prompt e outros schemas de ferramenta (ex.: 1.x `read(filePath)` contra 2.x
  `read(path, offset, limit)`). O ganho pode não se transferir para o 1.x; por isso o kit
  testa com os schemas reais do 2.2.7.
- Rollouts de até 65k tokens e 50 passos: o comportamento em sessões de 100k+ não foi treinado.
- `chat_template.jinja` do adaptador = o local + só as marcas `{% generation %}` (máscara de
  treino; o texto renderizado é idêntico). `tokenizer.json`: mesmo vocabulário; muda só o
  regex do pré-tokenizador (`\p{M}`, marcas combinantes, que pt-BR em NFC quase nunca usa).
  O kit **não** troca o tokenizer nem o template da produção.

## 2. Compatibilidade com o nosso stack (vLLM 0.33.0 + W4A16 INT8-head + DFlash2 + TP=2)

Base do teste: **a mesma da produção desde 2026-11-19**, `models/Qwen3.8-27B-W4A16-AutoRound`
(corpo W4A16 g128 compressed-tensors, **lm_head INT8**, embed INT8, MTP INT8), fixada por
`MODEL=` no `lora.env`. A `-fast` (lm_head INT4) tem exatamente o mesmo conjunto de chaves e os
mesmos módulos lineares do corpo, então a análise vale para as duas.

### 2.1 Comprovado (verificação estática, CPU)

| Item | Resultado | Evidência |
|---|---|---|
| Modelo suporta LoRA | sim: `Qwen3_5ForConditionalGeneration` herda `SupportsLoRA` do Qwen3-VL | `model_executor/models/qwen3_vl.py` (classe), `qwen3_5.py:508` |
| Nomes das chaves | **não precisa converter.** As 512 chaves `base_model.model.model.language_model.layers.N.*` viram `language_model.model.layers.N.*` pelo `hf_to_vllm_mapper` do próprio vLLM; os 256 módulos existem no checkpoint W4A16 (`weight_packed/scale/shape`) | `qwen3_vl.py:1990`, `lora/utils.py:180-223`; reproduzido por `lora/check_adapter.py` (rc=0) |
| q/k/v e gate/up | empacotados (`qkv_proj`, `gate_up_proj`) via `packed_modules_mapping`; o `q_proj` B [12288, 32] inclui o gate de saída da atenção, igual ao `QKVParallelLinear(… num_heads*(1+gate))` | `qwen3_5.py:342`, `qwen3_next.py:317` |
| Rank / alpha | r=32 aceito (`--max-lora-rank` ∈ {…,32,…}); `PEFTHelper.validate_legal` OK | `config/lora.py:27`; `check_adapter.py` |
| LoRA sobre W4A16 compressed-tensors | **suportado.** O wrapper chama o método de quantização da camada base e soma o LoRA em bf16 por cima; reconhece `weight_packed` do compressed-tensors | `lora/layers/base_linear.py:211` (`_get_quant_method().apply(...)`), `lora/layers/utils.py:55` |
| Flags | todas existem no `vllm serve --help` do venv; o argv final do `start_lora.sh` passa no parser do próprio vLLM (`make_arg_parser`) | dry-run abaixo |
| Argv | `DRY_RUN=1 bash lora/start_lora.sh` gera o argv da produção **idêntico**, exceto host 127.0.0.1, porta 18021, `GPU_UTIL` 0.65 e as 14 palavras de LoRA | diff conferido em 2026-11-19 |
| Patches HyperQwen | nenhum contorna o wrapper nos módulos-alvo: atenção e MLP chamam `self.qkv_proj(...)`, `self.o_proj(...)`, `self.gate_up_proj(...)`, `self.down_proj(...)`. O único caminho "cru" (`gdn-ba-pad-small-m`, `in_proj_ba` do DeltaNet) **se desliga sozinho com LoRA** | `qwen3_next.py:463,468`, `qwen2_moe.py:116,118`; `mamba/gdn/qwen_gdn_linear_attn.py:747`; `bench/test_gdn_ba_lora.py` rodado em CPU: 3/3 OK |
| DFlash2 / spec decode | o drafter **não** roda LoRA (documentado); o verify roda no alvo com LoRA, e o mapeamento token→LoRA usa `num_scheduled_tokens` (inclui os 7+1 do verify) | `config/lora.py:148`, `v1/worker/gpu/lora_utils.py:94-102`, `model_runner.py:1904-1911` |
| Prefix caching | o hash de bloco inclui nome+caminho do LoRA: base e adaptador **não** compartilham cache (correto) | `v1/core/kv_cache_utils.py:590` |
| CUDA graphs | `cudagraph_specialize_lora=True` (default): grafos separados com/sem LoRA, então requests no nome base não pagam o custo do LoRA | `config/compilation.py:663` |
| OpenCode 2.2.7 | instalado em `lora/opencode2` (versão exata do treino). A config foi validada contra um servidor OpenAI **falso** (CPU, porta 18099): `temperature`, `top_p`, `presence_penalty` e `chat_template_kwargs` chegam no corpo; websearch/webfetch saem da lista de ferramentas | `tests/fake_openai_server.py`, `tests/opencode2_capture.json` |

### 2.2 Decisões que o kit toma por causa disso

- **`--lora-target-modules qkv_proj o_proj gate_up_proj down_proj`.** Sem essa flag, o vLLM
  embrulha *toda* camada linear suportada (`lora/model_manager.py:492`): projeções do DeltaNet,
  o **lm_head INT8** (vira `LogitsProcessorWithLoRA`, e é esse lm_head que o DFlash2 compartilha
  com o alvo, `spec_decode/dflash/utils.py:62-73`) e o embed INT8. O adaptador não usa nada
  disso. Restringir economiza VRAM e mantém lm_head e embed no caminho que a produção já usa.
- **`DFLASH_TOKENS=7` obrigatório.** Acima de 7 o DFlash2 do HyperQwen usa bloco de verify de
  tamanho **adaptativo**. O vLLM recusa "adaptive verification" com LoRA porque o mapeamento
  token→LoRA é montado na CPU antes do corte (`config/vllm.py:3158-3163`). O caminho do
  HyperQwen não passa por essa checagem, então o `start_lora.sh` recusa `DFLASH_TOKENS>7`.
- **`--max-loras 1 --max-cpu-loras 1`**: um adaptador. Requests no nome base e no do
  adaptador podem dividir o mesmo batch (o limite conta adaptadores distintos, não requests).
- **Instância só em 127.0.0.1:18021**, sem API key: os clientes da LAN não acham o teste por engano.

### 2.3 Riscos (não dá para verificar sem GPU)

1. **Base quantizada ≠ base do treino.** Medido por `lora/delta_vs_quant.py` em 8 módulos
   (CPU): o delta do adaptador, |ΔW| = |2·B·A|, tem mediana de **0,2–0,45% do passo INT4** do
   nosso checkpoint (p99 ≈ 1–2%), e nenhum peso chega a meio passo. O erro de quantização do
   W4A16 (até ±½ passo por peso) é ~100x maior que a atualização. O LoRA em runtime soma o delta
   **exato** em bf16, mas sobre uma base que já difere da BF16 do treino. O efeito é coerente
   (posto 32) e o ruído da quantização é difuso, então pode funcionar, mas é empírico. Para isso
   existe o teste 3 do `smoke.py` ("o adaptador altera a saída?").
2. **VRAM.** Buffers do LoRA calculados: **0,188 GiB/GPU** (100,7 M elementos bf16; TP=2 e 1 slot).
   Somando o segundo conjunto de CUDA graphs e o scratch do punica, dá ~0,35 GiB/GPU. O pool de KV
   da produção (base INT8, `GPU_UTIL=0.62`) é de **5,22 GiB = 152.271 tokens, só 1,07x** o
   contexto de 142.080. Sem ajuste, o pool cairia para ~142k, no limite, e o vLLM recusa o boot
   se não couber uma sequência inteira. Por isso `GPU_UTIL=0.65` no `lora.env` (+0,72 GiB/GPU,
   pool estimado em ~5,6 GiB ≈ 160k tokens). Fallback: `GPU_UTIL=0.67 bash lora/window.sh`.
   RAM do host: cada worker TP carrega o adaptador fp32 (637 MB) e converte para bf16, com pico
   transitório de ~1–1,5 GB no total. Com a produção parada, sobra RAM.
3. **Velocidade.** Kernels punica (Triton) a mais nas 64 MLPs e nas 16 atenções a cada passo de
   decode/verify. Estimativa: **−5 a −15%** de tok/s nos requests do adaptador e ~0% no nome base
   (grafos sem LoRA). Boot: mais compilação Triton + captura dupla de grafos, então espere
   **~2,5–4 min** em vez de ~90 s. `speed.py` mede os dois casos.
4. **Aceitação do DFlash2.** O drafter foi treinado nas saídas do base. Se o adaptador muda o
   estilo (menos texto, mais tool calls), a aceitação pode cair. Lembre o gotcha 49: aceitação
   ALTA pode significar texto colapsado. `agent_ab.py` reporta a aceitação só nos episódios
   "limpos", e `spec_log.py` marca intervalos acima de 0,75.
5. Combinações com LoRA que **nunca foram testadas no upstream**: FA2 bf16 + split-KV verify
   (`spec-decode-attn.patch`) + LoRA + `--async-scheduling` + TP=2 custom all-reduce.
   Nada no código as proíbe, mas também não há receita. Se o boot falhar, o log
   (`lora/logs/lora-<ts>.log`) e `results/window-*/boot-highlights.log` mostram onde.
   Alavancas para isolar: `ASYNC_SCHED=0`, `SPEC_ATTN=0`, `EXTRA_ARGS` com `--enforce-eager`
   (lento, só diagnóstico).
6. `thinking_token_budget` padrão (patch local, 8192) também vale nos requests com thinking off.
   Deve ser inócuo (o template já fecha o `<think>`), mas confira no smoke se aparece truncamento.

## 3. Arquivos

| Arquivo | Para quê |
|---|---|
| `lora.env` | overrides da instância de teste sobre o `/root/qwen3/.env` (que só é **lido**): `MODEL` base INT8, porta 18021, host 127.0.0.1, `GPU_UTIL=0.65`, `EXTRA_ARGS` da produção + LoRA (aspas simples no valor inteiro, armadilha do CLAUDE.md), sha256/tamanho do adaptador |
| `start_lora.sh` | sobe a instância (foreground) via `single-user/start_qwen.sh` do upstream. **Recusa** se `systemctl is-active qwen38-27b` ou se alguma GPU tiver > 1 GB, confere o sha256 e acrescenta `--lora-modules`. `DRY_RUN=1` só imprime o argv (sem GPU) |
| `window.sh` | a janela completa com `trap` que **sempre** religa a produção. `--plan`, `--yes`, `--phases` |
| `check_adapter.py` | inspeção em CPU: config, header, mapeamento de chaves pelo código do vLLM, validação PEFT, VRAM dos buffers |
| `delta_vs_quant.py` | |ΔW| contra o passo INT4 (embasa os §2.3 e §7) |
| `tests/smoke.py` | /v1/models com os 2 nomes; chat; o adaptador muda a saída (texto/logprobs greedy); tool call; thinking do base |
| `tests/agent_ab.py` | mini-harness multi-turno com o **system prompt e os schemas reais do OpenCode 2.2.7** (read/write/edit/glob/grep/shell), 5 mini-tarefas de código com testes `unittest`, nota final restaurando os testes (como o SWE-bench Pro). `--selftest` roda sem servidor |
| `tests/tasks.py` | as 5 tarefas (verificadas: todas falham no estado inicial e todas têm solução) |
| `tests/speed.py` | tok/s de decode (streaming) base x LoRA + aceitação por /metrics |
| `tests/spec_log.py` | resume as linhas "SpecDecoding metrics" do log numa janela de tempo e marca as suspeitas |
| `tests/common.py` | HTTP, braços do A/B, amostragem do card, detectores de loop/colapso |
| `tests/fake_openai_server.py` | servidor OpenAI falso (CPU) para validar configs de cliente sem GPU |
| `tests/opencode2_capture.json` | system prompt + 10 schemas de ferramenta capturados do OpenCode 2.2.7 (HOME isolado, sem dados pessoais) |
| `opencode2/` | OpenCode **2.2.7** local (`node_modules/`, ~1 GB, fora do git), `opencode.json` e `run_task.sh` (headless numa tarefa, nota pelos testes) |
| `adapters/opencode-adapted/` | o download (fora do git): `adapter_config.json`, `adapter_model.safetensors`, `README.md` (card), `chat_template.jinja`, `tokenizer*.json` |
| `results/`, `logs/` | saídas (`results/` fora do git) |

O teste de loop **não** é cópia local. É o versionado `scripts/loop_stress.py` (o do A/B INT4
x INT8), estendido de forma retrocompatível: sem variáveis novas, o request é idêntico
byte a byte (conferido). Novas variáveis: `LS_MODEL`, `LS_THINKING=off`, `LS_SAMPLING=card` e `LS_PARALLEL`; a
porta continua sendo o 4º argumento.

## 4. Download (já feito; para refazer)

```bash
hf download harness-hub/Qwen3.8-27B-opencode-adapted --revision b4171c0069685320026d76eac96ccf716ca7e476 \
  --local-dir lora/adapters/opencode-adapted \
  README.md adapter_config.json adapter_model.safetensors chat_template.jinja tokenizer.json tokenizer_config.json
sha256sum lora/adapters/opencode-adapted/adapter_model.safetensors   # 668b9d7d4283d3d3...4f4582
CUDA_VISIBLE_DEVICES= qwen38-27b-rtx3090/venv/bin/python -I lora/check_adapter.py
```
Arquivos baixados são dados: o kit só lê o header JSON do safetensors e os JSONs, e nunca executa
nada que veio do repo do HF.

## 5. A janela de teste, passo a passo

**Antes:** avise os usuários dos clientes (OpenCode/OpenClaw/LiteLLM ficam sem servidor durante a
janela). Garanta que nada mais ocupa a GPU (`ollama ps`, `make playground-down`). O `window.sh`
recusa se encontrar processo estranho na GPU.

```bash
cd /root/qwen3
bash lora/window.sh --plan                         # revisão (não faz nada)
bash lora/window.sh                                # smoke,regress,speed,ab  (pede "STOP")
# variações:
bash lora/window.sh --yes --phases smoke           # só "carrega e funciona?" (~10 min com os 2 boots)
AB_REPS=3 bash lora/window.sh --yes --phases smoke,speed,ab,loop,opencode2
```

O que acontece:
1. preflight sem GPU: dry-run do `start_lora.sh`, sha256, `agent_ab.py --selftest`, GPU sem processo estranho;
2. `systemctl stop qwen38-27b` e espera as GPUs < 1 GB;
3. `setsid bash lora/start_lora.sh >> lora/logs/lora-<ts>.log` e espera `/health` (até 900 s;
   aborta se o processo morrer);
4. fases (resultados em `lora/results/window-<ts>/`):

| Fase | O que roda | Tempo estimado |
|---|---|---|
| `smoke` | `tests/smoke.py`. **Se falhar, aborta** (e religa a produção) | 2–4 min |
| `regress` | upstream `bench/api_smoke.py` nos 2 nomes (`PORT=18021`, `VLLM_MODEL`) + `verify.sh` (checks ao vivo em `PORT=18021`) | 5–10 min |
| `speed` | `tests/speed.py`: 2 nomes x 2 casos x 3 reps, 600 tokens, greedy, thinking off | ~3 min |
| `ab` | `tests/agent_ab.py`: 3 braços x 5 tarefas x `AB_REPS`=2 = 30 episódios, sequencial | 1–2 h |
| `loop` | `scripts/loop_stress.py` 3 x `LOOP_N`=4: LoRA off/card, base off/card, base low/prod (controle do A/B de 19/11) | 30–80 min |
| `opencode2` | OpenCode 2.2.7 real (`opencode2/run_task.sh`) em 2 tarefas x 2 nomes | 15–40 min |

5. `trap EXIT`: derruba o grupo de processos da instância, espera a GPU liberar,
   `systemctl start qwen38-27b` (se ela estava ativa) e espera `/health` da 18020 (até 600 s).
   Isso acontece em sucesso, erro, smoke falho ou Ctrl+C.

Padrão (`smoke,regress,speed,ab`): **~1,5–2,5 h** de produção parada. Para uma primeira olhada
barata, rode só `--phases smoke,speed` (~20 min com os boots).

**Braços do A/B** (`tests/common.py`):
- `lora-nothink`: adaptador como no card (thinking off, temp 0.8, top_p 1.0, presence 0);
- `base-nothink`: base nas mesmas condições (isola o efeito do adaptador);
- `base-think-prod`: base como a produção serve hoje (thinking medium, presence 1.0, temp 1.0,
  teto de thinking 8192 e alarme de repetição do patch local). Nenhum campo é enviado; valem os
  defaults do servidor;
- opcional `lora-nothink-prod`: adaptador com os defaults de amostragem da produção (o que um
  cliente que só desliga o thinking receberia).

**Métricas:** sucesso (suíte `unittest` com os testes originais restaurados); turnos; tool
calls; maior sequência de tool calls **idênticas** (o "repete o mesmo comando" do card); turnos
degenerados (linhas repetidas no fim, ou razão de palavras distintas < 0,2, gotcha 49);
`ended_by` (`done`/`max_turns`/`length`/`repetition`/`error`); tokens gerados e de raciocínio;
tok/s ponta a ponta; aceitação e comprimento médio aceito do DFlash2 via `/metrics` (por
episódio, válido com `--concurrency 1`, que é o default), em todos os episódios e só nos limpos.

**Segurança do mini-harness:** o `shell` executa comandos escritos pelo modelo como `nobody`
(`setpriv`), num diretório próprio em `/tmp`, com PATH mínimo e timeout. É isolamento leve, não
sandbox. `opencode2/run_task.sh` usa `--auto` e roda como o usuário atual (o kit não rebaixa
privilégio do OpenCode). Rode-o num diretório descartável, como o script já faz.

### Rodando o OpenCode 2 à mão (headless)

```bash
OC=lora/opencode2/node_modules/.bin/opencode
H=$(mktemp -d); mkdir -p $H/work; cd $H/work
env -i PATH=/usr/bin:/bin HOME=$H TERM=dumb OPENCODE_CONFIG=/root/qwen3/lora/opencode2/opencode.json \
  OPENCODE_DISABLE_AUTOUPDATE=1 OPENCODE_DISABLE_MODELS_FETCH=1 OPENCODE_DISABLE_PROJECT_CONFIG=1 \
  OPENCODE_DISABLE_CLAUDE_CODE=1 \
  $OC run --standalone --auto --model lora/opencode-adapted "Find out why the tests fail and fix the bug."
```
- formato da config do 2.x: igual ao do 1.x no essencial (`provider.<p>.npm/options/models.<m>.options`).
  Os campos de `options` vão para o corpo do request (conferido);
- `--standalone`: servidor privado, sem deixar o serviço de fundo do 2.x rodando;
- `OPENCODE_DISABLE_CLAUDE_CODE=1` + HOME isolado: sem isso, o 2.x injeta as skills de
  `~/.claude` no system prompt (visto na primeira captura). Fica longe do prompt do treino e vaza
  dados pessoais para o log;
- o `opencode.json` manda `presence_penalty: 0` de propósito: a instância herda o
  `--override-generation-config {"presence_penalty":1.0}` da produção, e o card avaliou com 0.

## 6. Critérios de decisão

**Bloqueadores (qualquer um = não adotar o LoRA em runtime):**
- instância não sobe com `GPU_UTIL` ≤ 0.67, ou smoke falha. Em especial o teste 3: se base e
  adaptador dão saída idêntica, o LoRA não está sendo aplicado;
- `verify.sh` com falhas, ou `api_smoke.py` < 12/12 em qualquer um dos dois nomes;
- erro/Traceback no log durante as fases (`results/window-*/log-errors.txt`).

**Adotar se, no A/B (`summary.json`), `lora-nothink` contra `base-think-prod` (a produção de hoje):**
- sucesso **≥** (ou no máximo 1 episódio a menos em 10);
- `loop_rate` **menor** e `max_identical_streak` < 3;
- mediana de turnos **≤ 0,75x** e de tokens gerados **≤ 0,5x** (o card promete 1/4 e 1/6–1/8;
  aqui o teste é muito menor, então exigimos bem menos);
- tok/s de decode dos requests do adaptador (`speed.py`) ≥ **85%** do nome base na mesma instância;
  nome base na instância LoRA ≥ **97%** do base sem LoRA (comparar com 133,1/66,9 tok/s da
  produção, mesmo método `speed`/`bench_tps`);
- aceitação do DFlash2 nos episódios limpos ≥ **80%** da do base (abaixo disso o ganho de turnos
  é comido pela velocidade).

**Inconclusivo:** 30 episódios dão só **direção**, não significância (o próprio card, com 51–84
tarefas, chega a p≈0,04–0,4). Se der direção positiva, repita com `AB_REPS=4` e confirme com
`opencode2` (o harness real) antes de mudar a produção. `lora-nothink` > `base-nothink` sem bater
`base-think-prod` quer dizer que o adaptador ajuda, mas não substitui o thinking.

**Se adotar:** o passo seguinte (fora deste kit) é portar as flags de LoRA do `lora.env` para o
`EXTRA_ARGS` do `.env` (mantendo `GPU_UTIL` ≥ 0.65) e configurar os clientes: modelo
`opencode-adapted`, thinking off, temp 0.8 / top_p 1.0 / presence 0, de preferência no **OpenCode 2.x**.

## 7. Rollback

- A janela não muda nada da produção: `.env`, venv, modelos e unit ficam intactos. O `trap`
  religa o serviço. Se algo der muito errado (ex.: `kill -9` no próprio `window.sh`):
  `pkill -f 'vllm serve .* --port 18021'; sleep 20; systemctl start qwen38-27b; make status`.
- O `ExecStartPre` do unit espera a GPU 0 < 1 GB por 2 min. Se a instância LoRA ficou presa,
  o start da produção dá timeout: mate-a e `systemctl start qwen38-27b` de novo.
- Remover o kit: `rm -rf lora/adapters lora/opencode2/node_modules lora/results lora/logs`
  (~1,6 GB). A única mudança fora de `lora/` é a extensão retrocompatível de
  `scripts/loop_stress.py` (variáveis `LS_*`); o `.gitignore` foi ajustado pelo coordenador.

## 8. Rota B: fundir o adaptador e requantizar (se o LoRA em runtime for inviável)

Use só se o runtime falhar por boot, VRAM ou velocidade. **Não executada.** Pontos centrais:

1. **Não dá para fundir no W4A16 que temos.** `delta_vs_quant.py` mostra |ΔW| ≈ 0,2–0,45% do
   passo INT4 (p99 ≈ 1–2%, nenhum peso acima de ½ passo). Desquantizar → somar ΔW → requantizar
   na mesma grade (RTN) arredonda **100%** da atualização de volta. A fusão tem de partir da
   base **BF16**, e a quantização tem de ser refeita do zero.
2. **Mesmo assim é perda.** Com Q(W+ΔW) − Q(W), só uma fração ~|ΔW|/passo dos pesos muda de
   nível, e cada um muda um passo inteiro. O delta só sobrevive "em média", com ruído grande.
   O AutoRound/GPTQ calibrado ajuda, porque otimiza a saída da camada e não o peso. O runtime
   (§5) aplica o delta exato e é numericamente superior. Esta rota troca qualidade do
   adaptador por velocidade e simplicidade.
3. **Recursos.** BF16 do `Qwen/Qwen3.8-27B` ≈ 54 GB. O `/` tem ~38 GB livres. Apagar o
   `venv.failed-031` (15 GB, rollback do 0.31) dá ~53 GB, ainda apertado para BF16 + saída W4A16
   (~22 GB). A RAM (20 GB) não comporta o `PeftModel.merge_and_unload()` do card (carrega 54 GB).
   Caminhos:
   - **merge por shard, em streaming** (o que cabe aqui): para cada shard BF16 do HF (≈4–5 GB),
     ler cada `*_proj.weight` alvo, somar `2.0 · B @ A` (fp32 → bf16), gravar o shard fundido e
     apagar o original. RAM de pico ≈ 1 shard + 1 módulo fp32 (~0,4 GB). Mapear
     `base_model.model.model.language_model.layers.N.<mod>` → `model.language_model.layers.N.<mod>.weight`;
     não tocar `linear_attn`, `lm_head`, `embed_tokens`, `mtp.*`, `visual.*`;
   - **quantização**: AutoRound W4A16 g128 simétrico, reproduzindo a receita do upstream
     (`docs/third-party-checkpoints.md`: `in_proj_a/in_proj_b`, a torre de visão e o MTP em BF16,
     o resto W4A16; foi o que se fez com o "Swift adapter merged"). Exportar em
     **compressed-tensors `pack-quantized`** (o `prepare/` não aceita export AutoRound nativo,
     ver `prepare/README.md`). AutoRound de 27B precisa de GPU por horas. Numa 3090, só com a
     produção parada e camada a camada; o mais prático é **alugar uma GPU de 48–80 GB** por
     algumas horas;
   - **`prepare/`** sobre o resultado, nesta ordem: `quant_lm_head.py` (INT8, como a base em
     produção), `quant_embed.py`, `quant_mtp.py`, `build_draft_vocab.py`, este de preferência com
     `--corpus` sobre **saídas do próprio modelo fundido**, já que o adaptador muda a distribuição
     de tokens (o caso Swift do upstream: o draft vocab recontado eliminou o déficit de aceitação);
   - o drafter **DFlash2** continua o mesmo (foi treinado no base). Meça a aceitação; se cair
     muito, a Rota B herda a mesma perda que o runtime.
4. Servir com `MODEL=<dir fundido>` no `.env`, sem flags de LoRA, e repetir `verify.sh`,
   `api_smoke`, `scripts/loop_stress.py` e o A/B deste kit apontando para ele.
