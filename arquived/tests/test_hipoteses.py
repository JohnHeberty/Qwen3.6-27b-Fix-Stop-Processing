"""
test_hipoteses.py — Testa as hipóteses pendentes do server-side
Direto no llama-server (:8000), sem OpenClaw.

H01: Overflow de contexto (prompt > ctx_size retorna erro)
H03: Thinking consome budget antes do tool_call (finish=length sem tool_calls)
H05: Parse de XML com tool_call args complexos
H08: Grammar com muitas tools (~26)

Uso:
  python3 tests/test_hipoteses.py              # roda todos
  python3 tests/test_hipoteses.py --only H01   # só H01
  python3 tests/test_hipoteses.py --only H03   # só H03
  python3 tests/test_hipoteses.py --only H05   # só H05
  python3 tests/test_hipoteses.py --only H08   # só H08
"""

import json
import os
import sys
import time
import hashlib
from uuid import uuid4

try:
    import requests
    from openai import OpenAI
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai", "requests", "-q"])
    import requests
    from openai import OpenAI

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000").rstrip("/")
MODEL = os.environ.get("TEST_MODEL", "qwen3")
PASS = "[OK]"
FAIL = "[FALHOU]"


def separador(titulo):
    print(f"\n{'='*60}")
    print(f"  {titulo}")
    print(f"{'='*60}")


def _client():
    return OpenAI(base_url=f"{BASE_URL}/v1", api_key="nao-precisa")


# ═══════════════════════════════════════════════════════════════════════════════
# H01 — Overflow de contexto
# ═══════════════════════════════════════════════════════════════════════════════
def teste_H01_overflow():
    separador("H01: Overflow de contexto (prompt > ctx_size)")
    client = _client()

    # Gera prompt que excede 106k tokens (~4 chars/token, precisa de ~420k chars)
    # Usa ~110k tokens pra garantir overflow
    bloco_grande = "Responda apenas: OK.\n" * 60000  # ~120k tokens

    try:
        t0 = time.time()
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "user", "content": bloco_grande}
            ],
            max_tokens=32,
            temperature=0.0,
        )
        elapsed = time.time() - t0

        # Se chegou aqui, NÃO estourou — o servidor aceitou o prompt
        usage = getattr(resp, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        print(f"  Prompt tokens: {prompt_tokens}")
        print(f"  Tempo: {elapsed:.1f}s")

        if prompt_tokens > 106496:
            print(f"{FAIL} Servidor aceitou {prompt_tokens} tokens sem erro — deveria ter rejeitado")
            return False

        # Prompt grande mas dentro do limite — aceitar
        print(f"{PASS} Prompt de {prompt_tokens} tokens processado OK (dentro do limite)")
        return True

    except Exception as e:
        erro = str(e)
        if "exceeds" in erro or "context" in erro or "143" in erro or "179" in erro:
            print(f"{PASS} Overflow detectado corretamente: {erro[:120]}")
            return True
        # Connection error, timeout etc
        if "Connection" in erro or "timeout" in erro.lower():
            print(f"{FAIL} Conexão falhou: {erro[:120]}")
            return False
        print(f"{FAIL} Erro inesperado: {erro[:200]}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# H03 — Thinking consome budget antes do tool_call
# ═══════════════════════════════════════════════════════════════════════════════
def teste_H03_thinking_budget():
    separador("H03: Thinking não consome budget antes do tool_call")
    client = _client()

    tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Obtém o clima de uma cidade.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["location"],
            },
        },
    }

    # Pergunta que FORÇA o uso de tool
    prompt = "Qual o tempo em Paris agora? Use a ferramenta get_weather."

    resultados = []
    n_execucoes = 3  # roda 3x pra pegar intermitência

    for i in range(n_execucoes):
        try:
            t0 = time.time()
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                tools=[tool],
                tool_choice="auto",
                max_tokens=8192,
                temperature=0.6,
            )
            elapsed = time.time() - t0

            choice = resp.choices[0]
            finish = choice.finish_reason
            tc = choice.message.tool_calls or []
            content = choice.message.content or ""
            reasoning = getattr(choice.message, "reasoning_content", None) or ""

            usage = getattr(resp, "usage", None)
            completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

            tem_thinking = bool(reasoning) or ("<think>" in content)
            tem_tool_call = bool(tc)

            resultado = {
                "execucao": i + 1,
                "finish_reason": finish,
                "completion_tokens": completion_tokens,
                "tem_thinking": tem_thinking,
                "tem_tool_call": tem_tool_call,
                "elapsed": elapsed,
                "content_len": len(content),
            }
            resultados.append(resultado)

            print(f"  Exec {i+1}: finish={finish}, tokens={completion_tokens}, "
                  f"thinking={'SIM' if tem_thinking else 'NAO'}, "
                  f"tool_call={'SIM' if tem_tool_call else 'NAO'}, "
                  f"tempo={elapsed:.1f}s")

        except Exception as e:
            print(f"  Exec {i+1}: ERRO — {str(e)[:150]}")
            resultados.append({"execucao": i + 1, "erro": str(e)[:150]})

    # Análise
    print(f"\n  Resumo ({len(resultados)} execuções):")

    falhas_thinking = [r for r in resultados if r.get("finish_reason") == "length"
                       and r.get("tem_thinking") and not r.get("tem_tool_call")]

    if falhas_thinking:
        print(f"{FAIL} {len(falhas_thinking)}/{len(resultados)} execuções: thinking consumiu budget"
              f" antes do tool_call (finish=length sem tool_calls)")
        return False

    # Verificar que pelo menos uma vez teve tool_call
    com_tool_call = [r for r in resultados if r.get("tem_tool_call")]
    if not com_tool_call:
        print(f"{FAIL} Nenhuma execução gerou tool_call — modelo pode estar ignorando tools")
        return False

    print(f"{PASS} Thinking não consumiu budget — {len(com_tool_call)}/{len(resultados)} "
          f"execuções geraram tool_call com sucesso")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# H05 — Parse de XML com tool_call args complexos
# ═══════════════════════════════════════════════════════════════════════════════
def teste_H05_tool_parse():
    separador("H05: Parse de tool_call com args complexos")
    client = _client()

    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_files",
                "description": "Busca arquivos no projeto por padrão.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob pattern, ex: src/**/*.py"},
                        "include": {"type": "string", "description": "Extensão para filtrar"},
                        "max_results": {"type": "integer", "default": 10},
                    },
                    "required": ["pattern"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Lê o conteúdo de um arquivo.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "offset": {"type": "integer"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_issue",
                "description": "Cria uma issue no GitHub.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "labels": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "milestone": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "integer"},
                            ],
                        },
                    },
                    "required": ["title"],
                },
            },
        },
    ]

    prompt = ("Busque todos os arquivos .py em src/, depois leia o primeiro resultado "
              "com offset 0 e limit 50. Use search_files e read_file.")

    try:
        t0 = time.time()
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            tools=tools,
            tool_choice="auto",
            max_tokens=4096,
            temperature=0.6,
        )
        elapsed = time.time() - t0

        choice = resp.choices[0]
        tc = choice.message.tool_calls or []

        print(f"  Tempo: {elapsed:.1f}s")
        print(f"  Tool calls gerados: {len(tc)}")

        for i, t in enumerate(tc):
            fname = t.function.name
            try:
                args = json.loads(t.function.arguments)
                print(f"    [{i+1}] {fname}({json.dumps(args, ensure_ascii=False)[:120]})")
            except json.JSONDecodeError as e:
                print(f"    [{i+1}] {fname}(INVALID JSON: {e})")
                print(f"        Raw: {t.function.arguments[:200]}")
                print(f"{FAIL} Parse de JSON falhou para {fname}")
                return False

        if not tc:
            print(f"  Finish reason: {choice.finish_reason}")
            print(f"{FAIL} Nenhum tool_call gerado — modelo ignorou as tools")
            return False

        print(f"{PASS} {len(tc)} tool_calls parseados corretamente")
        return True

    except Exception as e:
        print(f"{FAIL} Erro: {str(e)[:200]}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# H08 — Grammar com muitas tools (~26)
# ═══════════════════════════════════════════════════════════════════════════════
def teste_H08_grammar_muitas_tools():
    separador("H08: Grammar com 26 tools (array realista)")
    client = _client()

    # Gera 26 tools realistas (baseado no array real do projeto)
    nomes_tools = [
        ("search_files", "Busca arquivos por padrão glob"),
        ("read_file", "Lê conteúdo de um arquivo"),
        ("write_file", "Escreve conteúdo em um arquivo"),
        ("edit_file", "Edita um arquivo com replace"),
        ("list_directory", "Lista diretórios"),
        ("run_command", "Executa comando shell"),
        ("grep_search", "Busca em conteúdo de arquivos"),
        ("git_status", "Mostra status do git"),
        ("git_diff", "Mostra diff do git"),
        ("git_commit", "Cria commit no git"),
        ("git_push", "Push para remoto"),
        ("create_issue", "Cria issue no GitHub"),
        ("list_issues", "Lista issues do GitHub"),
        ("get_weather", "Obtém clima de uma cidade"),
        ("web_search", "Pesquisa na web"),
        ("web_fetch", "Busca conteúdo de URL"),
        ("create_memory", "Cria entrada na memória"),
        ("search_memory", "Busca na memória"),
        ("read_memory", "Lê arquivo de memória"),
        ("update_memory", "Atualiza memória"),
        ("delete_memory", "Deleta entrada de memória"),
        ("list_memory", "Lista memórias salvas"),
        ("set_config", "Define configuração"),
        ("get_config", "Lê configuração"),
        ("notify_user", "Notifica o usuário"),
        ("ask_user", "Pergunta ao usuário"),
    ]

    tools = []
    for nome, desc in nomes_tools:
        tools.append({
            "type": "function",
            "function": {
                "name": nome,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
            },
        })

    prompt = "Use git_status para verificar o estado do repositório."

    try:
        t0 = time.time()
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            tools=tools,
            tool_choice="auto",
            max_tokens=2048,
            temperature=0.6,
        )
        elapsed = time.time() - t0

        choice = resp.choices[0]
        tc = choice.message.tool_calls or []
        finish = choice.finish_reason
        content = choice.message.content or ""

        usage = getattr(resp, "usage", None)
        completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

        print(f"  Tools enviadas: {len(tools)}")
        print(f"  Tempo: {elapsed:.1f}s")
        print(f"  Finish: {finish}")
        print(f"  Completion tokens: {completion_tokens}")

        if tc:
            for t in tc:
                print(f"    Tool call: {t.function.name}({t.function.arguments[:80]})")
            print(f"{PASS} Grammar aceitou {len(tools)} tools — {len(tc)} tool_calls gerados")
            return True

        if finish == "stop" and content:
            print(f"  Conteúdo: {content[:150]}")
            # Resposta textual sem tool_call não é erro de grammar
            print(f"{PASS} Resposta textual (sem tool_call) — grammar OK (modelo escolheu não usar tool)")
            return True

        if finish == "length":
            print(f"{FAIL} Finish=length com 26 tools — grammar pode estar limitando")
            return False

        print(f"{FAIL} Resposta inesperada: finish={finish}, tool_calls={len(tc)}")
        return False

    except Exception as e:
        erro = str(e)
        if "grammar" in erro.lower() or "parse" in erro.lower():
            print(f"{FAIL} Erro de grammar: {erro[:200]}")
            return False
        if "exceeds" in erro or "context" in erro:
            print(f"{FAIL} Contexto estourou com 26 tools: {erro[:200]}")
            return False
        print(f"{FAIL} Erro: {erro[:200]}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
TESTES = {
    "H01": teste_H01_overflow,
    "H03": teste_H03_thinking_budget,
    "H05": teste_H05_tool_parse,
    "H08": teste_H08_grammar_muitas_tools,
}


def main():
    args = sys.argv[1:]
    if "--only" in args:
        idx = args.index("--only")
        apenas = [args[idx + 1].upper()]
    else:
        apenas = list(TESTES.keys())

    print(f"Testando hipóteses no servidor: {BASE_URL}")
    print(f"Modelo: {MODEL}")
    print(f"Testes: {', '.join(apenas)}")

    resultados = {}
    for nome in apenas:
        if nome not in TESTES:
            print(f"Teste desconhecido: {nome}")
            continue
        try:
            resultados[nome] = TESTES[nome]()
        except Exception as e:
            print(f"{FAIL} {nome} explodiu: {e}")
            resultados[nome] = False

    # Resumo
    separador("RESUMO")
    total = len(resultados)
    ok = sum(1 for v in resultados.values() if v)
    falhou = total - ok

    for nome, resultado in resultados.items():
        status = PASS if resultado else FAIL
        print(f"  {nome}: {status}")

    print(f"\n  Total: {ok}/{total} passaram, {falhou} falharam")
    return 0 if falhou == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
