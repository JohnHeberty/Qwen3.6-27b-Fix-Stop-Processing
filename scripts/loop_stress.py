#!/usr/bin/env python3
"""Mede a propensão do servidor a travar em loop numa tarefa de agente longa.

Reproduz as condições em que o Qwen3.8 colapsou em sessões do OpenCode: ~41k tokens de
contexto (arquivos do launcher), tarefa "planeje e escreva o arquivo de teste" com uma
ferramenta write_file, effort low e TODAS as proteções desligadas no request
(presence_penalty 0, repetition_detection off, thinking_token_budget 60000).

Classifica cada amostra: chamou a ferramenta, loop de texto (linhas finais repetidas),
colapso numérico (cauda dominada por um caractere, ex. '!!!' = token 0) ou runaway.
Foi o teste do A/B lm_head INT4 vs INT8 (2026-11-19): INT4 2/9 falhas, INT8 0/9.

  python3 scripts/loop_stress.py N ROTULO SAIDA.json [PORTA]   # N=9 leva ~40-60 min
"""
import json, sys, time, urllib.request, concurrent.futures as cf, collections
N = int(sys.argv[1]); TAG = sys.argv[2]; OUT = sys.argv[3]
PORT = sys.argv[4] if len(sys.argv) > 4 else "18020"
URL = f"http://127.0.0.1:{PORT}/v1/chat/completions"
R = "/root/qwen3/qwen38-27b-rtx3090/"
files = ["single-user/start_qwen.sh", "docs/optimizations.md", "launcher_common.sh", "resolve_config.sh"]
ctx = ""
for f in files:
    ctx += f"\n\n===== FILE: {f} =====\n" + open(R + f, errors="ignore").read()
ctx = ctx[:170000]
tools = [{"type": "function", "function": {"name": "write_file", "description": "Write a file to disk",
          "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                         "required": ["path", "content"]}}}]
task = ("Here is the codebase:\n" + ctx + "\n\nTask: plan carefully which behaviours of resolve_config.sh and the "
        "MAX_LEN selection in start_qwen.sh need unit tests (list at least 10 test cases with their exact inputs and "
        "expected outputs), then write the complete pytest file tests/test_launcher_config.py using the write_file tool.")
body = {"model": "qwen3.8-27b", "messages": [{"role": "user", "content": task}], "tools": tools,
        "max_tokens": 24000, "temperature": 1.0, "top_p": 0.95, "top_k": 20, "presence_penalty": 0.0,
        "reasoning_effort": "low", "thinking_token_budget": 60000,
        "repetition_detection": {"max_pattern_size": 0}}

def degenerate(text):
    """Colapso numerico: cauda dominada por um unico caractere (ex. '!' = token 0)."""
    t = text[-2000:]
    if len(t) < 500: return False
    ch, n = collections.Counter(t).most_common(1)[0]
    return n / len(t) > 0.8

def loop_score(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 20: return 0.0
    tail = lines[-200:]
    c = collections.Counter(tail)
    return round(sum(v for v in c.values() if v >= 3) / len(tail), 3)

def run(i):
    t = time.time()
    r = urllib.request.urlopen(urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=1800)
    d = json.load(r); c = d["choices"][0]; m = c["message"]
    reas = m.get("reasoning") or ""; cont = m.get("content") or ""
    tc = m.get("tool_calls") or []
    res = {"i": i, "finish": c["finish_reason"], "tool_call": bool(tc), "prompt_tok": d["usage"]["prompt_tokens"],
           "out_tok": d["usage"]["completion_tokens"],
           "reasoning_tok": (d["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens"),
           "loop_reasoning": loop_score(reas), "loop_content": loop_score(cont), "secs": round(time.time() - t),
           "tail": (reas + "\n|CONTENT|\n" + cont)[-300:]}
    res["degenerate"] = degenerate(reas) or degenerate(cont)
    res["runaway"] = c["finish_reason"] == "length" and not tc
    res["looped"] = res["loop_reasoning"] > 0.5 or res["loop_content"] > 0.5 or res["degenerate"]
    print(TAG, json.dumps({k: v for k, v in res.items() if k != "tail"}), flush=True)
    return res

with cf.ThreadPoolExecutor(3) as ex:
    rs = list(ex.map(run, range(N)))
json.dump(rs, open(OUT, "w"), indent=1, ensure_ascii=False)
print(TAG, "degenerados(!!!)", sum(r["degenerate"] for r in rs), "| runaway sem tool_call", sum(r["runaway"] for r in rs))
print(TAG, "RESUMO: loops", sum(r["looped"] for r in rs), "/", N, "| tool_call", sum(r["tool_call"] for r in rs), "/", N,
      "| length", sum(r["finish"] == "length" for r in rs), "| reasoning_tok medio", round(sum(r["reasoning_tok"] or 0 for r in rs)/len(rs)), "| loop_reasoning medio", round(sum(r["loop_reasoning"] for r in rs)/len(rs), 3))
