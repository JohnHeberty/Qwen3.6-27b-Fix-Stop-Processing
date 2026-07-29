Para esse problema, **aumentar `num_experts_per_tok` não é a solução**. Quando o modelo diz “vou consultar a ferramenta” mas não produz `tool_calls`, normalmente o problema está no **template, parser, modo de geração ou `tool_choice`**, não na quantidade de parâmetros ativos.

## Configurações que mais ajudam

| Ajuste                             | Efeito                                                    |
| ---------------------------------- | --------------------------------------------------------- |
| `tool_choice="required"`           | Obriga o modelo a produzir alguma chamada                 |
| Função específica em `tool_choice` | Obriga a chamar exatamente aquela função                  |
| `strict: true`                     | Restringe os argumentos ao JSON Schema                    |
| Parser `qwen3_coder`               | Converte a saída especial do Qwen em `message.tool_calls` |
| `enable_thinking=False`            | Reduz a tendência de narrar/raciocinar antes da chamada   |
| Temperatura baixa                  | Torna a escolha e os argumentos mais determinísticos      |
| Schema simples e claro             | Facilita muito para modelos pequenos                      |

Para o **Qwen3.5-35B-A3B**, a configuração oficial para vLLM inclui obrigatoriamente o parser `qwen3_coder` e a ativação da escolha automática de ferramentas. ([Hugging Face][1])

```bash
vllm serve Qwen/Qwen3.5-35B-A3B \
  --tensor-parallel-size 8 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3
```

Sem `--tool-call-parser qwen3_coder`, pode acontecer exatamente isto:

```text
"Vou consultar o pedido agora..."
```

em `message.content`, em vez de:

```json
{
  "tool_calls": [
    {
      "function": {
        "name": "consultar_pedido",
        "arguments": "{\"numero\":\"12345\"}"
      }
    }
  ]
}
```

## O parâmetro mais importante: `tool_choice`

### Quando obrigatoriamente precisa usar uma ferramenta

```python
response = client.chat.completions.create(
    model="Qwen/Qwen3.5-35B-A3B",
    messages=messages,
    tools=tools,
    tool_choice="required",
    temperature=0.1,
)
```

No vLLM, `tool_choice="required"` garante que será produzida pelo menos uma chamada estruturada e ativa geração restringida pelo schema. ([vLLM][2])

O ponto negativo é que ele chamará alguma ferramenta mesmo quando nenhuma for necessária. Portanto, isso funciona melhor quando sua aplicação já sabe que aquela etapa exige uma função.

### Quando você já sabe qual função deve ser usada

Essa é a configuração mais confiável:

```python
tool_choice={
    "type": "function",
    "function": {
        "name": "consultar_pedido"
    }
}
```

Exemplo completo:

```python
response = client.chat.completions.create(
    model="Qwen/Qwen3.5-35B-A3B",
    messages=[
        {
            "role": "system",
            "content": (
                "Use a ferramenta indicada. "
                "Não descreva a chamada e não simule resultados."
            ),
        },
        {
            "role": "user",
            "content": "Consulte o pedido 12345",
        },
    ],
    tools=tools,
    tool_choice={
        "type": "function",
        "function": {"name": "consultar_pedido"},
    },
    temperature=0.0,
)
```

No named function calling, o vLLM usa structured outputs para garantir uma chamada analisável e compatível com o JSON Schema. Isso garante a estrutura, embora não garanta que o modelo tenha escolhido semanticamente os melhores valores. ([vLLM][2])

## Use `strict: true`

Configure sua ferramenta assim:

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "consultar_pedido",
            "description": (
                "Consulta no sistema o estado atual de um pedido. "
                "Use quando o usuário pedir informações sobre um pedido existente."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "numero": {
                        "type": "string",
                        "description": "Número exato do pedido informado pelo usuário",
                    }
                },
                "required": ["numero"],
                "additionalProperties": False,
            },
        },
    }
]
```

Para `tool_choice="auto"`, o `strict: true` permite que o vLLM restrinja os argumentos gerados ao schema. A documentação recomenda também `additionalProperties: false`, todos os campos marcados como obrigatórios e campos opcionais representados com `null`. ([vLLM][2])

Isso resolve principalmente:

* JSON inválido;
* campo escrito com nome errado;
* argumento ausente;
* argumento extra;
* número retornado como texto narrativo fora da chamada.

Mas `strict` não obriga o modelo a decidir chamar uma função. Para isso, use `required` ou função nomeada.

## Desative o thinking para chamadas simples

O Qwen3.5-35B-A3B entra em thinking por padrão. Para tarefas simples de roteamento, eu testaria:

```python
response = client.chat.completions.create(
    model="Qwen/Qwen3.5-35B-A3B",
    messages=messages,
    tools=tools,
    tool_choice="auto",
    temperature=0.1,
    extra_body={
        "chat_template_kwargs": {
            "enable_thinking": False
        }
    },
)
```

O próprio Qwen disponibiliza `enable_thinking=False` para produzir respostas diretas. A documentação também alerta que templates ReAct baseados em stopwords podem se comportar mal em modelos de raciocínio, porque o modelo pode emitir essas marcações dentro do pensamento. ([Hugging Face][1])

Minha recomendação prática:

* **chamada simples:** thinking desativado;
* **função com muitos argumentos e decisões:** testar thinking ativado e desativado;
* **modelo narrando em vez de chamar:** começar com thinking desativado.

## Parâmetros de amostragem

Para function calling eu começaria assim:

```python
temperature=0.0
top_p=1.0
presence_penalty=0.0
frequency_penalty=0.0
```

Ou, caso `temperature=0` cause algum problema no servidor:

```python
temperature=0.1
top_p=0.9
```

Não é um parâmetro que aumenta a inteligência. Ele reduz variação. Em chamadas estruturadas, normalmente interessa que o modelo repita consistentemente o formato correto, não que explore formas criativas de responder.

Eu evitaria inicialmente:

```python
temperature=0.7
presence_penalty=1.5
```

porque penalidades altas podem incentivar o modelo a evitar tokens ou estruturas que ele precisaria repetir no JSON. Isso deve ser validado no seu conjunto de funções, pois o Qwen recomenda parâmetros mais altos para conversação geral, não necessariamente para máxima determinismo em tool calling. ([Hugging Face][1])

## O prompt também precisa impedir a narração

Um system prompt simples:

```text
Você é um controlador de ferramentas.

Quando uma ferramenta puder atender à solicitação:
- produza imediatamente a chamada estruturada;
- não diga que irá chamar a ferramenta;
- não escreva a chamada em texto comum;
- não invente o resultado da ferramenta;
- aguarde o resultado antes de responder ao usuário.

Quando faltar um argumento obrigatório, pergunte somente pelo argumento ausente.
```

Evite prompts enormes explicando várias vezes o protocolo. Para modelos pequenos, instruções curtas e exemplos concretos geralmente funcionam melhor.

## Reduza o número de ferramentas disponíveis

Um modelo pequeno terá mais dificuldade escolhendo entre:

```text
consultar_pedido
buscar_pedido
ver_pedido
obter_status_pedido
consultar_status
```

Prefira uma função clara:

```text
consultar_pedido
```

com descrição precisa.

Se você possui 50 ferramentas, faça um roteamento anterior e entregue ao modelo apenas as 3–8 mais relevantes. A documentação do vLLM deixa claro que a qualidade também depende das definições das ferramentas e do contexto fornecido pela aplicação. ([vLLM][2])

## Quando o problema exige fine-tuning

Se modelos pequenos continuam narrando mesmo com parser, template, `required` e schema estrito, o ajuste que realmente tende a mudar a capacidade é **SFT/LoRA com exemplos de function calling**.

Os dados precisam conter exemplos como:

```text
Usuário: Consulte o pedido 123.
Assistente: <tool_call estruturado>

Ferramenta: {"status":"enviado"}
Assistente: O pedido 123 foi enviado.
```

Também devem existir exemplos negativos:

```text
Usuário: Explique como funciona a entrega.
Assistente: resposta normal, sem ferramenta
```

Estudos com modelos pequenos encontraram melhora de zero-shot para few-shot e os melhores resultados após fine-tuning, embora aderir ao formato ainda seja uma das principais dificuldades desses modelos. ([arXiv][3])

## Configuração que eu usaria primeiro

```python
response = client.chat.completions.create(
    model="Qwen/Qwen3.5-35B-A3B",
    messages=messages,
    tools=tools,
    tool_choice="required",  # depois testar "auto"
    temperature=0.0,
    top_p=1.0,
    presence_penalty=0.0,
    frequency_penalty=0.0,
    extra_body={
        "chat_template_kwargs": {
            "enable_thinking": False
        }
    },
)
```

Servidor:

```bash
vllm serve Qwen/Qwen3.5-35B-A3B \
  --tensor-parallel-size 8 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3
```

A ordem de impacto mais provável é:

```text
parser/template correto
→ tool_choice required ou função nomeada
→ strict JSON Schema
→ thinking desativado
→ temperatura baixa
→ descrições melhores e menos ferramentas
→ few-shot
→ LoRA/SFT
```

Alterar o `top-k` dos experts ficaria no final da lista e provavelmente não corrigiria esse comportamento.

[1]: https://huggingface.co/Qwen/Qwen3.5-35B-A3B/blob/main/README.md "README.md · Qwen/Qwen3.5-35B-A3B at main"
[2]: https://docs.vllm.ai/en/latest/features/tool_calling/ "Tool Calling - vLLM"
[3]: https://arxiv.org/html/2504.19277 "Small Models, Big Tasks: An Exploratory Empirical Study on Small Language Models for Function Calling"
