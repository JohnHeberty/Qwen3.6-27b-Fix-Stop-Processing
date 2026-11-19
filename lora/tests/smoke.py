#!/usr/bin/env python3
"""Smoke test da instância LoRA (porta 18021): carrega? serve os dois nomes? o LoRA é aplicado?

  python3 -I lora/tests/smoke.py [--url http://127.0.0.1:18021] [--out lora/results/smoke.json]

Checagens:
  1. /v1/models lista qwen3.8-27b E opencode-adapted (com parent = qwen3.8-27b)
  2. chat simples com cada nome (thinking off) -> conteúdo não vazio, finish_reason=stop
  3. o adaptador MUDA a saída: mesmos prompts, greedy, logprobs; base vs LoRA precisam
     divergir em texto OU em logprob (se forem idênticos, o LoRA não está sendo aplicado
     -- ex.: um caminho fundido do HyperQwen contornando o wrapper de LoRA)
  4. tool call simples com cada nome (parser qwen3_coder) -> tool_calls com nome e args JSON
  5. o thinking do braço de produção continua funcionando no nome base (reasoning não vazio)
Sai com código 1 se algo falhar.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--url", default=C.DEFAULT_URL)
ap.add_argument("--out", default="")
args = ap.parse_args()
URL = C.check_url(args.url)

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)


# 1. modelos
try:
    models = C.list_models(URL)
    check("models: base listado", C.BASE_MODEL in models, ", ".join(models))
    lm = models.get(C.LORA_MODEL)
    check("models: adaptador listado", lm is not None, json.dumps(lm)[:300] if lm else "ausente")
    if lm is not None:
        check("models: parent do adaptador = base", lm.get("parent") == C.BASE_MODEL, f"parent={lm.get('parent')}")
except Exception as e:  # noqa: BLE001
    check("models: GET /v1/models", False, repr(e))
    print("servidor inacessível; abortando")
    sys.exit(1)

# 2. chat simples
for model in (C.BASE_MODEL, C.LORA_MODEL):
    body = {"model": model, "max_tokens": 64, "temperature": 0,
            "messages": [{"role": "user", "content": "Responda só com a palavra: pronto"}], **C.NO_THINK}
    try:
        d, s = C.chat(URL, body, 300)
        c = d["choices"][0]
        txt = (c["message"].get("content") or "").strip()
        check(f"chat {model}", txt and c["finish_reason"] == "stop", f"{txt[:60]!r} finish={c['finish_reason']} {s:.1f}s")
    except Exception as e:  # noqa: BLE001
        check(f"chat {model}", False, repr(e))

# 3. o LoRA altera a distribuição?
PROMPTS = [
    "Write a Python function that returns the n-th Fibonacci number iteratively.",
    "You are in a repository with a failing test in tests/test_parser.py. What is your first step? Answer in one sentence.",
    "Explain in two sentences what a race condition is.",
]
diverged = 0
for p in PROMPTS:
    outs = {}
    for model in (C.BASE_MODEL, C.LORA_MODEL):
        body = {"model": model, "max_tokens": 48, "temperature": 0, "logprobs": True, "top_logprobs": 1,
                "messages": [{"role": "user", "content": p}], **C.NO_THINK}
        try:
            d, _ = C.chat(URL, body, 300)
            ch = d["choices"][0]
            lp = [t["logprob"] for t in ((ch.get("logprobs") or {}).get("content") or [])]
            outs[model] = (ch["message"].get("content") or "", lp)
        except Exception as e:  # noqa: BLE001
            outs[model] = ("", [])
            check(f"logprobs {model}", False, repr(e))
    (tb, lb), (tl, ll) = outs.get(C.BASE_MODEL, ("", [])), outs.get(C.LORA_MODEL, ("", []))
    n = min(len(lb), len(ll))
    # compara só o prefixo em que os textos ainda são iguais token a token não é trivial;
    # basta: texto diferente OU soma de |delta logprob| nos primeiros tokens > 0.05
    dlp = sum(abs(a - b) for a, b in zip(lb[:n], ll[:n])) if n else 0.0
    d_ok = (tb != tl) or dlp > 0.05
    diverged += d_ok
    print(f"  prompt {p[:50]!r}: texto_igual={tb == tl} sum|dlogprob|={dlp:.3f}")
check("adaptador altera a saída (base != LoRA em >= 2 de 3 prompts)", diverged >= 2, f"{diverged}/3 divergiram")

# 4. tool call
TOOLS = [{"type": "function", "function": {
    "name": "get_weather", "description": "Get the current weather for a city",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
for model in (C.BASE_MODEL, C.LORA_MODEL):
    body = {"model": model, "max_tokens": 512, "tools": TOOLS, "tool_choice": "auto",
            "messages": [{"role": "user", "content": "What's the weather in Lisbon right now? Use the tool."}],
            **C.CARD_SAMPLING, **C.NO_THINK}
    try:
        d, s = C.chat(URL, body, 300)
        c = d["choices"][0]
        tcs = c["message"].get("tool_calls") or []
        ok = bool(tcs) and tcs[0]["function"]["name"] == "get_weather" \
            and "lisbon" in json.loads(tcs[0]["function"]["arguments"] or "{}").get("city", "").lower()
        check(f"tool call {model}", ok, f"finish={c['finish_reason']} calls={[t['function'] for t in tcs]} {s:.1f}s")
    except Exception as e:  # noqa: BLE001
        check(f"tool call {model}", False, repr(e))

# 5. thinking da produção no nome base (defaults do servidor)
try:
    body = {"model": C.BASE_MODEL, "max_tokens": 2048,
            "messages": [{"role": "user", "content": "Quanto é 17 * 23? Responda só o número."}]}
    d, s = C.chat(URL, body, 600)
    m = d["choices"][0]["message"]
    check("thinking ON no base (defaults de produção)", (m.get("reasoning") or m.get("reasoning_content")) and "391" in (m.get("content") or ""),
          f"content={(m.get('content') or '')[:40]!r} reasoning_chars={len(m.get('reasoning') or '')}")
except Exception as e:  # noqa: BLE001
    check("thinking ON no base", False, repr(e))

fails = [r for r in results if not r["ok"]]
print(f"\nSMOKE: {len(results) - len(fails)}/{len(results)} PASS")
if args.out:
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(results, open(args.out, "w"), indent=1, ensure_ascii=False)
sys.exit(1 if fails else 0)
