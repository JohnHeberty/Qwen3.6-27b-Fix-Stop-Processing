# HIPÓTESE 08 — Gramática enorme do array de ~26 tools

**Status:** NÃO INVESTIGADO · **Suspeita:** BAIXA

## Hipótese
Com muitas ferramentas (o caso era gerar um `TOOLS.md` com ~26 tools), o llama-server compila uma
**gramática de união** grande a partir de todo o array de schemas. Schemas profundos (`anyOf`,
`additionalProperties`, muitos props) podem gerar milhares de regras. Se isso estourar limites ou
custar demais, a chamada de ferramenta pode falhar ou degradar.

## O que explicaria
- A falha ter aparecido justamente num contexto com muitas tools declaradas.

## Evidência a favor
- `llama-cpp-grammar-patches.patch`: subiu `MAX_REPETITION_THRESHOLD` de 2000→100000 justamente
  porque schemas de tools estouravam o limite (quebrava tool calling — ver notas em
  `data/temp/opencode_session_mtp_export.md` ~linhas 11098–11109, issue upstream #20867).
- `docs/explanation/architecture.md` linha 63 alerta: schema patológico pode gerar "gramática enorme
  com alto custo de memória/compilação".

## Evidência contra
- O patch já eleva o limite para 100000; as notas medem "<2ms de compilação".
- `server.log` **não** tem erros de `grammar` (grep=0).
- 26 tools "normais" provavelmente ficam bem abaixo do limite.

## Como investigar
1. Reproduzir com o array real de ~26 tools do MoltBot e medir tempo/memória de compilação da
   gramática e se a chamada retorna `tool_calls`.
2. Testar com `tool_choice="required"` + array grande para forçar o caminho da gramática.
3. Se suspeito, reduzir o limite para um intermediário (ex.: 20000) e ver se algum schema real
   volta a estourar (isso revelaria o schema problemático).

## Confirmação / refutação
- **Confirma** se, com o array grande, a compilação da gramática falha/trava ou a chamada não
  produz `tool_calls`, e melhora ao reduzir/particionar as tools.
- **Refuta** se o mesmo array funciona de forma estável isoladamente.

## Correção provável (se confirmada)
- Simplificar/particionar schemas; limitar tools por request; ajustar o limite de repetição para um
  valor que caiba os schemas reais sem permitir explosão.
