# TOOLS.md

> Os **schemas** das ferramentas (nome, parâmetros, tipos, obrigatoriedade) já chegam
> no seu contexto a cada turno. Este arquivo NÃO os repete. Aqui fica só o que o schema
> não diz: as regras deste ambiente e as armadilhas já conhecidas.
>
> Detalhe completo de uma ferramenta: `exec: sed -n '1,120p' /usr/lib/node_modules/openclaw/docs/tools/<arquivo>.md`
> (descubra o nome com `exec: ls /usr/lib/node_modules/openclaw/docs/tools/`)

## Regras de ambiente

- **`read`/`write`/`edit` só enxergam `~/.openclaw/workspace`.** Caminho fora disso falha com
  "Path escapes sandbox root". Para ler qualquer coisa fora (docs, `/etc`, `/usr/lib`), use `exec`
  com `cat`/`sed`.
- Arquivos temporários/scratch: `.openclaw/tmp/` **dentro** do workspace.
- Resultado de ferramenta é cortado em **16.000 chars**. Prefira `sed -n 'A,Bp'` a `cat` em
  arquivos grandes.
- `read` trunca em 2000 linhas ou 50KB — use `offset`/`limit` para continuar.

## Índice

| Categoria | Ferramentas |
|---|---|
| Arquivos | `read` `write` `edit` `apply_patch` |
| Execução | `exec` `process` |
| Web | `web_search` `web_fetch` |
| Memória | `memory_search` `memory_get` |
| Sessões | `sessions_list` `sessions_history` `sessions_send` `sessions_spawn` `sessions_yield` `subagents` `session_status` |
| Mensagens | `message` |
| Planejamento | `update_plan` `create_goal` `get_goal` `update_goal` |
| Automação | `cron` `skill_workshop` |

## Escolha da ferramenta

- Editar arquivo existente → **`edit`**, nunca `write`. `write` sobrescreve o arquivo inteiro e
  custa muitos tokens de saída.
- Mudança em vários arquivos de uma vez → **`apply_patch`**.
- Comando que demora → **`exec` com `background`/`yieldMs`**, depois **`process`** para acompanhar.
  Nunca simule espera com `sleep` em loop.
- Agendar algo → **`cron`**. Nunca emule agendamento com `exec sleep`.
- Trabalho paralelo ou que sujaria muito o contexto → **`sessions_spawn`** e depois
  **`sessions_yield`** (não fique em loop de polling).
- Perguntas sobre trabalho/decisões/datas anteriores → **`memory_search` primeiro**, antes de responder.

## Armadilhas conhecidas (pagas em produção)

- **Sucesso é sucesso.** Se a ferramenta retornou sem erro, a operação foi feita. Nunca repita a
  mesma chamada "para garantir" — o detector de loop avisa em 10 repetições idênticas e
  **bloqueia a sessão em 20**.
- **`write` em modo append devolve sempre a mesma frase**, sem tamanho nem posição. Não é sinal de
  que a anterior falhou. Em dúvida, `read` no arquivo em vez de reescrever.
- **Não deduza caminhos.** Se um arquivo não existe onde você esperava, rode `ls` e ache o nome
  certo. Deduzir caminho por analogia já causou ENOENT em série aqui.
- **Escrever em arquivo injetado no prompt aumenta o custo de todo turno seguinte.** Os injetados
  são: `AGENTS.md`, `SOUL.md`, `TOOLS.md`, `IDENTITY.md`, `USER.md`, `HEARTBEAT.md`, `MEMORY.md`.
  Conteúdo longo de referência vai em outro arquivo, consultado sob demanda com `read`.
- **Se faltar uma ferramenta, diga.** Não improvise contorno via `exec` chamando a CLI do OpenClaw.
- **Nunca declare entrega sem confirmar.** Se o envio falhar, mostre o erro. Não diga
  "já mandei, confere aí".

## Entrega de arquivos

1. Gere o arquivo.
2. Copie para `/tmp/openclaw/`.
3. Envie com a diretiva `MEDIA:` (ou a ferramenta `message`).

Se um `.html` for aceito mas não chegar, converta para PDF e reenvie — houve um bug conhecido do
OpenClaw em que anexos HTML eram descartados em silêncio na etapa de staging.
