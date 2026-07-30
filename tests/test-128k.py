#!/usr/bin/env python3
"""Testa o modelo Ornith com ~127k tokens de contexto (pdf_pages)."""
import json, glob, os, sys
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

pages = sorted(glob.glob(os.path.join(PROJECT_ROOT, "data/pdf_pages/*.md")))
content = ""
for p in pages:
    with open(p) as f:
        content += f.read() + "\n\n"
content = content[:500000]

payload = json.dumps({
    "model": "ornith",
    "messages": [
        {"role": "user", "content": f"Resuma o conteudo abaixo em 500 palavras:\n\n'''\n{content}\n'''"}
    ],
    "max_tokens": 2048,
    "temperature": 0.6,
    "stream": False
})

print(f"Payload: {len(content)} chars (~{len(content)//4} tokens)")
print(f"JSON size: {len(payload)} bytes")
print(f"Enviando para http://127.0.0.1:8080/v1/chat/completions ...")

req = urllib.request.Request(
    "http://127.0.0.1:8080/v1/chat/completions",
    data=payload.encode(),
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(req, timeout=600) as resp:
        result = json.loads(resp.read())
    msg = result["choices"][0]["message"]
    usage = result.get("usage", {})
    print(f"\n=== Resposta ===")
    print(f"Content: {msg.get('content', '(vazio)')}")
    print(f"\nReasoning: {msg.get('reasoning_content', '(nenhum)')}")
    print(f"\nUsage: prompt={usage.get('prompt_tokens')}, completion={usage.get('completion_tokens')}, total={usage.get('total_tokens')}")
except Exception as e:
    print(f"Erro: {e}")
    sys.exit(1)
