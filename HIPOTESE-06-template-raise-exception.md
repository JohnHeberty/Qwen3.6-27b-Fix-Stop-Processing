# HIPÓTESE 06 — Template lança `raise_exception` em mensagem mal-formada

**Status:** NÃO INVESTIGADO · **Suspeita:** MÉDIA/BAIXA

## Hipótese
O template tem 5 pontos que **abortam a renderização** com `raise_exception`. Se o cliente manda
uma mensagem numa forma inesperada (ex.: `content` como dict/mapping em vez de string/lista; system
com imagem; `messages` vazio), o template estoura → llama-server devolve erro → agente falha.

## Evidência a favor
- `chat_template_local.jinja`, pontos de throw:
  - `No messages provided.` (messages vazio)
  - `Unexpected content type.` (content não é string, nem lista, nem none) ← **mais provável**
  - `Unexpected item type in content.` (item de lista sem `text`/`image`/`video`)
  - `System message cannot contain images.` / `... videos.`
- Um agente que monta o histórico "na mão" (OpenClaw) pode facilmente mandar `content` como objeto.

## Evidência contra
- `server.log` **não** mostra erros de template/jinja (grep `jinja`=0, `exception`=0). Se fosse
  frequente, provavelmente apareceria algum erro de render. Por isso a suspeita é média/baixa.
- Precisa confirmar se erro de render do template é logado no server.log ou só retornado ao cliente.

## Como investigar
1. Renderizar o template offline (via `data/templates/scripts/test_template.py` / jinja) com
   `content` sendo um dict, um role estranho, e `messages=[]`, e ver o throw.
2. Ligar log de request no LiteLLM para capturar o JSON exato que o MoltBot envia e checar o shape
   do `content` das mensagens.
3. Testar contra `:8000` um request com `content` mapping e ver a resposta de erro do llama-server.

## Confirmação / refutação
- **Confirma** se o JSON enviado pelo MoltBot tem `content` num shape que dispara um dos 5 throws.
- **Refuta** se o `content` é sempre string/lista bem-formada.

## Correção provável (se confirmada)
- Tornar o `render_content` do template tolerante (coagir mapping/None para string em vez de
  `raise_exception`), ou corrigir o cliente para enviar `content` no formato OpenAI padrão.
