#!/usr/bin/env python3
"""Benchmark de decode do servidor local (código e narrativa), reprodutível.

Mede tok/s de saída com stream, temperatura 0, N repetições por caso, e
captura as métricas de SpecDecoding do /metrics antes e depois de cada caso
para correlacionar aceitação do rascunho com a velocidade.

  python3 scripts/bench_tps.py [--url URL] [--reps N] [--out FILE]
"""
import argparse
import json
import re
import statistics
import sys
import time
import urllib.request

RE_SPEC = re.compile(
    r"vllm:spec_decode_num_accepted_tokens_total\{[^}]*\}\s+([0-9.e+-]+)"
)
RE_DRAFT = re.compile(r"vllm:spec_decode_num_draft_tokens_total\{[^}]*\}\s+([0-9.e+-]+)")


def fetch_metrics(url):
    req = urllib.request.Request(url + "/metrics")
    out = {}
    with urllib.request.urlopen(req, timeout=30) as r:
        for line in r.read().decode("utf-8", "replace").splitlines():
            m = RE_SPEC.search(line)
            if m:
                out["accepted"] = float(m.group(1))
                continue
            m = RE_DRAFT.search(line)
            if m:
                out["drafted"] = float(m.group(1))
    return out


def measure(url, model, prompt, max_tokens):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    req = urllib.request.Request(
        url + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
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
    return completion, time.time() - t0, "".join(text)


CASES = {
    "codigo": "Escreva uma função Python que faz merge sort, com comentários explicando cada passo. "
              "Depois explique a complexidade.",
    "narrativo": "Escreva um parágrafo narrativo sobre uma viagem de trem pelo interior do Brasil, "
                 "com descrição das paisagens e das pessoas.",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:18020")
    ap.add_argument("--model", default="qwen3.8-27b")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=600)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    results = {}
    for name, prompt in CASES.items():
        rows = []
        for i in range(args.reps):
            m0 = fetch_metrics(args.url)
            completion, elapsed, text = measure(
                args.url, args.model, prompt, args.max_tokens
            )
            m1 = fetch_metrics(args.url)
            acc = m1.get("accepted", 0) - m0.get("accepted", 0)
            draft = m1.get("drafted", 0) - m0.get("drafted", 0)
            tps = completion / elapsed if elapsed else 0.0
            accept_len = (acc / draft) if draft else 0.0
            rows.append(
                {
                    "rep": i + 1,
                    "tokens": completion,
                    "seconds": round(elapsed, 2),
                    "tok_s": round(tps, 1),
                    "accepted_tokens": acc,
                    "drafted_tokens": draft,
                    "accept_len": round(accept_len, 3),
                }
            )
            print(
                f"{name} rep{i + 1}: {completion} tokens em {elapsed:.1f}s = {tps:.1f} tok/s"
                f"  accept_len={accept_len:.3f} (accepted {acc:.0f} / drafted {draft:.0f})"
            )
            print(f"  inicio: {text[:80]!r}")
        tpss = [r["tok_s"] for r in rows]
        results[name] = {
            "runs": rows,
            "median_tok_s": round(statistics.median(tpss), 1),
            "mean_tok_s": round(statistics.mean(tpss), 1),
            "min_tok_s": min(tpss),
            "max_tok_s": max(tpss),
        }
        print(
            f"{name}: mediana {results[name]['median_tok_s']} tok/s"
            f" (min {min(tpss)} / max {max(tpss)})\n"
        )
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(results, fh, indent=2, ensure_ascii=False)
        print("gravado em", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
