# CLAUDE.md

Este arquivo fornece orientações ao Claude Code (claude.ai/code) ao trabalhar com código neste repositório.

## O que este projeto é

Um servidor local de inferência para **Qwen3.8-27B** (denso 27B, híbrido Gated DeltaNet + Atenção),
servido por **vLLM** com quantização **W4A16 (AutoRound)** e decodificação especulativa **DFlash2**,
expondo uma API compatível com OpenAI em `http://localhost:18020/v1`.
Roda em 2x RTX 3090 (48 GB VRAM) com tensor-parallel 2.

Este repositório é um **wrapper de operação** em volta do upstream
[syv-ai/HyperQwen](https://github.com/syv-ai/HyperQwen) (antes `syv-ai/qwen38-27b-rtx3090`),
que é clonado em [qwen38-27b-rtx3090/](qwen38-27b-rtx3090/). O que este repo adiciona:
`.env` único, `Makefile`, unit systemd, configs de consumidores (`infra/`) e benchmarks (`bench/`).
A lógica de servir vive toda no upstream — principalmente
[single-user/start_qwen.sh](qwen38-27b-rtx3090/single-user/start_qwen.sh), que traduz env vars em
flags do vLLM.

O repositório é bilíngue: `Makefile`, `.env`, `README.md` e este arquivo estão em português (pt-BR);
o upstream clonado é em inglês. Mantenha o idioma existente ao editar um dado arquivo.

> **NOTA HISTÓRICA:** até ~agosto/2026 este projeto usava **llama.cpp + GGUF + MTP na porta 8080**.
> Esse setup foi **abandonado** — não há mais nenhum `.gguf` em disco nem clone do llama.cpp.
> Documentação antiga mencionando `make build-llama-server`, `MODEL_FILE`, `CACHE_TYPE_K`,
> `REASONING_BUDGET`, `env-examples/` ou a porta 8080 está obsoleta. Material antigo em [arquived/](arquived/).

## Comandos

Tudo é dirigido pelo `Makefile` (`make help` para a lista completa). Variáveis vêm de [.env](.env),
que é lido tanto pelo Makefile quanto pelo systemd (`EnvironmentFile=`).

**Ciclo de vida** (o serviço roda via systemd como `qwen38-27b`):
```bash
make start / stop / restart / status / logs
make install-service / uninstall-service
```

**Diagnóstico** (read-only, do upstream — config efetiva + GPU + porta + `/health`):
```bash
make doctor
```
O `make doctor` exporta o `.env` da raiz e cria um symlink temporário
`qwen38-27b-rtx3090/.env` (removido no fim), porque o `scripts/hq-doctor.sh` do upstream lê o
`.env` de dentro do repo do vLLM.

**Setup** (idempotente, cada etapa com sentinel):
```bash
make setup   # setup-repo -> setup-venv -> setup-model -> setup-quant -> setup-patches
             # -> setup-fast -> setup-dflash2 -> setup-service -> setup-verify
```
Etapas individuais disponíveis com os mesmos nomes (ex.: `make setup-patches`).

**Testes / benchmarks** (requerem o servidor em :18020):
```bash
make test
./qwen38-27b-rtx3090/verify.sh       # verificação de sanidade do upstream
./qwen38-27b-rtx3090/run-all.sh      # suíte de benchmarks do upstream
```
Scripts de benchmark locais em [bench/](bench/).

**Integrações:**
```bash
make litellm-start / litellm-stop    # proxy LiteLLM (infra/litellm/)
make playground-up / playground-down # vLLM playground em Docker
```

**Rotação de logs:**
```bash
make install-logrotate      # instala /etc/logrotate.d/qwen-logs (inclui o log do vLLM)
make uninstall-logrotate    # remove
```
O unit do vLLM faz *append* em `data/logs/qwen38-27b.log`, que cresce sem limite (151 MB em ~1 dia
de uso). O template versionado em [infra/logrotate/qwen-logs](infra/logrotate/qwen-logs) usa
`copytruncate` (não derruba o serviço), `daily` + `maxsize 200M` e `rotate 7`.

## Arquitetura

**Fluxo de config:** [.env](.env) → `Makefile` + unit systemd ([infra/qwen38-27b.service](infra/qwen38-27b.service))
→ [single-user/start_qwen.sh](qwen38-27b-rtx3090/single-user/start_qwen.sh) (traduz env vars em flags do
vLLM, aplicando seus próprios defaults) → `vllm serve`. Ao alterar um parâmetro de runtime a fonte da
verdade é `.env`; o start script só repassa. **Cuidado:** o start script tem muitos defaults próprios
que o `.env` não define explicitamente — leia-o antes de assumir um valor.

O unit systemd tem um `ExecStartPre` que **espera a GPU 0 ficar abaixo de 1 GB usados** (até 2 min)
antes de subir. Se outro processo (Ollama, um playground) estiver segurando VRAM, o start falha por
timeout em vez de dar OOM.

**Seleção de modelo:** `start_qwen.sh` escolhe automaticamente
`models/Qwen3.8-27B-W4A16-AutoRound-fast` se existir (é o caso), senão cai para
`models/Qwen3.8-27B-W4A16-AutoRound`. A variante `-fast` tem lm_head/MTP requantizados em int4-GPTQ
e um draft vocab construído sobre as saídas do próprio modelo.

**Modos `CTX` e `SPEC`** (o eixo principal do start script):
- `SPEC=mtp` — cabeça MTP nativa do Qwen, drafts encadeados.
- `SPEC=dflash2` — drafter de bloco DFlash2, 7 drafts em **uma** passada não-autoregressiva. **Em uso.**
- `CTX=fast` — bf16 KV + FlashAttention, mais rápido. **Em uso.**
- `CTX=long` — int8/fp8 KV via FlashInfer, mais contexto, mais lento.
- `CTX=huge` — KV cache KVarN 4/2-bit, até ~240k, ~metade da taxa de decode.

**Pegadinha de contexto:** `.env` não define `CTX`, então o default é `fast`, cujo `DFLASH_MAX_LEN`
padrão seria 65536. Mas `.env` define `DFLASH_MAX_LEN=142080` explicitamente, que **sobrescreve** esse
default. Por isso a config efetiva é "modo fast (bf16) com contexto de 142k" — uma combinação que não
é o default de nenhum modo. Confirmado contra o processo vivo: `--kv-cache-dtype bfloat16`
`--max-model-len 142080`.

**Patches do vLLM** ([qwen38-27b-rtx3090/patches/](qwen38-27b-rtx3090/patches/), **61 arquivos**:
57 na série `patches/series` + 4 do KVarN (`kvarn/`). Backport do DFlash2, lookup drafting, atenção
split-KV para o verify, softmax/top-k sem sort, int8/int4 KV, prefill int8, bounds de GDN, correções de
serving (`/health`, 404 com nomes servidos, `/tokenize`). A ordem é obrigatória — alguns carregam como
contexto linhas que um patch anterior insere. Aplique **sempre** via a porta única, que lê
`patches/series` e recusa começar se a série e o diretório discordarem:
```bash
cd qwen38-27b-rtx3090
VLLM_DIR=$(venv/bin/python -c 'import vllm,os;print(os.path.dirname(vllm.__file__))' | tail -n1)
bash patches/apply.sh --list        # confere série vs diretório (rc=2 se divergirem)
bash patches/apply.sh "$VLLM_DIR"   # aplica em ordem; --forward, --fuzz 0
bash kvarn/install.sh               # 4 patches KVarN + módulos do backend KVARN
```
Política `--fuzz 0`: um *offset* é benigno (o contexto casou exato), mas *fuzz* falha pelo nome em vez
de aplicar no chute. **Um upgrade do vLLM sem reaplicá-los dropa todas essas otimizações.**

**Camada downstream** ([infra/](infra/)): LiteLLM (`infra/litellm/`), OpenCode (`infra/opencode/`),
OpenClaw, logrotate. Todos devem referenciar `qwen3.8-27b` na porta **18020**.

**OpenCode (testado headless, v1.18.34):** campos extras em `provider.<p>.models.<m>.options` **chegam** ao
servidor (`temperature`, `top_k`, `thinking_token_budget` conferidos no log); `agent.<nome>.temperature`
**não** chegou (veio 1.0). Por isso a config usa `options.temperature: 0.6` (experimento: o card recomenda
1.0; 0.6 + teto de thinking é o único relato de "resolveu" no HF #178) e `limit.output: 16384` (loop custa
no máximo 16k; gatilho de compactação = `context − output` = ~84k — o `compaction.reserved` só vale com
`limit.input`).

**Limites dos clientes (2026-11-16):** OpenCode e OpenClaude declaram contexto de **100k** (não 140k)
para compactar antes da faixa de 60k–120k onde sessões de agente colapsaram em loop de texto; LiteLLM
usa `max_input_tokens: 100000`; OpenClaw fica em 140k porque o `reserveTokens: 40000` dele já compacta
em ~100k. Effort em `medium` em todos (OpenCode `reasoningEffort`, OpenClaude `effortLevel`, OpenClaw
`thinkingDefault`). **O cliente sobrescreve o effort do servidor** — e as cópias que valem ficam nas
máquinas dos clientes, não neste repo. As camadas anti-loop existentes (`opencode-anti-loop`,
`infra/litellm/loop_guard.py`) só detectam **tool_calls repetidas**, não texto degenerado; para isso
existe só o `presence_penalty` do servidor.

## Config atual de produção

Verificado contra o processo vivo e `GET /v1/models` em 2026-11-12 (vLLM **0.33.0**).

- **Modelo servido:** `qwen3.8-27b` → `models/Qwen3.8-27B-W4A16-AutoRound-fast`
- **Porta:** 18020 · **Contexto:** 142080 (`max_model_len`) · **TP:** 2
- **Spec decoding:** `{"method":"dflash","model":".../Qwen3.8-27B-DFlash2-W4A16","num_speculative_tokens":7,"draft_sample_method":"probabilistic"}`
  - `DFLASH_TOKENS=7` é o default de chat — o drafter foi treinado para 7; posições 8-15 têm
    aceitação quase nula em chat geral. Use 15 apenas para reprodução de documento (custa ~8k de contexto).
- **KV cache:** bfloat16, **5,52 GiB por GPU** (161.063 tokens = 1,13x o contexto de 142k), dimensionado
  por `GPU_UTIL=0.62` com TP=2
- **Atenção:** `FLASH_ATTN` · `--mamba-cache-mode align` (deprecado no 0.33, sem efeito — o prefix
  caching do Mamba segue `--enable-prefix-caching`) · `--enable-prefix-caching`
- **GPU util:** 0.62 · `--max-num-seqs 8` · `--max-num-batched-tokens 2048` · `--async-scheduling`
- **Parsers:** `--reasoning-parser qwen3` · `--tool-call-parser qwen3_coder` (+`--enable-auto-tool-choice`)
  · `--tool-strict-level parameter`
- **Raciocínio:** `reasoning_effort:medium`, `enable_thinking:true`, **`preserve_thinking:false`**,
  todos via `--default-chat-template-kwargs` dentro de `EXTRA_ARGS` no `.env`.
- **Anti-repetição:** `--override-generation-config {"presence_penalty":1.0}` (desde 2026-11-16).
  O vLLM funde com o `generation_config.json` → defaults efetivos `presence_penalty=1.0, temperature=1.0,
  top_k=20, top_p=0.95`; o cliente ainda pode sobrescrever por request. Testado: `api_smoke.py` 12/12 e
  cópia literal de ~3,5k chars de código **idêntica** com penalty 0 / 1.0 / 1.5.
- **Teto de thinking e alarme de loop (desde 2026-11-16):** patch local
  [patches/local/qwen3-server-sampling-defaults.patch](patches/local/qwen3-server-sampling-defaults.patch)
  (`make setup-local-patches`, também na cadeia do `make setup`) faz o servidor preencher dois campos que o
  `--override-generation-config` não aceita, **só quando o request não os manda**, a partir do `.env`:
  `QWEN_DEFAULT_THINKING_BUDGET=8192` (força o `</think>`) e `QWEN_DEFAULT_REPETITION_DETECTION=3,24,12`
  (padrão de 3–24 tokens repetido 12x seguidas → `finish_reason=repetition`; o cliente desliga com
  `repetition_detection:{max_pattern_size:0}`). Vive **fora** do clone do upstream: um upgrade do vLLM
  (venv novo) exige rodar `make setup-local-patches` de novo. Validado: frase repetida para em 108 tokens;
  `api_smoke` 12/12; cópia literal de código idêntica; decode 150,5 tok/s código / 65,5 narrativo.
- **Log de requests (diagnóstico, temporário):** `--enable-log-requests --max-log-len 300` — mostra os
  `SamplingParams` reais de cada cliente (effort, temperatura, penalty) no log. Remover quando o loop de
  repetição estiver resolvido.
- **Cudagraph:** `--max-cudagraph-capture-size 64`, `custom_ops: [+rms_norm, +silu_and_mul]`
- **Boot:** ~90 s até `/health` 200 (torch.compile ~67 s + captura de cudagraph)

**`preserve_thinking:false` é o que impede o contexto de inflar sozinho** (ligado em 2026-10-12).
O template reinjeta o campo `reasoning` de *todos* os turnos anteriores do histórico, então cada
passo do agente re-alimenta todo o raciocínio acumulado. Medido com `/tokenize`, ~800 tokens de
raciocínio por turno:

| turnos | preserve ON | OFF |
|---|---|---|
| 5 | 5.118 | 143 |
| 20 | 20.338 | 438 |
| 40 | **40.638** | **838** |

Numa sessão de 40 turnos, 98% do prompt era raciocínio velho. Desligar **não** afeta o thinking do
turno atual (o modelo continua pensando normalmente) — só para de re-enviar o dos turnos passados.
O campo é `reasoning` (nome do 0.31); o `--no-reasoning-preserve` citado em notas antigas era flag
do llama.cpp e **não existe no vLLM** — aqui se faz pelo chat template kwargs.
- **Prefix caching:** liga `--enable-prefix-caching --mamba-cache-mode align`. Ganho grande de TTFT em
  requests repetidos (2º turno contra doc de 25k: 0.56s vs 22.4s).
- **Binding:** `HOST=0.0.0.0` no `.env` — obrigatório desde o 0.31 (ver Histórico de upgrade).
- **Sem autenticação** — por isso o launcher emite um WARNING a cada boot. É o comportamento
  anterior, mas note que qualquer máquina da LAN alcança a porta.

**`REASONING_EFFORT`** é repassado ao template. O template só aceita `low` | `medium` | `xhigh`;
qualquer outra coisa lança exceção (HTTP 400). **`high` NÃO era alias** — dava 400 até 2026-11-16.
Desde então o `EXTRA_ARGS` tem `--reasoning-effort-map {"high":"xhigh","max":"xhigh","minimal":"low"}`
(flag do vLLM 0.33), e todos os valores da API (`none|minimal|low|medium|high|xhigh|max`) funcionam.
O template local é idêntico ao do HF nesses ramos (ver "Modelo base no HuggingFace").
O que cada valor injeta não é o que o nome sugere:
- `xhigh` (default do template) → "think carefully, validate key assumptions, consider alternatives…"
- `medium` → **nada**. Não existe ramo `medium` no template; é "sem orientação", não "esforço médio".
  **Em uso desde 2026-11-16.**
- `low` → "Keep your thinking brief and focused, moving directly to the conclusion." É o único valor
  que efetivamente pede thinking curto. **Abandonado em 2026-11-16:** em sessões longas de agente
  (~58k–120k tokens) o thinking colapsou em fragmentos ("Let me.", "Let.", "I'll do.") até bater em
  `length` (5 requests). Não há anti-repetição configurado (sem `presence_penalty`; o
  `repetition_detection` do vLLM é só por request). Reapareceu com `medium` no servidor — num cliente
  **OpenCode** (a config do Windows pode ainda mandar `reasoningEffort: low`, que sobrescreve). Resposta em 2026-11-16: `presence_penalty`
  1.0 no servidor, OpenClaude em `medium` e `contextWindow` 100k (compacta mais cedo).

**Performance medida em 2026-11-12** (vLLM 0.33.0, prompt curto, 600 tokens de saída, streaming,
temperatura 0 — [scripts/bench_tps.py](scripts/bench_tps.py)): **133,1 tok/s em código**, 66,9 tok/s
narrativo. Números de batch/prefill do README do upstream (~1094 tok/s a 64 concorrentes, ~1810 tok/s
de prefill) seguem **não remedidos** aqui.

> **Não compare com os números de 2026-10-12** (143,6 / 88,8 tok/s): foram medidos com script,
> prompts e config diferentes (era a config `GPU_UTIL=0.93`). O A/B do mesmo método, 0.31.0 vs 0.33.0
> com argv idêntico, deu **132,9 vs 133,1 tok/s** (código) e **66,9 vs 66,8** (narrativo) — ou seja,
> **paridade**, dentro de 0,3%. Ver "Histórico de upgrade".

**Hardware:** 2x RTX 3090 (48 GB). Medido em 2026-11-12 com o servidor ocioso: **~15,6 GB por GPU
em uso (~63%)**, sobrando ~8,9 GB. Composição (log de boot): pesos 8,13 GiB + pool de KV 5,52 GiB
+ drafter/CUDA graphs/ativações (0,96 GiB pico + 0,10 GiB cudagraph). O pool (161k tokens = 1,13x o
contexto de 142k) é **pré-alocado** a partir de `GPU_UTIL=0.62`, não cresce com o uso.

## Pendências

**Autocomplete (FIM) no VSCode devolve 404.** Erro visto no cliente:
`llama.cpp FIM returned 404 at http://100.102.127.47:18020/completion` (`{"detail":"Not Found"}`).
Diagnóstico (2026-10-21):
- A extensão (estilo llama.vscode) chama os endpoints **do llama.cpp** `/completion` / `/infill`,
  que o vLLM não tem. O vLLM só expõe `/v1/completions`.
- `suffix` no `/v1/completions` também falha (400, "suffix is only supported for models with FIM
  completion rendering"): no 0.31 só o renderer do DeepSeek V4 implementa FIM.
- **Mas o modelo faz FIM.** O tokenizer tem `<|fim_prefix|>` (248060), `<|fim_middle|>` (248061),
  `<|fim_suffix|>` (248062), `<|fim_pad|>` (248063). Testado com prompt cru em `/v1/completions`
  (revalidado no 0.33 em 2026-11-12, mesmo resultado):
  `<|fim_prefix|>def soma(a, b):\n    <|fim_suffix|>\n    return r\n<|fim_middle|>` +
  `stop:["<|endoftext|>","<|fim_pad|>"]` → completou `r = a + b` corretamente e parou em
  `<|endoftext|>`.
- Caminhos possíveis: (a) extensão que fale OpenAI `/v1/completions` com template FIM configurável
  (ex.: Continue com `template` próprio); (b) um shim fino em `infra/` que traduza `/infill` e
  `/completion` do llama.cpp para `/v1/completions` com os tokens acima (mais simples para manter
  a extensão atual).
- **Decisão (2026-10-21): caminho (a), sem shim** — ficar no vLLM/OpenAI-compatible. Config pronta
  em [infra/twinny/README.md](infra/twinny/README.md) (cliente é o **Twinny**; config equivalente para o Continue em [infra/continue/config.yaml](infra/continue/config.yaml); FIM via `/v1/completions` +
  template custom). Nos logs: chat do Twinny OK, FIM batia em `/completion` (provider llamacpp). **Falta validar.**

**Coexistência com Ollama (2026-10-21).** `.env` ganhou `GPU_UTIL=0.62` (antes 0.93 implícito):
pool de KV caiu de 12,77 para **5,52 GiB/GPU** (161k tokens, 1,13x o contexto de 142k), sobrando
~8,9 GB/GPU. O `qwen2.5-coder:7b` foi testado e **removido do Ollama em 2026-10-22** (autocomplete ruim); o FIM fica no próprio 27B via vLLM. Com isso o `GPU_UTIL=0.62` só vale se quiser VRAM livre para outros modelos do Ollama.
Custo: menos prefix cache e só ~1 sequência longa por vez. **Armadilha:** o `ExecStartPre` espera a
GPU 0 ficar < 1 GB; com o modelo do Ollama carregado nela, `make restart` dá timeout — rode
`ollama stop <modelo>` antes. Para voltar ao normal: remover `GPU_UTIL` do `.env`.

## Histórico de upgrade

**2026-11-12 — upgrade vLLM 0.31.0 → 0.33.0 concluído.** Clone do upstream movido de `95ee3b6`
(11/10) para `3d6c954` (11/10), **+258 commits**. `verify.sh --install` e `verify.sh`:
**OK, 0 failures**.

O que mudou no upstream: pin do vLLM 0.31.0 → **0.33.0** (torch 2.13 → **2.14.0+cu130**, Triton 3.8.0,
flashinfer-python 0.7.0.post1 → **0.7.2.post1**), série de patches **re-recortada** para o 0.33.0
(57 patches + 4 do KVarN), plugins novos `fa2/` (FA2 fp8-KV), `pthfa/` (pth-flash-attn int8-KV),
`lsa/`, overlay `opt-170hx/`, `xgrammar/` compilado do fonte, `scripts/` novos (turing bench/tui/watch).
O upstream documenta o port em `qwen38-27b-rtx3090/docs/vllm-0.33.md`.

**Procedimento (venv nativo, não Docker).** O upstream é explícito: *não* atualizar o venv antigo in
place — `pip` só substitui arquivos que a wheel possui, e módulos copiados dentro da árvore continuam
ao lado do pin novo. O caminho certo é criar um venv novo:

```bash
cd qwen38-27b-rtx3090
mv venv venv.failed-031 && python3.12 -m venv venv
venv/bin/pip install -r docker/requirements.txt          # pins do upstream
bash patches/apply.sh --list
bash patches/apply.sh "$(venv/bin/python -c 'import vllm,os;print(os.path.dirname(vllm.__file__))' | tail -n1)"
bash kvarn/install.sh
CXXFLAGS=-Wno-error bash xgrammar/install.sh
bash verify.sh --install
```

Quatro armadilhas deste ciclo:

1. **Os scripts do `venv/bin` guardam o caminho absoluto do interpretador nos shebangs.** Depois do
   `mv venv-033 venv`, os ~60 scripts ficaram apontando para `venv-033/bin/python3.12` e o serviço
   morreu com `cannot execute: required file not found` (exit 127). Corrigido com um `sed` em
   `venv/bin/*`, `venv/bin/activate{,.csh,.fish}` e `venv/pyvenv.cfg`.
2. **`kvarn/install.sh` e `verify.sh` usam `$REPO/venv` por default** — se o venv novo ainda estiver
   em `venv-033`, eles aplicam no venv **antigo** e acusam "vLLM version mismatch" em 21 checks.
   Troque o venv de lugar **antes** de rodar essas duas etapas.
3. **O build do xgrammar falha neste host** com um erro de ODR do LTO do GCC. Compilar com
   `CXXFLAGS=-Wno-error CFLAGS=-Wno-error` resolve.
4. **Sem `flashinfer-cubin` o vLLM avisa** "flashinfer-cubin is not installed and nvcc ... is missing"
   ao importar — mas o venv tem o toolchain CUDA 13.0 do pip (`nvidia/cu13/bin/nvcc`) e o launcher
   exporta `CUDA_HOME` para ele, então o JIT funciona. O cubin (6,3 GB) é opcional; o venv de
   produção roda sem ele.

**Validação executada:** `verify.sh --install` e `verify.sh` (0 failures) · `bench/api_smoke.py`
(12/12) · `bench/residue_sweep.py` (0 broken de 128) · chat, tool calling e streaming ·
8 requisições em paralelo (8/8) · FIM por `/v1/completions` · playground em :7860 (health + teste de
conexão com o vLLM) · A/B de performance contra o 0.31.0 com argv idêntico (paridade, 0,3%).

**Rollback:** o venv antigo está preservado em `qwen38-27b-rtx3090/venv.failed-031` (15 GB). Para
bootar com ele é preciso re-apontar os shebangs de `venv.failed-031/bin/*` para
`venv.failed-031/bin/python3.12` (ele foi construído como `venv-031` e renomeado). Para voltar ao
estado novo: `mv venv venv.033 && mv venv.failed-031 venv` + `sed` nos shebangs + `systemctl restart`.

**Ganho de disco:** caches limpos (`~/.cache/pip` 6,4 GB, `~/.cache/uv` 22 GB, `~/.cache/vllm` 13 GB,
build cache do Docker 4,1 GB) — o `/` saiu de 9,7 GB livres (95%) para ~42 GB (76%).

**2026-10-12 — upgrade vLLM 0.27.1 → 0.31.0 concluído.** Clone do upstream movido de `fdf9182`
(24/08) para `95ee3b6` (11/10), +385 commits. `verify.sh`: **OK, 0 failures**.

Medido após o upgrade (prompt curto, 600 tokens de saída): **143,6 tok/s em código**,
88,8 tok/s narrativo. KV cache subiu de 5,2 para **12,75 GiB por GPU** (o 0.31 dimensiona o pool
a partir de `GPU_UTIL` com TP=2 em vez do `KV_MEM` fixo de card único).

Quatro armadilhas encontradas na prática — leia antes de repetir o processo:

1. **Aspas no `EXTRA_ARGS`.** O launcher expande `${EXTRA_ARGS}` **sem aspas**. Aspas em volta
   apenas do JSON chegam literais ao argparse e matam o boot (`invalid loads value`); sem aspas
   nenhuma, o shell trata `{...}` como brace-expansion e a variável vira vazia. A forma correta é
   aspas simples em volta do **valor inteiro**. Validado nos dois caminhos (systemd `EnvironmentFile`
   e `source` no shell) antes de aplicar.
2. **O venv precisa se chamar `venv`.** O autodetect de `CUDA_HOME` procura em `"$REPO"/venv/`
   hardcoded. Instalar em `venv-031` e deixar assim quebra o FlashInfer JIT. Ao renomear, os
   shebangs dos ~59 scripts em `venv/bin/` apontam para o caminho antigo e precisam de um `sed`.
3. **`HOST=0.0.0.0` virou obrigatório.** Sem API key, o 0.31 liga em `127.0.0.1` (o 0.27.1 ligava em
   `0.0.0.0`). Os consumidores em `infra/opencode/`, `infra/openclaw/` e `.opencode/` apontam para
   `http://192.168.1.139:18020` e **todos quebram** sem essa linha no `.env`.
4. **`REASONING_EFFORT`/`ENABLE_THINKING` eram customização local**, não do upstream — vinham do
   commit local `fdf9182`, nunca estiveram no HyperQwen. No 0.31 são passados via
   `--default-chat-template-kwargs` dentro de `EXTRA_ARGS`.

O bloqueio do nvcc que parecia exigir instalar o CUDA 13 **resolveu-se sozinho**: o launcher 0.31
detecta nvcc < 13 no PATH e aponta `CUDA_HOME` para o toolchain CUDA 13.4 que o pip instala dentro
do venv. O patch local `CUDA_HOME=/usr/local/cuda` ficou obsoleto e foi descartado (apontaria de
volta para o 12.8).

5. **O campo de raciocínio mudou de nome na resposta.** O 0.31 emite `reasoning`, não
   `reasoning_content` (em JSON e em streaming). As configs do OpenCode liam o nome antigo e foram
   ajustadas — se o raciocínio sumir num cliente, é isto.

Sem rollback guardado: os backups do 0.27.1 foram removidos após a validação. Para voltar seria
preciso reinstalar `vllm==0.27.1` num venv limpo e dar `git checkout fdf9182` no clone.

**Ainda não adotado:** `KV_OFFLOAD_GB` (tier de KV cache em CPU via `/dev/shm`; a máquina tem só
20 GB de RAM, comece em 8), `VISION_OFFLOAD` (a visão voltou a ser possível neste stack).

**Modelo base no HuggingFace:** [Qwen/Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B) — nenhuma
mudança de peso. Último commit `37561816` (2026-11-07, "Add a response template and generation tags"):
o `chat_template.jinja` ganhou só marcações `{% generation %}` (máscara de treino); o texto renderizado
na inferência e os ramos de `reasoning_effort` são idênticos ao template local (md5 `519239a4…`).
Não aplicado — sem efeito em serving.
