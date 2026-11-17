#!/usr/bin/env python3
"""Compara as métricas de decodificação especulativa entre boots do vLLM,
extraindo do log do serviço (sem precisar reiniciar o servidor).

Cada boot é aberto pela linha "Initializing a V1 LLM engine (vX.Y.Z)" e a
versão do vLLM vem do próprio marcador. As métricas vêm das linhas
"SpecDecoding metrics: ...".

  python3 scripts/compare_spec_metrics.py [LOG]
"""
import re
import sys
from collections import OrderedDict

LOG = sys.argv[1] if len(sys.argv) > 1 else "/root/qwen3/data/logs/qwen38-27b.log"

RE_BOOT = re.compile(r"Initializing a V1 LLM engine \(v([0-9]+\.[0-9]+(?:\.[0-9]+)?)\)")
RE_TS = re.compile(r"INFO (\d\d-\d\d \d\d:\d\d:\d\d)")
RE_METRICS = re.compile(r"SpecDecoding metrics: (.+)$")
RE_MAL = re.compile(r"Mean acceptance length: ([0-9]+\.?[0-9]*)")
RE_ACCEPTED_TPS = re.compile(r"Accepted throughput: ([0-9]+\.?[0-9]*) tokens/s")
RE_DRAFTED_TPS = re.compile(r"Drafted throughput: ([0-9]+\.?[0-9]*) tokens/s")
RE_AVG_ACCEPT = re.compile(r"Avg Draft acceptance rate: ([0-9]+\.?[0-9]*)%")


def parse(path):
    boots = []
    cur = None
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            mb = RE_BOOT.search(line)
            if mb:
                ts = RE_TS.search(line)
                cur = {
                    "version": mb.group(1),
                    "ts": ts.group(1) if ts else "?",
                    "accept": {},
                }
                boots.append(cur)
                continue
            if cur is None:
                continue
            mm = RE_METRICS.search(line)
            if not mm:
                continue
            body = mm.group(1)
            for key, rx in (
                ("mal", RE_MAL),
                ("accepted_tps", RE_ACCEPTED_TPS),
                ("drafted_tps", RE_DRAFTED_TPS),
                ("avg_accept", RE_AVG_ACCEPT),
            ):
                m = rx.search(body)
                if m:
                    cur["accept"][key] = float(m.group(1))
    return boots


def main():
    boots = parse(LOG)
    if not boots:
        print("nenhum boot encontrado em", LOG)
        return 1
    print(f"{'boot (inicio)':<20} {'vllm':<8} {'mean accept len':>16} "
          f"{'avg draft accept':>18} {'accepted tok/s':>16}")
    print("-" * 84)
    for b in boots:
        acc = b["accept"]
        mal = acc.get("mal")
        ada = acc.get("avg_accept")
        atps = acc.get("accepted_tps")
        print(
            f"{str(b['ts']):<20} {b['version']:<8} "
            f"{(f'{mal:.3f}' if mal is not None else '-'):>16} "
            f"{(f'{ada:.1f}%' if ada is not None else '-'):>18} "
            f"{(f'{atps:.1f}' if atps is not None else '-'):>16}"
        )
    print()
    agg = OrderedDict()
    for b in boots:
        agg.setdefault(b["version"], []).append(b["accept"])
    print("resumo por versao (media das leituras por boot):")
    for v, rows in agg.items():
        mals = [r["mal"] for r in rows if "mal" in r]
        adas = [r["avg_accept"] for r in rows if "avg_accept" in r]
        atps = [r["accepted_tps"] for r in rows if "accepted_tps" in r]
        if not mals:
            print(f"  vLLM {v}: n=0 (sem leitura de acceptance length no log)")
            continue
        print(
            f"  vLLM {v}: boots={len(rows)} leituras={len(mals)} "
            f"mean_accept_len={sum(mals) / len(mals):.3f} "
            f"min={min(mals):.3f} max={max(mals):.3f} "
            f"avg_draft_accept={sum(adas) / len(adas):.1f}% "
            f"accepted_tps={sum(atps) / len(atps):.1f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
