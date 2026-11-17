#!/usr/bin/env python3
"""Mede tok/s de decode do servidor local (código e narrativa), para comparar
entre versões do vLLM. Usa /v1/chat/completions com stream e conta os tokens.

  venv/bin/python scripts/measure_tps.py
"""
import json
import sys
import time
import urllib.request

URL = "http://127.0.0.1:18020/v1/chat/completions"
MODEL = "qwen3.8-27b"

CASES = {
    "codigo": "Escreva uma função Python que faz merge sort, com comentários explicando cada passo. "
              "Depois explique a complexidade.",
    "narrativo": "Escreva um parágrafo narrativo sobre uma viagem de trem pelo interior do Brasil, "
                 "com descrição das paisagens e das pessoas.",
}


def measure(prompt, max_tokens=600):
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    completion = 0
    text = []
    with urllib.request.urlopen(req, timeout=1800) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            usage = chunk.get("usage")
            if usage:
                completion = usage.get("completion_tokens", completion)
            for ch in chunk.get("choices", []):
                delta = ch.get("delta", {}) or {}
                if delta.get("content"):
                    text.append(delta["content"])
    elapsed = time.time() - t0
    return completion, elapsed, "".join(text)


def main():
    out = {}
    for name, prompt in CASES.items():
        completion, elapsed, text = measure(prompt)
        tps = completion / elapsed if elapsed else 0.0
        out[name] = (completion, elapsed, tps)
        print(f"{name}: {completion} tokens em {elapsed:.1f}s = {tps:.1f} tok/s")
        print(f"  inicio: {text[:90]!r}")
    return out


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
