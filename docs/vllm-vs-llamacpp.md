# vLLM × llama.cpp — Qwen3.6-27B numa RTX 3090

Medido em **2026-07-29** com a mesma ferramenta (`tests/bench_decode.py`), mesmo prompt, mesma
definição de tok/s (`usage.completion_tokens`, nonce por execução para invalidar prefix cache).

## Resultado — varredura completa de KV cache

Todos os `--kv-cache-dtype` que o vLLM 0.26 aceita, medidos com prompt de ~23,2k:

| Config | Contexto máx | decode tok/s @24k | TTFT |
|---|---|---|---|
| **llama.cpp** Q5_K_M + KV `q4_0` | **106.496** | 55,95 | 22,1 s |
| vLLM KV `auto` (fp16) | 28.315 | 46,52 | 23,5 s |
| **vLLM KV `fp8_e5m2`** | 56.631 | **82,44** | **20,0 s** |
| vLLM KV `int4_per_token_head` | **112.885** | 36,54 | 28,4 s |
| vLLM KV `int4` @ 65k | 93.875 | 35,21 | 28,4 s |
| vLLM KV `turboquant_*` (4 presets) | — | não inicializa | — |

A 8k: llama.cpp 58,27 · vLLM fp8 **84,61**. Suíte de 13 testes: 13/13 em ambas as engines.

**A conclusão é que não existe configuração que entregue as duas coisas.**

- Para **velocidade**: `fp8_e5m2` dá +47%, mas o contexto cai para 56.631.
- Para **contexto**: `int4_per_token_head` entrega 112.885 — mas a 36,5 tok/s, **35% mais lento que
  o llama.cpp** no mesmo contexto.

O custo do int4 é **intrínseco ao dtype**, não pressão de escalonamento: medido a 65k (folga de KV
de 1,43x) dá 35,21, praticamente igual aos 36,54 medidos a 104k (folga 1,06x). Não adianta procurar
um ponto ótimo intermediário.

Note também que fp16 é *mais lento* que o llama.cpp (46,52), porque a 24k o KV fica a 85% da
capacidade e sufoca o scheduler. Só com fp8 o vLLM ganha — **KV comprimido não é otimização
opcional aqui, é o que faz a migração valer.**

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

Não é "vLLM é melhor". São dois pontos de operação, e o meio-termo não existe:

| | Contexto | tok/s @24k | Observação |
|---|---|---|---|
| **llama.cpp** | 106.496 | 55,95 | contrato `reasoning_content` intacto |
| **vLLM fp8** | 56.631 | 82,44 (+47%) | clientes precisam de ajuste |
| vLLM int4 | 112.885 | 36,54 (−35%) | mesmo contexto do llama.cpp, mas mais lento |

**No contexto que este projeto exige (104k), o llama.cpp é 53% mais rápido que o vLLM.**
O vLLM só ganha aceitando metade do contexto.

### Quanto contexto as sessões realmente usam

Medido nos logs de produção de 2026-07-28 (prompts que chegaram ao servidor e estimativas do
OpenClaw nos erros de overflow):

```
69.835 · 70.462 · 70.974 · 72.039 · 75.780      (recebidos pelo llama-server)
74.829 · 82.043 · 86.277 · 89.560 · 101.426     (estimados pelo OpenClaw)
```

Todos **acima de 56.631**. O teto do vLLM fp8 ficaria abaixo do piso de uso real — a compactação
destrutiva passaria a disparar em quase toda tarefa de pesquisa, que é justamente o que produzia o
loop de re-anúncio. 47% mais rápido em turnos que não terminam não é ganho.

### Quando reconsiderar

- **Segunda RTX 3090** (TP=2): os pesos se dividem, sobram ~14 GB para KV, e aí dá para ter os
  256k nativos *com* a velocidade do vLLM. Resolve os dois lados.
- **TurboQuant estabilizar para modelos híbridos** — acompanhar os 4 issues citados acima.
- **Modelo menor** (14B INT4, ~9 GB) deixaria ~12 GB de KV: contexto folgado e ainda mais rápido,
  trocando qualidade por espaço.
