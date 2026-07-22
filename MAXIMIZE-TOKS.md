## Diagnóstico

O seu servidor **não está necessariamente 22 tok/s mais lento**. O número de **72,5 tok/s** do outro repositório foi obtido com um prompt curto, de aproximadamente 200 tokens, contexto configurado em 32k e MTP `n=3`. No teste com um prompt real de aproximadamente **24 mil tokens**, esse mesmo preset entregou cerca de **50 tok/s** — praticamente o desempenho que você observou. O preset mais otimizado do projeto chega a aproximadamente **64,5 tok/s em 24k**, usando MTP `n=6`. ([GitHub][1])

### Comparação real

| Item                       | Repositório devnen        | Seu repositório   |
| -------------------------- | ------------------------- | ----------------- |
| Engine                     | vLLM modificado           | llama.cpp         |
| Pesos                      | AutoRound INT4            | GGUF Q5_K_M       |
| Tamanho aproximado         | 16,9 GB                   | 19 GB             |
| KV cache                   | FP8 E4M3                  | Q8_0              |
| MTP                        | 6 tokens no preset rápido | 3 tokens          |
| Attention                  | Triton Attention          | kernels llama.cpp |
| CUDA Graph                 | Ativado                   | não equivalente   |
| Prompt do número divulgado | Curto, ~200 tokens        | testes de 8k–80k  |
| Resultado em ~24k          | 50–64,5 tok/s             | 47,6–50 tok/s     |

As configurações do devnen incluem `auto-round`, `fp8_e4m3`, `TRITON_ATTN`, CUDA Graphs, `VLLM_MARLIN_USE_ATOMIC_ADD=1`, memória da GPU configurada em `0.948` e MTP com seis tokens. O seu servidor usa `llama-server`, Q5_K_M, KV Q8_0, batch 4096 e MTP `n=3`. ([GitHub][2])

## Problema mais importante: seu benchmark não mede tokens

No seu `tests/benchmark.py`, o contador é incrementado desta forma:

```python
if content:
    token_count += 1
```

Depois:

```python
tok_per_sec = token_count / gen_time
```

Isso mede **quantos eventos/chunks SSE foram recebidos por segundo**, não quantos tokens o modelo gerou. Um chunk SSE pode conter um token, parte de um token ou vários tokens. Portanto, o seu valor de `50 tok/s` não é uma medição confiável de tokens por segundo. ([GitHub][3])

O benchmark do devnen solicita `stream_options.include_usage` e utiliza o valor final de `usage.completion_tokens`. Ou seja, ele conta os tokens informados pelo tokenizer do servidor, não os chunks HTTP. ([GitHub][4])

A correção conceitual deve ser semelhante a:

```python
payload["stream_options"] = {"include_usage": True}

usage = None
first_token_time = None
end_time = None

for line in response.iter_lines():
    # decodificar o evento SSE...

    if chunk.get("usage"):
        usage = chunk["usage"]

    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content")

    if content:
        now = time.perf_counter()

        if first_token_time is None:
            first_token_time = now

        end_time = now

completion_tokens = usage["completion_tokens"]
decode_seconds = end_time - first_token_time
decode_tps = completion_tokens / decode_seconds
```

Caso a sua versão do `llama-server` não forneça `usage` durante streaming, acumule a saída completa e passe o texto pelo tokenizer ou endpoint de tokenização. **Não use quantidade de chunks como fallback.**

## De onde vem o ganho real do outro projeto

### 1. MTP `n=6`

Esse provavelmente é o maior ganho isolado. O sweep publicado pelo devnen encontrou aproximadamente:

* `n=3`: 53,4 tok/s
* `n=4`: 58,3 tok/s
* `n=5`: 62,8 tok/s
* `n=6`: 64,5 tok/s
* `n=7`: 61,5 tok/s
* `n=8`: 58 tok/s

Portanto, no workload longo deles, passar de `n=3` para `n=6` representa aproximadamente **21% de ganho**. Acima disso, a taxa de aceitação cai e o desempenho piora. ([GitHub][5])

Seu backend llama.cpp está configurado para três tokens. Mesmo que você aumentasse diretamente para seis, não há garantia de que a implementação e o draft model GGUF aceitariam ou escalariam da mesma maneira que o backend vLLM modificado.

### 2. AutoRound INT4 contra GGUF Q5_K_M

O seu Q5_K_M movimenta aproximadamente 19 GB de pesos durante a geração. O AutoRound INT4 usado pelo outro projeto fica próximo de 16,9 GB. Como a geração de um único usuário costuma ser bastante limitada por largura de banda de memória, a inferência provável é que o modelo INT4 exija menos tráfego de VRAM por token. ([GitHub][2])

Os seus próprios resultados mostram a vantagem de Q4 sobre Q5:

* 8k: `53,5` contra `50 tok/s`
* 40k: `47,6` contra `44,4 tok/s`
* 72k: `45,7` contra `41,7 tok/s`

Isso sugere um ganho de aproximadamente **7% a 10%** mudando de Q5 para Q4, ainda insuficiente sozinho para transformar 50 em 72 tok/s. ([GitHub][6])

### 3. Kernels vLLM/Marlin, Triton e CUDA Graphs

O servidor rápido não é apenas “o mesmo modelo com outras flags”. Ele utiliza outra pilha de execução:

* kernels AutoRound/Marlin;
* Triton Attention;
* CUDA Graphs;
* speculative decoding integrado ao scheduler do vLLM;
* alocação de aproximadamente 94,8% da VRAM;
* GPU de inferência separada da GPU usada pelo desktop;
* limite de energia de até 350 W.

Esses ganhos são cumulativos, mas não podem ser reproduzidos integralmente apenas alterando flags do llama.cpp. ([GitHub][2])

### 4. Comprimento do prompt

O seu benchmark detalhado já mostra a queda conforme o contexto ativo aumenta:

* 8k: 50 tok/s
* 24k: 47,6 tok/s
* 40k: 44,4 tok/s
* 72k: 41,7 tok/s
* 80k: queda severa para aproximadamente 10 tok/s

Portanto, comparar seu resultado de 24k, 40k ou 72k com os 72,5 tok/s obtidos pelo outro projeto em um chat curto é uma comparação inadequada. ([GitHub][6])

## Ordem recomendada de otimização

### 1. Corrigir o benchmark

Use exatamente o mesmo:

* prompt;
* número máximo de tokens;
* temperatura;
* seed;
* modelo;
* warm-up;
* quantidade de execuções;
* definição de decode tok/s.

Registre separadamente:

```text
prompt_tokens
completion_tokens
time_to_first_token
prefill_tokens_per_second
decode_tokens_per_second
wall_clock_tokens_per_second
```

Faça três warm-ups e pelo menos cinco execuções medidas. Prefix cache deve estar desativado ou invalidado durante a comparação.

### 2. Testar Q4_K_M no seu backend

Pelos números do próprio repositório, esta é a otimização mais simples para obter aproximadamente 7–10% sem trocar a arquitetura inteira.

### 3. Criar um sweep reproduzível

Teste, mantendo o mesmo prompt:

```text
MTP_TOKENS = 1, 2, 3
N_CTX      = 32768, 49152, 73728
BATCH      = 2048, 4096
UBATCH     = valores suportados pela build
KV cache   = q8_0 e alternativas compatíveis
```

Aumentar o contexto máximo sem necessidade consome VRAM e pode reduzir a margem disponível, embora o principal fator seja o tamanho do contexto efetivamente processado.

### 4. Tornar o build do llama.cpp reproduzível

Seu `Makefile` clona o `latest` do llama.cpp e compila basicamente com `GGML_CUDA=ON`. Isso torna os resultados instáveis entre builds. Fixe um commit conhecido e teste uma build específica para a RTX 3090:

```bash
cmake -B build \
  -DGGML_CUDA=ON \
  -DCMAKE_CUDA_ARCHITECTURES=86 \
  -DCMAKE_BUILD_TYPE=Release
```

Também vale comparar Flash Attention ativado e desativado, conforme o suporte da versão fixada.

### 5. Para realmente buscar 64–72 tok/s

A rota mais provável não é continuar ajustando Q5_K_M no llama.cpp. É criar um backend alternativo com a mesma pilha do outro projeto:

```text
Qwen3.6 AutoRound INT4
vLLM compatível
KV FP8 E4M3
Triton Attention
CUDA Graphs
MTP sweep até n=6
GPU sem carga gráfica
power limit adequado à placa
```

## Conclusão

Há três números diferentes sendo misturados:

1. **72,5 tok/s:** devnen, prompt curto.
2. **64,5 tok/s:** devnen, prompt de aproximadamente 24k, MTP `n=6`.
3. **47,6–50 “tok/s”:** seu servidor, Q5_K_M, MTP `n=3`, com um benchmark que atualmente conta chunks SSE.

Em condições semelhantes de prompt longo e MTP `n=3`, o próprio repositório devnen também registra aproximadamente **50 tok/s**. A diferença real a investigar não é 72 contra 50, mas algo próximo de **64,5 contra 47,6–50**, e parte desse intervalo vem de MTP `n=6`, INT4 e do backend vLLM/Marlin. Antes de qualquer alteração de desempenho, a prioridade deve ser corrigir `tests/benchmark.py`.

[1]: https://github.com/devnen/qwen3.6-windows-server/blob/main/dist/RELEASE_NOTES.md?utm_source=chatgpt.com "qwen3.6-windows-server/dist/RELEASE_NOTES.md at main - GitHub"
[2]: https://github.com/devnen/qwen3.6-windows-server/raw/refs/heads/main/snapshots/start_speed.py "raw.githubusercontent.com"
[3]: https://github.com/JohnHeberty/Qwen3.6-27b-Fix-Stop-Processing/blob/main/tests/benchmark.py "Qwen3.6-27b-Fix-Stop-Processing/tests/benchmark.py at main · JohnHeberty/Qwen3.6-27b-Fix-Stop-Processing · GitHub"
[4]: https://github.com/devnen/qwen3.6-windows-server/blob/main/windows_tools/bench.py "qwen3.6-windows-server/windows_tools/bench.py at main · devnen/qwen3.6-windows-server · GitHub"
[5]: https://github.com/devnen/qwen3.6-windows-server/blob/main/docs/TUNING.md?utm_source=chatgpt.com "qwen3.6-windows-server/docs/TUNING.md at main - GitHub"
[6]: https://github.com/JohnHeberty/Qwen3.6-27b-Fix-Stop-Processing/blob/main/docs/infra/README-q5.md "Qwen3.6-27b-Fix-Stop-Processing/docs/infra/README-q5.md at main · JohnHeberty/Qwen3.6-27b-Fix-Stop-Processing · GitHub"
