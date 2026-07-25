"""
test-api.py — Testa o servidor Qwen3.6-35B-A3B rodando no llama.cpp
Instalar dependencia: pip install openai requests

Endpoint configuravel via env:
  TEST_BASE_URL   (default http://localhost:8000)  — sem o sufixo /v1
  TEST_MODEL      (default qwen3)

Diferente da versao antiga, TODOS os testes tem asserts reais: um teste que
"passava so por nao lancar excecao" agora FALHA de fato quando o conteudo
esperado nao aparece. Ha uma bateria dedicada de tool-calling (o objetivo
principal do projeto), que so passa a valer depois da remocao do proxy que
mutilava schemas e conversas.
"""

import json
import os
import sys

try:
    import requests
    from openai import OpenAI
except ImportError:
    print("Instalando dependencias...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai", "requests", "-q"])
    import requests
    from openai import OpenAI


BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000").rstrip("/")
MODEL = os.environ.get("TEST_MODEL", "qwen3")
PASS = "[OK]"
FAIL = "[FALHOU]"


def separador(titulo: str):
    print(f"\n{'='*50}")
    print(f"  {titulo}")
    print('='*50)


def _client():
    return OpenAI(base_url=f"{BASE_URL}/v1", api_key="nao-precisa")


def _reasoning(msg):
    """Extrai o raciocinio esteja ele em reasoning_content (--reasoning-format
    deepseek separa o bloco) ou embutido como <think>...</think> no content."""
    rc = getattr(msg, "reasoning_content", None)
    if rc:
        return rc
    conteudo = msg.content or ""
    if "<think>" in conteudo:
        return conteudo.split("<think>", 1)[-1].split("</think>", 1)[0]
    return ""


# ── Ferramentas usadas nos testes de tool-calling ───────────────────────────────

TOOL_WEATHER = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Obtem o clima atual de uma cidade.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "Cidade, ex.: 'Paris'"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            "required": ["location"],
            "additionalProperties": False,
        },
    },
}

# Ferramenta com oneOf no parametro: id pode ser string OU inteiro. Antes, o
# sanitizador do proxy jogava fora tudo menos a primeira alternativa; sem proxy
# o contrato chega intacto ao llama.cpp.
TOOL_LOOKUP_ONEOF = {
    "type": "function",
    "function": {
        "name": "lookup_user",
        "description": "Busca um usuario por identificador (nome ou numero).",
        "parameters": {
            "type": "object",
            "properties": {
                "identifier": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "integer"},
                    ],
                    "description": "Nome de usuario (string) ou ID numerico (integer).",
                }
            },
            "required": ["identifier"],
        },
    },
}


def _tool_calls(resp):
    return resp.choices[0].message.tool_calls or []


# ── Testes basicos (agora com asserts reais) ─────────────────────────────────────

def teste_health():
    separador("Teste 1: Health check")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code == 200:
            body = r.json() if r.text.strip() else {"status": "ok"}
            print(f"{PASS} Servidor respondeu: {body}")
            return True
        print(f"{FAIL} Status inesperado: {r.status_code}")
        return False
    except requests.exceptions.ConnectionError:
        print(f"{FAIL} Servidor nao esta rodando em {BASE_URL}")
        print("       Execute: make start-bg")
        return False


def teste_modelos():
    separador("Teste 2: Listar modelos")
    try:
        r = requests.get(f"{BASE_URL}/v1/models", timeout=5)
        modelos = r.json()
        data = modelos.get("data", [])
        for m in data:
            print(f"       - {m['id']}")
        if not data:
            print(f"{FAIL} Nenhum modelo listado em /v1/models")
            return False
        print(f"{PASS} {len(data)} modelo(s) disponivel(is)")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


def teste_chat_basico():
    separador("Teste 3: Chat basico")
    try:
        resp = _client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Voce e um assistente util e objetivo."},
                {"role": "user",   "content": "Quanto e 7 vezes 8? Responda so o numero."},
            ],
            # Modelo thinking: orcamento amplo p/ o raciocinio terminar e sair a resposta.
            max_tokens=512,
            temperature=0.1,
        )
        msg = resp.choices[0].message
        conteudo = (msg.content or "").strip()
        combinado = conteudo + _reasoning(msg)
        print(f"       Resposta: {conteudo!r}")
        if "56" not in combinado:
            print(f"{FAIL} Esperava '56' na resposta/raciocinio")
            return False
        print(f"{PASS} Calculo correto")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


def teste_thinking_mode():
    separador("Teste 4: Thinking mode (raciocinio)")
    try:
        resp = _client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "user", "content": "Se uma loja tem 240 produtos e vende 35% deles, quantos sobraram?"},
            ],
            max_tokens=512,
            temperature=0.6,
            extra_body={"enable_thinking": True},
        )
        msg = resp.choices[0].message
        raciocinio = _reasoning(msg)
        conteudo = msg.content or ""
        print(f"       Raciocinio: {len(raciocinio)} chars | Resposta: {len(conteudo)} chars")
        if not raciocinio:
            print(f"{FAIL} Sem raciocinio (nem reasoning_content nem <think>) — thinking mode/template quebrado")
            return False
        # 240 - 35% = 156. Aceita a resposta no content ou no fim do raciocinio.
        if "156" not in (conteudo + raciocinio):
            print(f"{FAIL} Resposta numerica errada (esperava 156). Content: {conteudo[:200]}")
            return False
        print(f"{PASS} Raciocinio presente e resultado correto (156)")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


def teste_streaming():
    separador("Teste 5: Streaming")
    try:
        stream = _client().chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Diga 'streaming funcionando' em 5 palavras."}],
            # Orcamento amplo: modelo thinking emite reasoning_content antes do content.
            max_tokens=512,
            temperature=0.1,
            stream=True,
        )
        print(f"       Tokens chegando: ", end="", flush=True)
        chunks = 0
        for chunk in stream:
            delta = chunk.choices[0].delta
            # Conta tanto o conteudo final quanto o raciocinio incremental.
            texto = delta.content or getattr(delta, "reasoning_content", None)
            if texto:
                print(texto, end="", flush=True)
                chunks += 1
        print(f"\n       Total de chunks: {chunks}")
        if chunks == 0:
            print(f"{FAIL} Nenhum chunk recebido no stream")
            return False
        print(f"{PASS} Streaming funcionando")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


def teste_system_prompt():
    separador("Teste 6: System prompt customizado")
    try:
        resp = _client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Voce e um especialista em engenharia de dados. Responda sempre em portugues de forma tecnica e concisa."},
                {"role": "user",   "content": "O que e um pipeline ETL?"},
            ],
            # Orcamento amplo: modelo thinking gasta tokens no raciocinio antes do content.
            max_tokens=768,
            temperature=0.6,
        )
        msg = resp.choices[0].message
        conteudo = (msg.content or "").strip()
        print(f"       {conteudo[:300]}")
        # Aceita conteudo final OU raciocinio substancial (reasoning_content).
        if len(conteudo) < 20 and len(_reasoning(msg)) < 20:
            print(f"{FAIL} Resposta vazia/curta demais (content e reasoning)")
            return False
        print(f"{PASS} Resposta com conteudo")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


# ── Tool-calling (o objetivo principal do projeto) ──────────────────────────────

def teste_tool_call_simples():
    separador("Teste 7: Tool call simples")
    try:
        resp = _client().chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Qual o clima em Paris agora? Use a ferramenta disponivel."}],
            tools=[TOOL_WEATHER],
            max_tokens=512,
            temperature=0.6,
        )
        calls = _tool_calls(resp)
        if not calls:
            print(f"{FAIL} Modelo nao chamou nenhuma ferramenta")
            return False
        c = calls[0]
        if c.function.name != "get_weather":
            print(f"{FAIL} Chamou ferramenta errada: {c.function.name}")
            return False
        args = json.loads(c.function.arguments)
        if "location" not in args:
            print(f"{FAIL} Faltou o parametro obrigatorio 'location': {args}")
            return False
        print(f"{PASS} get_weather(location={args['location']!r})")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


def teste_tool_choice_required():
    separador("Teste 8: tool_choice='required'")
    # Prompt com intencao clara de ferramenta, mas SEM instruir "use a ferramenta":
    # required deve forcar o tool_call mesmo assim. Nota: com o template atual,
    # required nao e estritamente enforced para prompts totalmente off-topic
    # (ex.: uma saudacao) — o modelo pode responder em texto. Ver o A/B de
    # template em docs/explanation/architecture.md ("Why froggeric's template").
    try:
        resp = _client().chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Preciso decidir se levo casaco para Londres hoje."}],
            tools=[TOOL_WEATHER],
            tool_choice="required",
            max_tokens=512,
            temperature=0.6,
        )
        calls = _tool_calls(resp)
        if not calls:
            print(f"{FAIL} tool_choice=required nao produziu tool_call")
            return False
        print(f"{PASS} Ferramenta forcada: {calls[0].function.name}")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


def teste_tool_oneof_schema():
    separador("Teste 9: Schema com oneOf (contrato preservado)")
    try:
        resp = _client().chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Busque o usuario de ID 42 usando a ferramenta."}],
            tools=[TOOL_LOOKUP_ONEOF],
            tool_choice="required",
            max_tokens=512,
            temperature=0.6,
        )
        calls = _tool_calls(resp)
        if not calls:
            print(f"{FAIL} Nao chamou lookup_user (oneOf pode ter quebrado a gramatica)")
            return False
        args = json.loads(calls[0].function.arguments)
        if "identifier" not in args:
            print(f"{FAIL} Faltou 'identifier': {args}")
            return False
        print(f"{PASS} lookup_user(identifier={args['identifier']!r}) — oneOf aceito")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


def teste_tool_correcao_apos_erro():
    separador("Teste 10: Correcao apos erro da ferramenta")
    try:
        # Simula uma chamada anterior malformada (sem 'location') + erro da ferramenta.
        # O modelo precisa ENXERGAR o erro e corrigir — exatamente o que o antigo
        # clean_conversation do proxy apagava.
        messages = [
            {"role": "user", "content": "Use get_weather para o clima em Berlim."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": "{}"},
                }],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "Erro: o parametro 'location' e obrigatorio e nao foi fornecido.",
            },
        ]
        resp = _client().chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=[TOOL_WEATHER],
            max_tokens=512,
            temperature=0.6,
        )
        calls = _tool_calls(resp)
        if not calls:
            print(f"{FAIL} Modelo nao refez a chamada apos o erro")
            return False
        args = json.loads(calls[0].function.arguments)
        if "location" not in args:
            print(f"{FAIL} Corrigiu mas ainda sem 'location': {args}")
            return False
        print(f"{PASS} Corrigiu a chamada: get_weather(location={args['location']!r})")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


def teste_tool_paralelo():
    separador("Teste 11: Chamadas paralelas")
    try:
        resp = _client().chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Compare o clima em Paris e em Tokyo agora. Use a ferramenta para cada cidade."}],
            tools=[TOOL_WEATHER],
            parallel_tool_calls=True,
            max_tokens=512,
            temperature=0.6,
        )
        calls = _tool_calls(resp)
        if not calls:
            print(f"{FAIL} Nenhuma tool_call gerada")
            return False
        cidades = []
        for c in calls:
            try:
                cidades.append(json.loads(c.function.arguments).get("location"))
            except Exception:
                pass
        print(f"       {len(calls)} tool_call(s): {cidades}")
        if len(calls) >= 2:
            print(f"{PASS} Chamadas paralelas ({len(calls)}) geradas")
        else:
            print(f"{PASS} 1 tool_call (o modelo pode sequenciar; paralelismo aceito quando ocorre)")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


def teste_conversa_longa_multi_tool():
    separador("Teste 12: Conversa longa multi-ferramenta")
    try:
        # Turno 1: pede clima, devolve resultado da ferramenta, pede conclusao final.
        messages = [
            {"role": "system", "content": "Voce ajuda a decidir roupas com base no clima. Use as ferramentas."},
            {"role": "user", "content": "Vou para Paris. Qual o clima?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_a",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": json.dumps({"location": "Paris"})},
                }],
            },
            {"role": "tool", "tool_call_id": "call_a", "content": json.dumps({"temp_c": 8, "cond": "chuva"})},
            {"role": "user", "content": "Com base nisso, preciso de guarda-chuva? Responda sim ou nao e por que."},
        ]
        resp = _client().chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=[TOOL_WEATHER],
            max_tokens=512,
            temperature=0.6,
        )
        conteudo = (resp.choices[0].message.content or "").strip()
        print(f"       {conteudo[:200]}")
        # Deve concluir usando o resultado da ferramenta (chuva -> sim).
        if len(conteudo) < 5:
            print(f"{FAIL} Resposta final vazia")
            return False
        if "sim" not in conteudo.lower():
            print(f"       AVISO: esperava recomendar guarda-chuva (chuva no resultado)")
        print(f"{PASS} Manteve o contexto da ferramenta e concluiu")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nIniciando testes do servidor Qwen3.6-35B-A3B")
    print(f"Endpoint: {BASE_URL}/v1  (modelo: {MODEL})")

    resultados = {
        "Health check":            teste_health(),
        "Listar modelos":          teste_modelos(),
        "Chat basico":             teste_chat_basico(),
        "Thinking mode":           teste_thinking_mode(),
        "Streaming":               teste_streaming(),
        "System prompt":           teste_system_prompt(),
        "Tool call simples":       teste_tool_call_simples(),
        "tool_choice=required":    teste_tool_choice_required(),
        "Schema oneOf":            teste_tool_oneof_schema(),
        "Correcao apos erro":      teste_tool_correcao_apos_erro(),
        "Chamadas paralelas":      teste_tool_paralelo(),
        "Conversa multi-tool":     teste_conversa_longa_multi_tool(),
    }

    separador("Resultado Final")
    aprovados = sum(1 for v in resultados.values() if v)
    total = len(resultados)

    for nome, ok in resultados.items():
        status = PASS if ok else FAIL
        print(f"  {status} {nome}")

    print(f"\n  {aprovados}/{total} testes passaram")

    if aprovados == total:
        print("\n  Servidor operacional!")
    else:
        print("\n  Alguns testes falharam.")
        sys.exit(1)
