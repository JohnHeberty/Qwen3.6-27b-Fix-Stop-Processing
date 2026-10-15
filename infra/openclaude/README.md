# OpenClaude → Qwen3.8-27B local

Config do [OpenClaude](https://github.com/Twigpine/openclaude) (CLI de coding agent,
`npm i -g @gitlawb/openclaude`) apontando para o servidor vLLM deste repo em
`http://192.168.1.139:18020/v1`.

> **Não confundir com o [OpenClaw](../openclaw/)**, que fica na pasta vizinha.
> São produtos diferentes, de autores diferentes: OpenClaw é uma plataforma de agente
> com gateway, canais (Telegram) e plugins; OpenClaude é um CLI de código no estilo
> Claude Code. Os formatos de config não são compatíveis entre si.

## Arquivos

| arquivo | destino |
|---|---|
| `openclaude.env` | fica onde você quiser; passado com `--provider-env-file` |
| `settings.json` | `~/.openclaude/settings.json` (Linux/macOS) · `%USERPROFILE%\.openclaude\settings.json` (Windows) |

## Como usar

O OpenClaude **não lê `.env` do projeto automaticamente**. Duas formas:

```bash
# 1) arquivo de env explícito (recomendado — não suja o ambiente)
openclaude --provider-env-file /root/qwen3/infra/openclaude/openclaude.env

# 2) exportando antes de chamar
set -a; . /root/qwen3/infra/openclaude/openclaude.env; set +a
openclaude
```

No Windows (PowerShell), copie `settings.json` para
`%USERPROFILE%\.openclaude\settings.json` — o bloco `env` dele já carrega as mesmas
variáveis, então o `--provider-env-file` fica opcional.

Terceira alternativa, sem arquivo nenhum: rode `/provider` dentro do OpenClaude e
preencha base URL, modelo e uma chave qualquer. Ele salva um perfil em
`.openclaude-profile.json`.

## Armadilhas (testadas contra o servidor em 2026-10-15)

**`effortLevel` tem que ser `low`, `medium` ou `high` — nunca `max`.**
O OpenClaude aceita `low|medium|high|xhigh|max`, mas o chat template do Qwen3.8 só
conhece `xhigh|medium|low` (`high` é alias de `xhigh`). Mandar `max` devolve **HTTP 400**:

```
Unexpected reasoning effort max. Supported types are xhigh (default), medium, and low.
```

E atenção: `medium` **não injeta orientação nenhuma** no template — não existe ramo
`medium` nele. Só `low` pede de fato pensamento curto.

**O cliente sobrescreve o `reasoning_effort` do servidor.** O `.env` do repo força
`reasoning_effort:low` via `--default-chat-template-kwargs`, mas o que o cliente manda
vence. Medido num prompt de design de sistema:

| effort enviado | tokens de raciocínio |
|---|---|
| `low` | 321 |
| `xhigh` | 1.920 |

Por isso `effortLevel: "low"` no `settings.json` não é redundante — sem ele você perde
o ajuste que o servidor tenta aplicar.

**Aspas simples nos JSON maps do `.env`.** `CLAUDE_CODE_OPENAI_CONTEXT_WINDOWS` e
`CLAUDE_CODE_OPENAI_MAX_OUTPUT_TOKENS` levam JSON. Sem aspas simples em volta, o shell
remove as aspas duplas internas ao exportar e o cliente recebe algo que não parseia.

**`OPENAI_API_KEY` é obrigatória mesmo sem autenticação.** O servidor roda sem auth e
ignora o valor, mas o cliente exige a variável presente.

## Contexto e saída

- Servidor: `max_model_len=142080`
- Declarado aqui: `contextWindow: 140000` (2.080 de margem), `maxOutputTokens: 32768`

Mesmos números dos outros consumidores (`../opencode/`, `../litellm/`, `../openclaw/`).

## Não verificado

O OpenClaude **não está instalado nesta máquina**, então nada aqui foi executado pelo
cliente real — só a conectividade e o comportamento do servidor foram testados com
`curl` usando exatamente estas variáveis. As chaves de `settings.json` vêm da
[doc oficial](https://openclaude.gitlawb.com/docs/configuration/); `agentModels` e
`agentRouting` existem e permitem roteamento por agente, mas a doc não publica o schema
dos campos, então não foram usados aqui. Se precisar deles, confira na sua versão.
