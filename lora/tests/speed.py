#!/usr/bin/env python3
"""Decode tok/s per arm (streaming, short prompt, 600 output tokens) + DFlash2 acceptance via /metrics.

Same cases as scripts/bench_tps.py (code / narrative), but with arms (model + thinking).
Answers: how much does --enable-lora cost on base requests (compare with production:
133.1 / 66.9 tok/s, 2026-11-12) and how much does the adapter cost on its own requests.

  python3 -I lora/tests/speed.py --reps 3 --out lora/results/speed.json

Default: temperature 0 and thinking off on every arm (comparable among themselves).
--card uses the card's sampling (0.8 / 1.0) instead of greedy.
"""
import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

CASES = {
    "codigo": "Escreva uma função Python que faz merge sort, com comentários explicando cada passo. "
              "Depois explique a complexidade.",
    "narrativo": "Escreva um parágrafo narrativo sobre uma viagem de trem pelo interior do Brasil, "
                 "com descrição das paisagens e das pessoas.",
}
ap = argparse.ArgumentParser()
ap.add_argument("--url", default=C.DEFAULT_URL)
ap.add_argument("--models", default=f"{C.BASE_MODEL},{C.LORA_MODEL}")
ap.add_argument("--reps", type=int, default=3)
ap.add_argument("--max-tokens", type=int, default=600)
ap.add_argument("--card", action="store_true")
ap.add_argument("--out", default="")
a = ap.parse_args()
URL = C.check_url(a.url)
samp = C.CARD_SAMPLING if a.card else {"temperature": 0.0}

res = {}
for model in a.models.split(","):
    for case, prompt in CASES.items():
        rows = []
        for i in range(a.reps):
            c0 = C.spec_counters(URL)
            r = C.chat_stream(URL, {"model": model, "max_tokens": a.max_tokens, "ignore_eos": True,
                                    "messages": [{"role": "user", "content": prompt}], **samp, **C.NO_THINK})
            sp = C.spec_delta(c0, C.spec_counters(URL))
            rows.append({k: r[k] for k in ("completion_tokens", "ttft", "seconds", "decode_tok_s", "finish")}
                        | {"accept_rate": sp["accept_rate"], "mean_accept_len": sp["mean_accept_len"],
                           "degenerate": C.is_degenerate(r["content"])})
            print(f"{model:<18} {case:<10} rep{i + 1}: {r['decode_tok_s']} tok/s ttft={r['ttft']}s "
                  f"accept={sp['accept_rate']} len={sp['mean_accept_len']} degenerate={rows[-1]['degenerate']}",
                  flush=True)
        tps = [x["decode_tok_s"] for x in rows]
        res[f"{model}/{case}"] = {"runs": rows, "median_tok_s": round(statistics.median(tps), 1)}
        print(f"  -> {model}/{case}: median {res[f'{model}/{case}']['median_tok_s']} tok/s\n")
if a.out:
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(res, open(a.out, "w"), indent=1, ensure_ascii=False)
