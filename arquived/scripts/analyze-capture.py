#!/usr/bin/env python3
"""
analyze-capture.py — transforma a captura CRUA do llama-server em relatório com flags.

Lê:
  data/logs/capture/llama-verbose.log   (--verbose): geração token-a-token + motivo de parada
  data/logs/capture/prompts/**/*.txt     (--log-prompts-dir): prompt renderizado por requisição
  data/logs/server.log                    (fallback de timings)

Emite:
  - um relatório legível (default) com contadores de flags, percentis e top ofensores
  - JSONL estruturado (--jsonl PATH), 1 registro por geração

Flags automáticas (fecham hipóteses):
  runaway      geração bateu (ou quase) o teto n_predict  -> loop de repetição (H09)
  loop_repeat  texto gerado tem repetição cíclica          -> loop (H09)
  empty_turn   sem content e sem <tool_call>               -> "couldn't generate a response" (H02)
  thinking_only só raciocínio, nada depois de </think>     -> (H02/H03)
  has_tool_call emitiu <tool_call>/<function=              (informativo / H05)
  near_context  prompt perto do teto de contexto           -> overflow (H01)

Uso:
  python3 scripts/analyze-capture.py [--capture-dir DIR] [--n-predict 8192]
          [--n-ctx 106496] [--jsonl out.jsonl] [--top 10] [--since HH:MM]
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# "slot ... : id  0 | task 123 | ... next token:  1234 'txt'"
RE_TASK = re.compile(r"task\s+(\d+)\b")
RE_NEXT = re.compile(r"next token:\s*\d+\s+'(.*)'\s*$")
# token de newline: a linha termina com "next token: N '" (aspa aberta, sem fechar)
RE_NEXT_NL = re.compile(r"next token:\s*\d+\s+'$")
RE_STOP_LIMIT = re.compile(r"stopped by limit, n_decoded = (\d+), n_predict = (\d+)")
RE_STOP_EOS = re.compile(r"stopped by EOS")
RE_STOP_CTX = re.compile(r"running out of context")
RE_LAUNCH = re.compile(r"launch_slot_.*task\s+(\d+)")


def reconstruct_generations(verbose_path):
    """Reconstroi o texto gerado por task a partir das linhas 'next token'."""
    gens = defaultdict(lambda: {"text": [], "n_tokens": 0, "finish": None, "n_predict": None})
    if not os.path.exists(verbose_path):
        return {}
    with open(verbose_path, "r", errors="replace") as f:
        for line in f:
            mt = RE_TASK.search(line)
            if not mt:
                continue
            task = mt.group(1)
            g = gens[task]
            mn = RE_NEXT.search(line)
            if mn:
                # desescapa \n \t que o log emite como literais
                piece = mn.group(1).replace("\\n", "\n").replace("\\t", "\t")
                g["text"].append(piece)
                g["n_tokens"] += 1
                continue
            if RE_NEXT_NL.search(line.rstrip("\n")):  # token de quebra de linha
                g["text"].append("\n")
                g["n_tokens"] += 1
                continue
            ml = RE_STOP_LIMIT.search(line)
            if ml:
                g["finish"] = "limit"
                g["n_predict"] = int(ml.group(2))
                continue
            if RE_STOP_EOS.search(line):
                g["finish"] = g["finish"] or "eos"
            elif RE_STOP_CTX.search(line):
                g["finish"] = g["finish"] or "context"
    for g in gens.values():
        g["text"] = "".join(g["text"])
    return gens


def split_think(text):
    """Retorna (reasoning, final) separando o bloco <think>...</think>."""
    if "</think>" in text:
        head, _, tail = text.partition("</think>")
        reasoning = head.split("<think>", 1)[-1]
        return reasoning, tail
    if "<think>" in text:  # abriu e não fechou (raciocínio consumiu tudo)
        return text.split("<think>", 1)[-1], ""
    return "", text


def has_repetition(text, window=48, min_repeats=4):
    """Heurística de loop: alguma janela de `window` chars aparece >= min_repeats vezes."""
    if len(text) < window * min_repeats:
        return False
    seen = defaultdict(int)
    step = max(1, window // 4)
    for i in range(0, len(text) - window, step):
        chunk = text[i:i + window]
        if chunk.strip():
            seen[chunk] += 1
            if seen[chunk] >= min_repeats:
                return True
    return False


def analyze_prompts(prompts_glob, n_ctx):
    """Analisa os dumps de prompt: tamanho, tools, near_context, e detecta prompts repetidos."""
    files = sorted(glob.glob(prompts_glob, recursive=True), key=lambda p: os.path.basename(p))
    recs = []
    prev_sig = None
    repeat_run = 0
    max_repeat_run = 0
    for fp in files:
        try:
            txt = open(fp, "r", errors="replace").read()
        except OSError:
            continue
        approx_tokens = len(txt) // 4  # estimativa grosseira
        n_tools = txt.count("<function=") + (txt.count('"name"') if "<tools>" in txt else 0)
        sig = txt[:400]
        if sig == prev_sig:
            repeat_run += 1
            max_repeat_run = max(max_repeat_run, repeat_run)
        else:
            repeat_run = 0
        prev_sig = sig
        recs.append({
            "file": os.path.basename(fp),
            "chars": len(txt),
            "approx_tokens": approx_tokens,
            "near_context": approx_tokens > 0.9 * n_ctx,
            "has_tools_block": "<tools>" in txt,
        })
    return recs, max_repeat_run


def pct(sorted_vals, p):
    if not sorted_vals:
        return 0
    i = min(len(sorted_vals) - 1, int(p / 100 * len(sorted_vals)))
    return sorted_vals[i]


def main():
    ap = argparse.ArgumentParser(description="Analisa a captura crua do llama-server.")
    ap.add_argument("--capture-dir", default=os.path.join(ROOT, "data/logs/capture"))
    ap.add_argument("--n-predict", type=int, default=int(os.environ.get("N_PREDICT", "8192")))
    ap.add_argument("--n-ctx", type=int, default=int(os.environ.get("N_CTX", "106496")))
    ap.add_argument("--jsonl", default=None, help="grava 1 registro por geração")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    verbose_path = os.path.join(args.capture_dir, "llama-verbose.log")
    prompts_glob = os.path.join(args.capture_dir, "prompts", "**", "*.txt")

    gens = reconstruct_generations(verbose_path)
    prompt_recs, prompt_repeat_run = analyze_prompts(prompts_glob, args.n_ctx)

    records = []
    for task, g in gens.items():
        text = g["text"]
        reasoning, final = split_think(text)
        has_tc = ("<tool_call>" in text) or ("<function=" in text)
        near_cap = g["n_tokens"] >= (args.n_predict - 64) or g["finish"] == "limit"
        loop = has_repetition(text)
        empty = (not final.strip()) and (not has_tc)
        thinking_only = bool(reasoning.strip()) and empty
        rec = {
            "task": task,
            "n_tokens": g["n_tokens"],
            "finish": g["finish"],
            "reasoning_len": len(reasoning),
            "final_len": len(final.strip()),
            "flags": {
                "runaway": near_cap,
                "loop_repeat": loop,
                "empty_turn": empty,
                "thinking_only": thinking_only,
                "has_tool_call": has_tc,
            },
            "preview": (final.strip() or reasoning.strip())[:160],
        }
        records.append(rec)

    if args.jsonl:
        with open(args.jsonl, "w") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ── Relatório ──────────────────────────────────────────────────────────────
    n = len(records)
    print("=" * 64)
    print(f"  RELATÓRIO DE CAPTURA — {n} gerações, {len(prompt_recs)} prompts")
    print(f"  (n_predict={args.n_predict}, n_ctx={args.n_ctx})")
    print("=" * 64)
    if n == 0 and not prompt_recs:
        print("  Nenhum dado. Ligue `make capture-on`, reproduza, e rode de novo.")
        return

    def count(flag):
        return sum(1 for r in records if r["flags"][flag])

    for flag in ["runaway", "loop_repeat", "empty_turn", "thinking_only", "has_tool_call"]:
        c = count(flag)
        bar = "█" * int(30 * c / n) if n else ""
        print(f"  {flag:14s}: {c:4d}/{n}  {bar}")

    near_ctx = sum(1 for p in prompt_recs if p["near_context"])
    print(f"  {'near_context':14s}: {near_ctx:4d}/{len(prompt_recs)}  (prompt > 90% do contexto)")
    print(f"  prompts quase-idênticos em sequência (máx run): {prompt_repeat_run}")

    toks = sorted(r["n_tokens"] for r in records)
    print(f"\n  Tokens gerados: p50={pct(toks,50)} p90={pct(toks,90)} max={toks[-1] if toks else 0}")

    print(f"\n  TOP {args.top} ofensores (runaway/loop/empty):")
    def score(r):
        f = r["flags"]
        return (f["runaway"] + f["loop_repeat"] + f["empty_turn"], r["n_tokens"])
    for r in sorted(records, key=score, reverse=True)[:args.top]:
        active = ",".join(k for k, v in r["flags"].items() if v) or "-"
        print(f"    task {r['task']:>8} | {r['n_tokens']:5d} tok | {r['finish'] or '?':7s} | {active}")
        print(f"      {r['preview']!r}")

    print("\n  Legenda: runaway=bateu teto | loop_repeat=texto repetitivo | "
          "empty_turn=sem content nem tool_call | thinking_only=só raciocínio")


if __name__ == "__main__":
    main()
