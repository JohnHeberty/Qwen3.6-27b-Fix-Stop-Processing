#!/usr/bin/env python3
"""Extrai por boot do log do serviço: versão do vLLM, argv principal
(gpu_memory_utilization, num_speculative_tokens, max_model_len, ...), tamanho
do pool de KV e a última leitura de SpecDecoding.

  python3 scripts/log_boot_analysis.py [LOG]
"""
import re
import sys

LOG = sys.argv[1] if len(sys.argv) > 1 else "/root/qwen3/data/logs/qwen38-27b.log"

RE_BOOT = re.compile(r"Initializing a V1 LLM engine \(v([0-9]+\.[0-9]+(?:\.[0-9]+)?)\)")
RE_TS = re.compile(r"INFO (\d\d-\d\d \d\d:\d\d:\d\d)")
RE_ARGS = re.compile(r"non-default args: (.*)$")
RE_KV = re.compile(r"GPU KV cache size: ([0-9,]+) tokens")
RE_CONC = re.compile(r"Maximum concurrency for ([0-9,]+) tokens per request: ([0-9.]+)x")
RE_MAL = re.compile(r"Mean acceptance length: ([0-9]+\.?[0-9]*)")
RE_AVG = re.compile(r"Avg Draft acceptance rate: ([0-9]+\.?[0-9]*)%")
RE_COMPILE = re.compile(r"torch.compile takes ([0-9.]+) seconds")
RE_INIT = re.compile(r"init engine \(.*?\) took ([0-9.]+) seconds")

KEYS = [
    "gpu_memory_utilization",
    "num_speculative_tokens",
    "max_model_len",
    "max_num_batched_tokens",
    "max_num_seqs",
    "kv_cache_memory_bytes",
    "kv_cache_dtype",
    "tensor_parallel_size",
    "attention_backend",
    "async_scheduling",
    "enable_prefix_caching",
    "method",
]


def parse(path):
    boots = []
    cur = None
    args = {}
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            mb = RE_BOOT.search(line)
            if mb:
                ts = RE_TS.search(line)
                cur = {
                    "version": mb.group(1),
                    "ts": ts.group(1) if ts else "?",
                    "args": "",
                    "kv": None,
                    "conc": None,
                    "mal": None,
                    "avg": None,
                    "compile_s": None,
                    "init_s": None,
                }
                boots.append(cur)
                continue
            if cur is None:
                continue
            ma = RE_ARGS.search(line)
            if ma:
                cur["args"] = ma.group(1)
                continue
            mk = RE_KV.search(line)
            if mk:
                cur["kv"] = int(mk.group(1).replace(",", ""))
            mc = RE_CONC.search(line)
            if mc:
                cur["conc"] = (mc.group(1), mc.group(2))
            mm = RE_MAL.search(line)
            if mm:
                cur["mal"] = float(mm.group(1))
            mv = RE_AVG.search(line)
            if mv:
                cur["avg"] = float(mv.group(1))
            mc2 = RE_COMPILE.search(line)
            if mc2:
                cur["compile_s"] = float(mc2.group(1))
            mi = RE_INIT.search(line)
            if mi:
                cur["init_s"] = float(mi.group(1))
    return boots


def pick(args, key):
    i = args.find(key)
    if i < 0:
        return None
    j = args.find(",", i)
    seg = args[i:] if j < 0 else args[i:j]
    seg = seg.strip()
    if ":" in seg:
        return seg.split(":", 1)[1].strip()
    return seg


def main():
    boots = parse(LOG)
    if not boots:
        print("nenhum boot encontrado")
        return 1
    for b in boots:
        if not b["kv"] and not b["mal"]:
            continue
        print(f"=== {b['ts']}  vLLM {b['version']}")
        for k in KEYS:
            v = pick(b["args"], k)
            if v:
                print(f"    {k} = {v}")
        print(
            f"    KV pool tokens = {b['kv']}  concurrency = {b['conc']}"
            f"  mean_accept_len = {b['mal']}  avg_draft_accept = {b['avg']}%"
            f"  compile_s = {b['compile_s']}  init_s = {b['init_s']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
