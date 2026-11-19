#!/usr/bin/env python3
"""Summarizes the "SpecDecoding metrics" lines from the vLLM log (the stat logger prints every 10 s).

  python3 -I lora/tests/spec_log.py lora/logs/lora-<ts>.log [--since "11-18 23:10:00"] [--until ...]

Counts Accepted/Drafted per interval, the per-position rate, and flags intervals with
suspicious acceptance (gotcha 49 in upstream docs/gotchas.md: high acceptance may be COLLAPSED
text, which is trivially predictable). Rule: an interval with acceptance > 0.75 is flagged;
cross-check against the degenerate turns in agent_ab and scripts/loop_stress.py before attributing the gain to
the drafter. The per-arm acceptance from /metrics (agent_ab.py, speed.py) is more precise;
this parser is the log-based cross-check and covers what ran outside the scripts
(e.g. the OpenCode 2 e2e).
"""
import argparse
import re

RE = re.compile(r"(?P<ts>\d\d-\d\d \d\d:\d\d:\d\d) \[metrics\.py:\d+\] SpecDecoding metrics: Mean acceptance length: "
                r"(?P<mal>[\d.]+).*?Accepted: (?P<acc>\d+) tokens, Drafted: (?P<dr>\d+) tokens, "
                r"Per-position acceptance rate: (?P<pp>[\d., ]+?), Avg Draft")

ap = argparse.ArgumentParser()
ap.add_argument("log")
ap.add_argument("--since", default="")
ap.add_argument("--until", default="")
a = ap.parse_args()

acc = dr = n = sus = 0
pos = None
for line in open(a.log, errors="replace"):
    m = RE.search(line)
    if not m:
        continue
    ts = m.group("ts")
    if (a.since and ts < a.since) or (a.until and ts > a.until):
        continue
    x, y = int(m.group("acc")), int(m.group("dr"))
    if y == 0:
        continue
    n += 1
    acc += x
    dr += y
    pp = [float(v) for v in m.group("pp").split(",")]
    pos = pp if pos is None else [p + q for p, q in zip(pos, pp)]
    if x / y > 0.75:
        sus += 1
        print(f"SUSPECT {ts}: acceptance {x / y:.2f} (Accepted {x} / Drafted {y}) -> check for collapsed text")
if not n:
    print("no SpecDecoding line with Drafted>0 in the window")
else:
    print(f"intervals={n} accepted={acc} drafted={dr} acceptance={acc / dr:.3f} suspects(>0.75)={sus}")
    print("mean per-position rate:", ", ".join(f"{p / n:.3f}" for p in pos))
