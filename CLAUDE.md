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

**Patches do vLLM** ([qwen38-27b-rtx3090/patches/](qwen38-27b-rtx3090/patches/), **50 arquivos**):
backport do DFlash2, lookup drafting, atenção split-KV para o verify, softmax/top-k sem sort, int8/int4
KV, prefill int8, bounds de GDN, correções de serving (`/health`, 404 com nomes servidos, `/tokenize`).
A ordem é obrigatória — alguns carregam como contexto linhas que um patch anterior insere.
Aplique **sempre** via a porta única, que lê `patches/series` e recusa começar se a série e o
diretório discordarem:
```bash
cd qwen38-27b-rtx3090
VLLM_DIR=$(venv/bin/python -c 'import vllm,os;print(os.path.dirname(vllm.__file__))' | tail -n1)
bash patches/apply.sh --list        # confere série vs diretório (rc=2 se divergirem)
bash patches/apply.sh "$VLLM_DIR"   # aplica em ordem; --forward, --fuzz 0
```
Política `--fuzz 0`: um *offset* é benigno (o contexto casou exato), mas *fuzz* falha pelo nome em vez
de aplicar no chute. **Um upgrade do vLLM sem reaplicá-los dropa todas essas otimizações.**

**Camada downstream** ([infra/](infra/)): LiteLLM (`infra/litellm/`), OpenCode (`infra/opencode/`),
OpenClaw, logrotate. Todos devem referenciar `qwen3.8-27b` na porta **18020**.

## Config atual de produção

Verificado contra o processo vivo e `GET /v1/models` em 2026-10-12.

- **Modelo servido:** `qwen3.8-27b` → `models/Qwen3.8-27B-W4A16-AutoRound-fast`
- **Porta:** 18020 · **Contexto:** 142080 (`max_model_len`) · **TP:** 2
- **Spec decoding:** `{"method":"dflash","model":".../Qwen3.8-27B-DFlash2-W4A16","num_speculative_tokens":7}`
  - `DFLASH_TOKENS=7` é o default de chat — o drafter foi treinado para 7; posições 8-15 têm
    aceitação quase nula em chat geral. Use 15 apenas para reprodução de documento (custa ~8k de contexto).
- **KV cache:** bfloat16, ~**12,75 GiB por GPU** (o 0.31 com TP=2 dimensiona o pool a partir de
  `GPU_UTIL=0.93` e ignora o `KV_MEM` de card único)
- **Atenção:** `FLASH_ATTN` · `--mamba-cache-mode align` · `--enable-prefix-caching`
- **GPU util:** 0.93 · `--max-num-seqs 8` · `--max-num-batched-tokens 2048` · `--async-scheduling`
- **Parsers:** `--reasoning-parser qwen3` · `--tool-call-parser qwen3_coder` (+`--enable-auto-tool-choice`)
- **Raciocínio:** `REASONING_EFFORT=low`, `ENABLE_THINKING=true`, via `--default-chat-template-kwargs`
- **Prefix caching:** liga `--enable-prefix-caching --mamba-cache-mode align`. Ganho grande de TTFT em
  requests repetidos (2º turno contra doc de 25k: 0.56s vs 22.4s).
- **Binding:** `HOST=0.0.0.0` no `.env` — obrigatório desde o 0.31 (ver Histórico de upgrade).
- **Sem autenticação** — por isso o launcher emite um WARNING a cada boot. É o comportamento
  anterior, mas note que qualquer máquina da LAN alcança a porta.

**`REASONING_EFFORT`** é repassado ao template. Valores válidos: `low` | `medium` | `xhigh`
(`high` é alias de `xhigh`); qualquer outra coisa faz o template lançar exceção e a requisição falhar.
O que cada valor injeta não é o que o nome sugere:
- `xhigh` (default do template) → "think carefully, validate key assumptions, consider alternatives…"
- `medium` → **nada**. Não existe ramo `medium` no template; é "sem orientação", não "esforço médio".
- `low` → "Keep your thinking brief and focused, moving directly to the conclusion." **Em uso** — é o
  único valor que efetivamente pede thinking curto.

**Performance medida localmente em 2026-10-12** (vLLM 0.31.0, prompt curto, 600 tokens de saída):
**143,6 tok/s em código**, 88,8 tok/s narrativo. Números de batch/prefill do README do upstream
(~1094 tok/s a 64 concorrentes, ~1810 tok/s de prefill) seguem **não remedidos** aqui.

**Hardware:** 2x RTX 3090 (48 GB). ~16.3 GB por GPU em uso (~66%).

## Histórico de upgrade

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

**Modelo base no HuggingFace sem novidade:** [Qwen/Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B)
teve último commit em agosto/2026, só README/tokenizer/generation_config — nenhuma mudança de peso.
