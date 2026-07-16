## Veredito

**Sim — assumindo uma única GPU com 24 GB, como a RTX 3090, dá para chegar perto da faixa “normal” do post, mas não manter o pico de 100+ tokens/s.**

Uma meta realista para o Qwen3.6-27B seria:

| Configuração                                   |                                              Geração observada |
| ---------------------------------------------- | -------------------------------------------------------------: |
| Seu projeto atual, `llama.cpp` Q5_K_M, 16k–64k |                                                **25–30 tok/s** |
| Uma RTX 3090, vLLM INT4, sem MTP, 32k          |                                          cerca de **32 tok/s** |
| Uma RTX 3090, vLLM INT4 + MTP, 20k             |                      **55 tok/s geral / 70,5 tok/s em código** |
| Uma RTX 3090, vLLM INT4 + MTP, 48k             |                                          **50,9 / 67,5 tok/s** |
| Duas RTX 3090 do post                          | normalmente **60–106 tok/s**, com 100+ em condições favoráveis |

Os benchmarks de uma única 3090 mostram que o teto prático fica em aproximadamente **50–55 tok/s para texto geral e 67–70 tok/s para código estruturado**. Portanto, é possível chegar perto do limite inferior do post, mas o pico de 100+ tok/s depende das duas GPUs, tensor parallel, NVLink, AWQ INT4 e alta aceitação do MTP. ([GitHub][1])

## Contexto menor não é suficiente sozinho

No benchmark do seu próprio projeto:

* 16k: 29,8 tok/s
* 32k: 28,4 tok/s
* 48k: 26,9 tok/s
* 64k: 25,5 tok/s

Reduzir de 64k para 16k melhora a geração em apenas cerca de **17%**. O principal benefício é liberar VRAM, reduzir tempo de prefill e melhorar o primeiro token. Durante a geração, o modelo continua precisando ler aproximadamente 17–20 GB de pesos a cada token, então a banda de memória permanece sendo o principal gargalo. ([GitHub][2])

O salto de aproximadamente 30 para 50–70 tok/s vem principalmente de:

1. Quantização INT4 otimizada para vLLM;
2. MTP/speculative decoding;
3. Kernels FlashInfer/CUDA;
4. Contexto e concorrência controlados;
5. Maior taxa de aceitação de tokens especulativos.

## Como aplicar isso ao seu projeto

Seu patch é **complementar** à otimização de desempenho. Ele resolve template, encerramento prematuro, chamadas de ferramentas e invalidação do KV cache. Isso pode melhorar bastante conversas multi-turno e agentes, mas não multiplica sozinho a velocidade de geração bruta. ([GitHub][2])

Eu estruturaria o projeto com três perfis.

### 1. `stable`

Manter o comportamento padrão do projeto:

* `llama.cpp`
* Q5_K_M
* 80k de contexto
* MTP habilitado (padrão)
* Patch de template aplicado

Esse seria o perfil padrão — MTP habilitado com 80k de contexto para ~68 tok/s.

### 2. `fast`

Ainda usando `llama-server`:

* Q5_K_M
* 80k de contexto
* KV cache Q8
* uma sequência
* MTP habilitado
* template externo corrigido

O `llama.cpp` atual já possui suporte a `draft-mtp`, embora o ganho precise ser validado especificamente na RTX 3090 porque a eficácia varia conforme backend e prompt. ([GitHub][3])

Exemplo inicial:

```bash
llama-server \
  --model data/models/Qwen3.6-27B-Q5_K_M.gguf \
  --gpu-layers all \
  --ctx-size 81920 \
  --parallel 1 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --flash-attn on \
  --batch-size 2048 \
  --ubatch-size 512 \
  --jinja \
  --chat-template-file data/templates/chat_template.jinja \
  --spec-type draft-mtp \
  --spec-draft-n-max 3 \
  --host 0.0.0.0 \
  --port 8000
```

Eu começaria testando:

```text
--spec-draft-n-max 1
--spec-draft-n-max 2
--spec-draft-n-max 3
```

Mais tokens especulativos não significam automaticamente mais desempenho. Com baixa aceitação, o custo extra pode até reduzir a velocidade.

### 3. `turbo-vllm`

Esse é o perfil com maior chance de alcançar **50–70 tok/s**:

* vLLM
* checkpoint INT4 compatível com MTP
* contexto de 20k ou 80k
* `max-num-seqs=1`
* MTP com três tokens
* modo somente texto, quando visão não for necessária
* template corrigido como arquivo externo

O suporte oficial informa que o Qwen3.6-27B INT4 cabe em uma GPU de 24 GB e que o modelo suporta MTP diretamente no vLLM. ([vLLM Recipes][4])

Uma configuração inicial seria:

```bash
vllm serve <checkpoint-qwen3.6-27b-int4> \
  --max-model-len 20000 \
  --max-num-seqs 1 \
  --gpu-memory-utilization 0.92 \
  --language-model-only \
  --chat-template data/templates/chat_template.jinja \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --speculative-config '{"method":"mtp","num_speculative_tokens":3}'
```

Para 48k:

```bash
--max-model-len 49152
```

O desempenho medido entre 20k e 48k muda pouco; portanto, **80k provavelmente oferece melhor equilíbrio do que limitar agressivamente a 8k ou 16k**. ([GitHub][1])

## Atualização importante no patch

Seu projeto atualmente referencia uma versão anterior do template corrigido. A versão publicada mais recentemente é a **v21.3**, com correções adicionais para:

* invalidação de prefix/KV cache;
* encerramento prematuro;
* loops de tool calling;
* mensagens de ferramentas;
* compatibilidade com `llama.cpp` e vLLM.

Vale fixar uma versão e checksum no projeto, em vez de baixar sempre a versão “latest”. ([Hugging Face][5])

Também seria melhor evitar alterar permanentemente o binário GGUF quando o servidor permite:

```bash
--jinja --chat-template-file data/templates/chat_template.jinja
```

Assim, o mesmo patch pode ser usado tanto pelo backend `llama.cpp` quanto pelo backend vLLM, sem manter duas cópias modificadas do modelo.

## Pontos que eu ajustaria no repositório

Há algumas configurações atualmente desalinhadas entre documentação e `.env.example`:

* benchmark documentado com Q5_K_M;
* documentação usando 80k;
* ausência de uma opção explícita para MTP;
* backend fixado em `llama-server`.

Uma organização adequada seria:

```text
BACKEND=llama_cpp|vllm
PROFILE=stable|fast|turbo
MODEL_QUANT=Q5_K_M|INT4
CONTEXT_SIZE=81920
ENABLE_MTP=true
MTP_TOKENS=3
```

## Resultado esperado

Para uma RTX 3090 de 24 GB:

* **30 tok/s:** praticamente garantido com sua arquitetura atual;
* **40–55 tok/s:** objetivo com `llama.cpp` + Q5_K_M + MTP, dependendo da aceitação;
* **50–70 tok/s:** objetivo comprovadamente atingível com vLLM + MTP;
* **80+ tok/s:** possível apenas em prompts altamente favoráveis ou como pico;
* **100+ tok/s sustentados:** improvável em uma única 3090 com um modelo dense de 27B.

O caminho mais sólido é preservar o `llama.cpp` como backend estável e adicionar um segundo backend `vllm-mtp`, usando exatamente o mesmo template corrigido e uma suíte de benchmark que separe **prefill, decode, aceitação MTP, VRAM e tool calling**.

[1]: https://github.com/noonghunna/qwen36-27b-single-3090 "GitHub - noonghunna/qwen36-27b-single-3090 · GitHub"
[2]: https://github.com/JohnHeberty/Qwen3.6-27b-Fix-Stop-Processing "GitHub - JohnHeberty/Qwen3.6-27b-Fix-Stop-Processing · GitHub"
[3]: https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md "llama.cpp/docs/speculative.md at master · ggml-org/llama.cpp · GitHub"
[4]: https://recipes.vllm.ai/Qwen/Qwen3.6-27B "Qwen/Qwen3.6-27B | vLLM Recipes"
[5]: https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates "froggeric/Qwen-Fixed-Chat-Templates · Hugging Face"
