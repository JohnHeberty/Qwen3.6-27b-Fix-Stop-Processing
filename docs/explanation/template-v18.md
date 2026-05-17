# Template v18 — froggeric

---

## Créditos

Este projeto utiliza o **Jinja2 chat template v18** criado por [**froggeric**](https://huggingface.co/froggeric):

> **[huggingface.co/froggeric/Qwen-Fixed-Chat-Templates](https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates)**

O template v18 é um drop-in replacement para o template oficial do Qwen3.6 que corrige múltiplos bugs críticos presentes no template publicado pela Alibaba/Qwen.

---

## O que o template v18 corrige

### KV Cache invalidation

O template oficial invalida o KV cache a cada turno em conversas multi-turno, forçando re-processamento completo do prompt a cada resposta. O v18 normaliza o whitespace de forma a manter 100% de hit rate no KV cache — reduz significativamente a latência em conversas longas.

### Tool calling loops

A detecção de erros no template original era baseada em substring: se a resposta JSON continha a palavra `"error"` (por qualquer razão), o template interpretava como falha e entrava em loop. O v18 usa detecção baseada em estrutura estrita, eliminando falsos positivos.

### Compatibilidade com engines legados

O template original usava `loop.previtem` (feature do Jinja2 moderno) que causava crashes em builds antigos do llama.cpp e no minijinja. O v18 substitui por indexação de array — compatível com todas as versões.

### Thinking mode bypass

`enable_thinking=false` não era respeitado em certos fluxos de chamada. O v18 corrige o comportamento para que o controle de thinking mode seja consistente.

### Escalada de erros em tool chains

Sistema de dois níveis com contador `consecutive_failures` para workflows agênticos — evita loops infinitos em tool calls com falhas consecutivas.

---

## Como o patch é aplicado

O template é patchado **diretamente no arquivo GGUF** via `src/fix_template.py`. Isso garante que o template correto é usado independente do cliente ou configuração de servidor.

O patch é binário (streaming) para evitar corrupção dos tokens byte-level do vocabulário:

1. Lê o header GGUF com forward-scan para localizar `tokenizer.chat_template`
2. Calcula o padding de alinhamento (32 bytes) após a substituição
3. Stream-copia o arquivo inteiro para `/tmp` com o novo template e padding correto
4. Substitui o original atomicamente via `shutil.move`
5. Salva backup do template original em `data/backups/gguf_template_backup_<ts>.jinja`

```bash
make fix-template   # aplica o patch
```

---

## Compatibilidade

O template v18 é compatível com:
- llama.cpp / llama-server
- LM Studio
- vLLM
- MLX
- Qualquer engine com suporte a templates HuggingFace Jinja2

---

## Arquivo do template

O template está em `data/templates/archive/qwen3.6/chat_template-v18.jinja` após o `make setup`.
