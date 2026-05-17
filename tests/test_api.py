"""
test-api.py — Testa o servidor Qwen3.6 27B rodando no llama.cpp
Instalar dependencia: pip install openai requests
"""

import json
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


BASE_URL = "http://localhost:8000"
PASS = "[OK]"
FAIL = "[FALHOU]"


def separador(titulo: str):
    print(f"\n{'='*50}")
    print(f"  {titulo}")
    print('='*50)


def teste_health():
    separador("Teste 1: Health check")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code == 200:
            body = r.json() if r.text.strip() else {"status": "ok"}
            print(f"{PASS} Servidor respondeu: {body}")
            return True
        else:
            print(f"{FAIL} Status inesperado: {r.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"{FAIL} Servidor nao esta rodando em {BASE_URL}")
        print("       Execute: .\\start-server.ps1")
        return False


def teste_modelos():
    separador("Teste 2: Listar modelos")
    try:
        r = requests.get(f"{BASE_URL}/v1/models", timeout=5)
        modelos = r.json()
        print(f"{PASS} Modelos disponiveis:")
        for m in modelos.get("data", []):
            print(f"       - {m['id']}")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


def teste_chat_basico():
    separador("Teste 3: Chat basico")
    client = OpenAI(base_url=f"{BASE_URL}/v1", api_key="nao-precisa")

    try:
        resp = client.chat.completions.create(
            model="qwen3",
            messages=[
                {"role": "system", "content": "Voce e um assistente util e objetivo."},
                {"role": "user",   "content": "Quanto e 7 vezes 8? Responda so o numero."},
            ],
            max_tokens=64,
            temperature=0.1,
        )
        conteudo = resp.choices[0].message.content.strip()
        print(f"{PASS} Resposta: {conteudo}")
        if "56" in conteudo:
            print("       Calculo correto!")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


def teste_thinking_mode():
    separador("Teste 4: Thinking mode (raciocinio)")
    client = OpenAI(base_url=f"{BASE_URL}/v1", api_key="nao-precisa")

    try:
        resp = client.chat.completions.create(
            model="qwen3",
            messages=[
                {"role": "user", "content": "Se uma loja tem 240 produtos e vende 35% deles, quantos sobraram?"},
            ],
            max_tokens=512,
            temperature=0.6,
            extra_body={"enable_thinking": True},
        )
        conteudo = resp.choices[0].message.content
        print(f"{PASS} Resposta recebida ({len(conteudo)} chars)")

        tem_think = "<think>" in conteudo
        fecha_think = "</think>" in conteudo
        if tem_think and fecha_think:
            print("       Tags <think></think> abertas e fechadas corretamente")
        elif tem_think and not fecha_think:
            print(f"       AVISO: <think> aberto mas nao fechado — template pode estar incorreto")
        else:
            print("       Thinking mode desativado ou sem tag (normal se --no-think)")

        # Mostrar so a resposta final (sem o bloco de raciocinio)
        if "</think>" in conteudo:
            resposta_final = conteudo.split("</think>")[-1].strip()
            print(f"       Resposta final: {resposta_final[:200]}")
        else:
            print(f"       Resposta: {conteudo[:200]}")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


def teste_streaming():
    separador("Teste 5: Streaming")
    client = OpenAI(base_url=f"{BASE_URL}/v1", api_key="nao-precisa")

    try:
        stream = client.chat.completions.create(
            model="qwen3",
            messages=[{"role": "user", "content": "Diga 'streaming funcionando' em 5 palavras."}],
            max_tokens=64,
            temperature=0.1,
            stream=True,
        )

        print(f"{PASS} Tokens chegando: ", end="", flush=True)
        tokens = 0
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                print(delta, end="", flush=True)
                tokens += 1
        print(f"\n       Total de chunks: {tokens}")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


def teste_system_prompt():
    separador("Teste 6: System prompt customizado")
    client = OpenAI(base_url=f"{BASE_URL}/v1", api_key="nao-precisa")

    try:
        resp = client.chat.completions.create(
            model="qwen3",
            messages=[
                {"role": "system", "content": "Voce e um especialista em engenharia de dados. Responda sempre em portugues de forma tecnica e concisa."},
                {"role": "user",   "content": "O que e um pipeline ETL?"},
            ],
            max_tokens=256,
            temperature=0.6,
        )
        conteudo = resp.choices[0].message.content.strip()
        print(f"{PASS} Resposta:")
        print(f"       {conteudo[:300]}")
        return True
    except Exception as e:
        print(f"{FAIL} Erro: {e}")
        return False


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nIniciando testes do servidor Qwen3.6 27B")
    print(f"Endpoint: {BASE_URL}/v1")

    resultados = {
        "Health check":     teste_health(),
        "Listar modelos":   teste_modelos() if True else False,
        "Chat basico":      teste_chat_basico(),
        "Thinking mode":    teste_thinking_mode(),
        "Streaming":        teste_streaming(),
        "System prompt":    teste_system_prompt(),
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
        print("\n  Alguns testes falharam — verifique se o servidor esta rodando.")
        sys.exit(1)
