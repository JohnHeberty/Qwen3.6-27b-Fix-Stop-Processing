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
| `settings.json` | `~/.openclaude/settings.json` (Linux/macOS) · `%USERPROFILE%\.openclaude\settings.json` (Windows) |
| `openclaude.env` | fica onde você quiser; passado com `--provider-env-file` |
| `powershell-profile.ps1` | conteúdo vai no `$PROFILE` do PowerShell (Windows) |
| `bashrc-snippet.sh` | conteúdo vai no `~/.bashrc` ou `~/.zshrc` (Linux/WSL) |

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

## Como mudar o nível de pensamento

Três formas, da mais pontual à mais permanente:

**1. Durante a sessão** — `/effort low` (ou sem argumento, que abre um seletor).
Vale só para a sessão; o OpenClaude salva o nível por modelo.

**2. Ao iniciar** — `openclaude --effort low`.

**3. Permanente** — `effortLevel` no `settings.json` (é o que está configurado aqui).
Escrito automaticamente quando você roda `/effort` com `low`, `medium`, `high` ou `xhigh`.

O `settings.json` leva **um** valor, não a lista — aqui está `"low"`. Para trocar de vez,
edite essa chave; para trocar só agora, use `/effort`. E `auto` não foi escolhido como
default de propósito: medido contra este servidor ele fica praticamente igual ao `low`
(326 vs 304 tokens de raciocínio numa tarefa de código), porque cai no ramo sem
orientação do template. `low` dá o mesmo resultado sendo explícito sobre o que pede.

**Cuidado com os níveis que quebram** (ver tabela abaixo): se você rodar `/effort max`
ou `/effort high` numa sessão, as requisições passam a falhar com HTTP 400 até você
voltar para um valor aceito. Não é erro de config — é incompatibilidade entre a lista do
OpenClaude e o template do Qwen.

Para desligar o pensamento por completo, `effortLevel` não serve — o mais baixo ainda
pensa (~254 tokens). Isso se faz com `enable_thinking:false` no chat template kwargs, o
que o OpenClaude não expõe; teria de ser mudado no servidor (`EXTRA_ARGS` no `.env` do
repo), afetando todos os clientes.

## Modos de permissão (Shift+Tab)

O ciclo padrão do Shift+Tab é `default` (manual) → `acceptEdits` → `plan`. Os modos
"hands-off" são **opcionais** e só entram no ciclo se a sessão for iniciada de um jeito
que os habilite — é por isso que aparecem só `plan` e `acceptEdits` por aqui.

**`auto` não está disponível neste setup.** Ele depende de um classificador que revisa
cada ação no lugar do usuário, e isso exige um modelo suportado pela Anthropic. Com um
provider OpenAI-compatível apontando para o vLLM local, o modo não fica disponível — e,
se algo pedir `auto`, a sessão cai em Manual. Não há como ativá-lo contra este servidor.

**`bypassPermissions` é o que resolve** — e dá para deixar permanente, sem digitar flag
nenhuma. Use um dos arquivos desta pasta:

| sistema | arquivo | onde cola |
|---|---|---|
| Windows | `powershell-profile.ps1` | `$PROFILE` (`notepad $PROFILE`) |
| Linux/WSL | `bashrc-snippet.sh` | `~/.bashrc` ou `~/.zshrc` |

Os dois fazem o mesmo: sobrepõem o nome `openclaude` para que ele já suba com
`--allow-dangerously-skip-permissions`. Resultado — você digita só `openclaude`, a sessão
**começa em `acceptEdits`** (seguro) e o Shift+Tab passa a oferecer o bypass:

```
default → acceptEdits → plan → bypassPermissions
```

No PowerShell é uma *função*, não `Set-Alias`: alias do PowerShell não aceita argumentos
fixos. No bash o `alias` basta.

**Por que não `permissions.defaultMode: "bypassPermissions"` no `settings.json`?**
Essa chave também coloca o modo no ciclo, mas, sendo `defaultMode`, faz **toda** sessão
*começar* nele — sem pedir confirmação para nada desde o primeiro comando. A doc oficial
recomenda o bypass apenas em container ou VM isolada, e este cliente roda na sua máquina
de trabalho. Por isso o `settings.json` fica em `acceptEdits` e a disponibilidade do
bypass vem do perfil do shell: o modo está a um Shift+Tab de distância, mas você escolhe
quando entrar nele.

Se preferir começar já no bypass, o arquivo do PowerShell traz uma variante comentada
(`openclaude-yolo`), e dá para fixar com a chave do `settings.json`.

**Caminho intermediário**, se o que incomoda é só a repetição: pré-aprove comandos
específicos em vez de liberar tudo.

```bash
openclaude --allowed-tools "Bash(git:*)" "Bash(ls:*)" "Bash(cat:*)" Edit
```

## Armadilhas (testadas contra o servidor em 2026-10-15)

**Três dos sete níveis de effort do OpenClaude quebram este servidor.**
O `/effort` do OpenClaude oferece `low medium high xhigh max ultracode auto`, mas o chat
template do Qwen3.8 só conhece `xhigh|medium|low`. Testado valor por valor contra o
servidor em 2026-10-15:

| `/effort` | servidor | raciocínio medido |
|---|---|---|
| `low` | ✅ | 254 tok — **em uso** |
| `auto` | ✅ | 332 tok (cai no ramo default, sem orientação) |
| `medium` | ✅ | não injeta orientação nenhuma |
| `xhigh` | ✅ | 1.500 tok |
| `high` | ❌ HTTP 400 | — |
| `max` | ❌ HTTP 400 | — |
| `ultracode` | ❌ HTTP 400 | — |

```
Unexpected reasoning effort high. Supported types are xhigh (default), medium, and low.
```

Note que `high` **não** é alias de `xhigh` aqui — ele falha. E `medium` passa mas não
tem ramo no template: é "sem orientação", não "esforço médio". Só `low` pede de fato
pensamento curto.

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
