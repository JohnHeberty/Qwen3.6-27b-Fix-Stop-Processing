# vLLM × llama.cpp — Qwen3.6-27B numa RTX 3090

Medido em **2026-07-29** com a mesma ferramenta (`tests/bench_decode.py`), mesmo prompt, mesma
definição de tok/s (`usage.completion_tokens`, nonce por execução para invalidar prefix cache).

## Resultado

| | llama.cpp Q5_K_M | vLLM INT4 · KV fp16 | **vLLM INT4 · KV fp8_e5m2** |
|---|---|---|---|
| decode tok/s @8k | 58,27 | 69,49 | **84,61** |
| decode tok/s @24k | 55,95 | 46,52 | **82,44** |
| TTFT @24k | 22,14 s | 23,48 s | **20,04 s** |
| Contexto máximo | **106.496** | 28.315 | 56.631 |
| Suíte de 13 testes | 13/13 | — | **13/13** |

**+47% de decode a 24k** e **+45% a 8k** contra o llama.cpp, ao custo de **metade do contexto**.

Note o salto entre as duas colunas de vLLM: fp16 é *mais lento* que o llama.cpp a 24k (46,52),
porque o KV fica a 85% da capacidade e sufoca o scheduler. Só com fp8 o vLLM ganha de verdade.
Ou seja: **KV comprimido não é otimização opcional aqui, é o que faz a migração valer.**

## A configuração que funciona

```
Modelo   Lorbus/Qwen3.6-27B-int4-AutoRound (18 GB, W4A16, mtp.fc em BF16)
vLLM     0.26.0 · torch 2.11.0+cu130
KV       fp8_e5m2          (fp8 como armazenamento; Ampere não tem FP8 de compute)
MTP      n=3
Parsers  --reasoning-parser qwen3  --tool-call-parser qwen3_xml
CUDA     CUDA_HOME=/usr/local/cuda (12.8 do sistema)
Extra    flashinfer-python==0.6.13 + flashinfer-cubin==0.6.13
```

## Três armadilhas que custaram caro

**1. O FlashInfer compila kernels em JIT no primeiro request.** Com KV em fp8 ele é obrigatório, e
falha de dois jeitos opostos: sem `CUDA_HOME` não acha `cuda_runtime.h`; apontando para o toolkit
cu13 que vem no wheel do torch, o `cccl` do flashinfer 0.6.13 reclama de
*"CUDA compiler and CUDA toolkit headers are incompatible"*. Tem de ser o **12.8 do sistema**.

**2. Atualizar o vLLM traz flashinfer 0.6.14 de volta e quebra tudo.** Reinstale sempre com
`--no-deps`, senão o flashinfer arrasta o torch para cu12 e destrói o ambiente:
```bash
uv pip install --no-deps "flashinfer-python==0.6.13" "flashinfer-cubin==0.6.13"
```

**3. O parser de tool-call `hermes` não serve.** Este modelo emite XML
(`<function=nome><parameter=x>`), não o JSON do Hermes. Com `hermes` os 5 testes de ferramenta
falham em silêncio — o tool call vira texto no `content`. O parser certo é **`qwen3_xml`**.

## Mudança de contrato: `reasoning_content` → `reasoning`

O llama.cpp (`--reasoning-format deepseek`) devolve o raciocínio em **`reasoning_content`**.
O vLLM 0.26 devolve em **`reasoning`**, e **não há flag de compatibilidade**.

`tests/test_api.py` e `tests/bench_decode.py` já aceitam os dois nomes. **Os clientes não**:

| Cliente | Onde |
|---|---|
| OpenCode | `interleaved.field: "reasoning_content"` |
| OpenClaw | consome `reasoning_content` para exibir o raciocínio |

Antes de promover o vLLM a padrão, confirmar se o LiteLLM normaliza o campo. Se não normalizar,
os dois clientes param de mostrar raciocínio até serem reconfigurados.

## O que NÃO funciona nesta placa

**TurboQuant** (o caminho para 104k+) é incompatível com este modelo. O Qwen3.6-27B é híbrido —
**48 das 64 camadas são `linear_attention`** e só 16 têm KV comprimível. Bugs abertos no vLLM:

- [#41560](https://github.com/vllm-project/vllm/issues/41560) — falha em Qwen3_5 híbrido: a
  geometria de página das camadas GDN difere das de atenção. É o erro que reproduzimos.
- [#40124](https://github.com/vllm-project/vllm/issues/40124) — TurboQuant + híbrido quebrado em
  **Ampere (SM 80-86)**; precisa de 13 patches de terceiros.
- [#41726](https://github.com/vllm-project/vllm/issues/41726) — a PR que conserta híbrido (#39931)
  trava em prefill longo.
- [#40831](https://github.com/vllm-project/vllm/issues/40831) — **TurboQuant × speculative decoding
  produz "degenerate token loops"**.

O último importa em especial: TurboQuant + MTP reproduziria o loop de repetição que este projeto
passou dias diagnosticando.

**FP8 de compute** também não existe em Ampere. O `fp8_e5m2` aqui é só formato de armazenamento do
KV; a conversão é feita em software.

## A decisão que sobra

Não é "vLLM é melhor". É um troco explícito:

| | Fica com |
|---|---|
| **llama.cpp** | 106.496 de contexto, 56 tok/s, contrato `reasoning_content` intacto |
| **vLLM** | 56.631 de contexto, 82 tok/s (+47%), clientes precisam de ajuste |

Se o uso agêntico rotineiramente passa de 56k, o llama.cpp continua sendo a escolha certa apesar de
mais lento — velocidade não compensa o turno que morre por falta de contexto.
