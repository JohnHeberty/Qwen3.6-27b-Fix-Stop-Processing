#!/usr/bin/env python3
"""
Benchmark — Sweep incremental de contexto (8k→max) com MTP.

Testa N_CTX de --start ate --max, incremento de --step, reiniciando o
servidor entre cada teste. Para quando VRAM insuficiente ou servidor crasha.
Salva resultado em CSV incrementalmente a cada teste.

Uso:
    python3 tests/benchmark.py                          # sweep 8k→131k, step 8k
    python3 tests/benchmark.py --start 16384 --step 16384
    python3 tests/benchmark.py --start 8192 --step 8192 --max 65536
    python3 tests/benchmark.py --fill 80 --max-tokens 4096
    python3 tests/benchmark.py --resume data/temp/benchmark_20250101_120000.csv
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pandas", "-q"], check=True)
    import pandas as pd

try:
    import requests
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "requests", "-q"], check=True)
    import requests

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HEALTH_URL = "http://localhost:8000/health"
CHAT_URL = "http://localhost:8000/v1/chat/completions"
PDF_PATH = PROJECT_ROOT / "data" / "temp" / "RL_OREILLY_full.md"
TEMP_DIR = PROJECT_ROOT / "data" / "temp"

DEFAULT_START = 8192
DEFAULT_STEP = 8192
DEFAULT_MAX = 131072
DEFAULT_FILL = 90
DEFAULT_MAX_TOKENS = 2048
VRAM_OOM_THRESHOLD = 200  # MiB livre

CSV_SEP = ";"
CSV_DEC = ","

CSV_COLUMNS = [
    "timestamp", "n_ctx", "fill_pct", "prompt_tokens_est",
    "prompt_tokens", "completion_tokens", "tokens_gen",
    "prompt_time_s", "gen_time_s", "total_time_s",
    "tok_per_sec", "server_tok_per_sec",
    "draft_n", "draft_accepted", "mtp_acceptance_pct",
    "vram_used", "vram_free", "ram_free_before", "ram_free_after",
    "ram_delta", "rss", "status",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def get_vram():
    r = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used,memory.free",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    used, free = r.stdout.strip().split(", ")
    return int(used), int(free)


def get_ram_free():
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    return 0


def get_rss():
    r = subprocess.run(["ps", "-o", "rss=", "-C", "llama-server"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return sum(int(x) for x in r.stdout.strip().split() if x.isdigit()) // 1024
    return 0


def wait_server(timeout=180):
    start = time.time()
    while time.time() - start < timeout:
        try:
            if requests.get(HEALTH_URL, timeout=3).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def stop_server():
    subprocess.run(["pkill", "-f", "llama-server"], capture_output=True)
    time.sleep(3)
    subprocess.run(["pkill", "-9", "-f", "llama-server"], capture_output=True)
    time.sleep(2)


def start_server(n_ctx):
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        found = False
        for i, line in enumerate(lines):
            if line.startswith("N_CTX="):
                lines[i] = f"N_CTX={n_ctx}"
                found = True
                break
        if not found:
            lines.append(f"N_CTX={n_ctx}")
        env_path.write_text("\n".join(lines) + "\n")

    subprocess.Popen(
        ["make", "start-bg"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    if not wait_server(timeout=180):
        log("ERRO: Servidor nao iniciou em 180s")
        return False
    time.sleep(5)
    return True


# ── PDF / Prompt ──────────────────────────────────────────────────────────────

def load_pdf():
    if not PDF_PATH.exists():
        log(f"ERRO: PDF nao encontrado: {PDF_PATH}")
        sys.exit(1)
    return PDF_PATH.read_text(encoding="utf-8")


def build_prompt(pdf_text, target_tokens):
    target_chars = int(target_tokens * 3.5)
    truncated = pdf_text[:target_chars]
    estimated = len(truncated) // 3.5

    prompt = (
        "Voce recebeu um livro completo sobre Reinforcement Learning. "
        "Analise e resuma em 3-5 paragrafos.\n\n"
        "Conteudo:\n\n" + truncated
    )
    return prompt, int(estimated)


# ── CSV I/O ───────────────────────────────────────────────────────────────────

def save_csv_row(row: dict, csv_path: Path):
    """Append uma linha ao CSV. Cria com header se nao existir."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([row])
    if not csv_path.exists():
        df.to_csv(csv_path, sep=CSV_SEP, decimal=CSV_DEC, index=False)
    else:
        df.to_csv(csv_path, sep=CSV_SEP, decimal=CSV_DEC, index=False,
                  mode="a", header=False)
    log(f"CSV: +1 linha -> {csv_path.name} ({get_row_count(csv_path)} linhas total)")


def get_row_count(csv_path: Path) -> int:
    if not csv_path.exists():
        return 0
    df = pd.read_csv(csv_path, sep=CSV_SEP, decimal=CSV_DEC)
    return len(df)


def load_csv(csv_path: Path):
    if not csv_path.exists():
        return pd.DataFrame(columns=CSV_COLUMNS)
    return pd.read_csv(csv_path, sep=CSV_SEP, decimal=CSV_DEC)


# ── Teste individual ──────────────────────────────────────────────────────────

def run_test(pdf_text, n_ctx, fill_pct, max_tokens):
    target_tokens = int(n_ctx * fill_pct / 100)
    prompt, est_tokens = build_prompt(pdf_text, target_tokens)

    log(f"Prompt: ~{est_tokens:,} tokens ({fill_pct}% de {n_ctx // 1024}k)")

    vram_used, vram_free = get_vram()
    ram_free_before = get_ram_free()
    rss_before = get_rss()
    log(f"VRAM: {vram_used}/{vram_free} MiB | RAM livre: {ram_free_before} MiB | RSS: {rss_before} MiB")

    start_time = time.perf_counter()
    first_token_time = None
    end_time = None
    token_count = 0
    usage = None
    server_timings = None

    try:
        stream = requests.post(
            CHAT_URL,
            json={
                "model": "qwen3",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.3,
                "stream": True,
                "stream_options": {"include_usage": True},
            },
            stream=True,
            timeout=600,
        )

        if stream.status_code != 200:
            log(f"ERRO HTTP {stream.status_code}: {stream.text[:300]}")
            return None

        for line in stream.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if not decoded.startswith("data: ") or decoded == "data: [DONE]":
                continue
            try:
                chunk = json.loads(decoded[6:])

                if "usage" in chunk:
                    usage = chunk["usage"]
                if "timings" in chunk:
                    server_timings = chunk["timings"]

                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content") or delta.get("reasoning_content")
                    if content:
                        now = time.perf_counter()
                        if first_token_time is None:
                            first_token_time = now
                        end_time = now
                        token_count += 1
            except (json.JSONDecodeError, IndexError, KeyError):
                pass

        total_time = time.perf_counter() - start_time
        prompt_time = (first_token_time - start_time) if first_token_time else total_time
        gen_time = (end_time - first_token_time) if (first_token_time and end_time) else 0
        completion_tokens = usage.get("completion_tokens", 0) if usage else 0
        prompt_tokens = usage.get("prompt_tokens", 0) if usage else 0
        tok_per_sec = completion_tokens / gen_time if gen_time > 0 else 0
        server_tok_per_sec = server_timings.get("predicted_per_second", 0) if server_timings else 0
        draft_n = server_timings.get("draft_n", 0) if server_timings else 0
        draft_accepted = server_timings.get("draft_n_accepted", 0) if server_timings else 0
        mtp_pct = round(draft_accepted / draft_n * 100, 1) if draft_n > 0 else 0

        vram_used_after, vram_free_after = get_vram()
        ram_free_after = get_ram_free()
        rss_after = get_rss()

        status = "ok"
        if vram_free_after < VRAM_OOM_THRESHOLD:
            status = "vram_exhausted"
            log(f"!! VRAM livre < {VRAM_OOM_THRESHOLD} MiB")

        row = {
            "timestamp": datetime.now().isoformat(),
            "n_ctx": n_ctx,
            "fill_pct": fill_pct,
            "prompt_tokens_est": est_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tokens_gen": token_count,
            "prompt_time_s": round(prompt_time, 2),
            "gen_time_s": round(gen_time, 2),
            "total_time_s": round(total_time, 2),
            "tok_per_sec": round(tok_per_sec, 1),
            "server_tok_per_sec": round(server_tok_per_sec, 1),
            "draft_n": draft_n,
            "draft_accepted": draft_accepted,
            "mtp_acceptance_pct": mtp_pct,
            "vram_used": vram_used_after,
            "vram_free": vram_free_after,
            "ram_free_before": ram_free_before,
            "ram_free_after": ram_free_after,
            "ram_delta": ram_free_before - ram_free_after,
            "rss": rss_after,
            "status": status,
        }

        log(f"Resultado: {completion_tokens} tokens reais, {token_count} chunks | "
            f"{tok_per_sec:.1f} tok/s calc vs {server_tok_per_sec:.1f} server | "
            f"MTP: {draft_accepted}/{draft_n} aceitos ({mtp_pct}%) | "
            f"VRAM: {vram_used_after}/{vram_free_after} MiB | Status: {status}")

        return row

    except requests.exceptions.ConnectionError:
        log("!! Conexao perdida — servidor crashou?")
        return {"timestamp": datetime.now().isoformat(), "n_ctx": n_ctx,
                "status": "oom", "tokens_gen": 0, "tok_per_sec": 0,
                "server_tok_per_sec": 0,
                "draft_n": 0, "draft_accepted": 0, "mtp_acceptance_pct": 0,
                "fill_pct": fill_pct, "prompt_tokens_est": 0,
                "prompt_tokens": 0, "completion_tokens": 0,
                "prompt_time_s": 0, "gen_time_s": 0, "total_time_s": 0,
                "vram_used": 0, "vram_free": 0, "ram_free_before": 0,
                "ram_free_after": 0, "ram_delta": 0, "rss": 0}
    except Exception as e:
        log(f"ERRO: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Benchmark sweep de contexto")
    parser.add_argument("--start", type=int, default=DEFAULT_START,
                        help=f"N_CTX inicial (padrao: {DEFAULT_START})")
    parser.add_argument("--step", type=int, default=DEFAULT_STEP,
                        help=f"Incremento entre testes (padrao: {DEFAULT_STEP})")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX,
                        help=f"N_CTX maximo (padrao: {DEFAULT_MAX})")
    parser.add_argument("--fill", type=int, default=DEFAULT_FILL,
                        help=f"Preenchimento do contexto em %% (padrao: {DEFAULT_FILL})")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help=f"Max tokens a gerar (padrao: {DEFAULT_MAX_TOKENS})")
    parser.add_argument("--output", type=str,
                        help="Arquivo CSV de saida (padrao: data/temp/benchmark_<ts>.csv)")
    parser.add_argument("--resume", type=str,
                        help="Retomar de CSV existente")
    args = parser.parse_args()

    # Definir path do CSV
    if args.output:
        csv_path = Path(args.output)
    elif args.resume:
        csv_path = Path(args.resume)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = TEMP_DIR / f"benchmark_{ts}.csv"

    pdf_text = load_pdf()
    log(f"PDF: {len(pdf_text):,} chars (~{len(pdf_text) // 35 * 10:,} tokens)")

    # Gerar lista de contextos
    contexts = []
    ctx = args.start
    while ctx <= args.max:
        contexts.append(ctx)
        ctx += args.step

    log(f"Sweep: {len(contexts)} testes | {args.start}k → {args.max // 1024}k (step {args.step // 1024}k)")
    for c in contexts:
        log(f"  N_CTX={c:,} ({c // 1024}k)")

    # Carregar resultados existentes se --resume
    tested = set()
    if args.resume and csv_path.exists():
        df_existing = load_csv(csv_path)
        tested = set(df_existing["n_ctx"].astype(int).tolist())
        log(f"Resume: {len(tested)} contexto(s) ja no CSV")

    remaining = [c for c in contexts if c not in tested]
    if tested:
        log(f"Skip: {len(tested)} ja testados, {len(remaining)} restantes")

    if not remaining:
        log("Nenhum teste restante")
        return

    log(f"\nIniciando sweep...")

    stopped = False
    total = len(remaining)
    for i, n_ctx in enumerate(remaining, 1):
        if stopped:
            break

        log(f"\n{'=' * 60}")
        log(f"[{i}/{total}] N_CTX={n_ctx:,} ({n_ctx // 1024}k)")
        log(f"{'=' * 60}")

        stop_server()

        if not start_server(n_ctx):
            log(f"ERRO: Falha ao iniciar com N_CTX={n_ctx}")
            fail_row = {
                "timestamp": datetime.now().isoformat(),
                "n_ctx": n_ctx, "fill_pct": args.fill,
                "prompt_tokens_est": 0, "prompt_tokens": 0,
                "completion_tokens": 0, "tokens_gen": 0,
                "prompt_time_s": 0, "gen_time_s": 0, "total_time_s": 0,
                "tok_per_sec": 0, "server_tok_per_sec": 0,
                "draft_n": 0, "draft_accepted": 0, "mtp_acceptance_pct": 0,
                "vram_used": 0, "vram_free": 0,
                "ram_free_before": 0, "ram_free_after": 0,
                "ram_delta": 0, "rss": 0, "status": "fail",
            }
            save_csv_row(fail_row, csv_path)
            continue

        result = run_test(pdf_text, n_ctx, args.fill, args.max_tokens)

        if result is None:
            fail_row = {
                "timestamp": datetime.now().isoformat(),
                "n_ctx": n_ctx, "fill_pct": args.fill,
                "prompt_tokens_est": 0, "prompt_tokens": 0,
                "completion_tokens": 0, "tokens_gen": 0,
                "prompt_time_s": 0, "gen_time_s": 0, "total_time_s": 0,
                "tok_per_sec": 0, "server_tok_per_sec": 0,
                "draft_n": 0, "draft_accepted": 0, "mtp_acceptance_pct": 0,
                "vram_used": 0, "vram_free": 0,
                "ram_free_before": 0, "ram_free_after": 0,
                "ram_delta": 0, "rss": 0, "status": "fail",
            }
            save_csv_row(fail_row, csv_path)
        else:
            save_csv_row(result, csv_path)
            if result.get("status") in ("oom", "vram_exhausted"):
                stopped = True
                log(f"!! Sweep interrompido em N_CTX={n_ctx} ({result['status']})")

    stop_server()

    # Resumo final
    df = load_csv(csv_path)
    ok = df[df["status"] == "ok"]

    log(f"\n{'=' * 60}")
    log("RESUMO")
    log(f"{'=' * 60}")
    for _, r in df.iterrows():
        icon = "✓" if r["status"] == "ok" else "✗"
        log(f"  {icon} {int(r['n_ctx']) // 1024}k: {r['tok_per_sec']} tok/s, "
            f"VRAM {r['vram_used']}/{r['vram_free']} MiB, "
            f"status={r['status']}")

    if not ok.empty:
        avg_speed = ok["tok_per_sec"].mean()
        best = ok.loc[ok["tok_per_sec"].idxmax()]
        log(f"\nMedia: {avg_speed:.1f} tok/s")
        log(f"Melhor: {int(best['n_ctx']) // 1024}k @ {best['tok_per_sec']} tok/s")

    log(f"\nCSV: {csv_path}")
    log(f"Linhas: {len(df)}")


if __name__ == "__main__":
    main()
