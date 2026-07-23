#!/usr/bin/env python3
"""
MTP Sweep — testa diferentes MTP_TOKENS (n=1 até --max-n) com um modelo.
Lê MODEL_FILE do .env, roda benchmark em contexto fixo (8k) para cada n.

Uso:
    python3 tests/sweep_mtp.py                              # n=1..6, 8k
    python3 tests/sweep_mtp.py --max-n 8                    # n=1..8
    python3 tests/sweep_mtp.py --n-ctx 16384                # 16k em vez de 8k
    python3 tests/sweep_mtp.py --resume data/temp/sweep_*.csv
"""

import argparse
import json
import os
import re
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


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
HEALTH_URL = "http://localhost:8000/health"
CHAT_URL = "http://localhost:8000/v1/chat/completions"
PDF_PATH = PROJECT_ROOT / "data" / "temp" / "RL_OREILLY_full.md"
TEMP_DIR = PROJECT_ROOT / "data" / "temp"

DEFAULT_MAX_N = 6
DEFAULT_N_CTX = 8192
DEFAULT_FILL = 90
DEFAULT_MAX_TOKENS = 2048
VRAM_OOM_THRESHOLD = 200

CSV_SEP = ";"
CSV_DEC = ","

CSV_COLUMNS = [
    "timestamp", "model", "n_ctx", "mtp_n",
    "fill_pct", "prompt_tokens_est",
    "prompt_tokens", "completion_tokens", "tokens_gen",
    "prompt_time_s", "gen_time_s", "total_time_s",
    "tok_per_sec", "server_tok_per_sec",
    "prefill_tps", "decode_tps",
    "prompt_per_token_ms", "predicted_per_token_ms",
    "draft_n", "draft_accepted", "mtp_acceptance_pct",
    "vram_used", "vram_free",
    "ram_free_before", "ram_free_after", "ram_delta",
    "rss", "status",
]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def get_model_file():
    if not ENV_PATH.exists():
        log("ERRO: .env nao encontrado")
        sys.exit(1)
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith("MODEL_FILE="):
            return line.split("=", 1)[1].strip()
    log("ERRO: MODEL_FILE nao definido no .env")
    sys.exit(1)


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
    subprocess.run(["pkill", "llama-server"], capture_output=True)
    time.sleep(3)
    subprocess.run(["pkill", "-9", "llama-server"], capture_output=True)
    time.sleep(2)


def start_server():
    subprocess.Popen(
        ["make", "start-bg"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    if not wait_server(timeout=180):
        return False
    time.sleep(5)
    return True


def set_env_n_ctx(n_ctx):
    lines = ENV_PATH.read_text().splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith("N_CTX="):
            lines[i] = f"N_CTX={n_ctx}"
            found = True
            break
    if not found:
        lines.append(f"N_CTX={n_ctx}")
    ENV_PATH.write_text("\n".join(lines) + "\n")


def set_env_mtp(mtp_n):
    lines = ENV_PATH.read_text().splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith("MTP_TOKENS="):
            lines[i] = f"MTP_TOKENS={mtp_n}"
            found = True
            break
    if not found:
        # Add before or after ENABLE_MTP
        for i, line in enumerate(lines):
            if line.startswith("ENABLE_MTP="):
                lines.insert(i + 1, f"MTP_TOKENS={mtp_n}")
                found = True
                break
    ENV_PATH.write_text("\n".join(lines) + "\n")


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


def save_csv_row(row, csv_path):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([row])
    if not csv_path.exists():
        df.to_csv(csv_path, sep=CSV_SEP, decimal=CSV_DEC, index=False)
    else:
        df.to_csv(csv_path, sep=CSV_SEP, decimal=CSV_DEC, index=False,
                  mode="a", header=False)


def load_csv(csv_path):
    if not csv_path.exists():
        return pd.DataFrame(columns=CSV_COLUMNS)
    return pd.read_csv(csv_path, sep=CSV_SEP, decimal=CSV_DEC)


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
        prefill_tps = server_timings.get("prompt_per_second", 0) if server_timings else 0
        decode_tps = server_tok_per_sec
        prompt_per_token_ms = round(server_timings.get("prompt_per_token_ms", 0), 2) if server_timings else 0
        predicted_per_token_ms = round(server_timings.get("predicted_per_token_ms", 0), 2) if server_timings else 0
        draft_n = server_timings.get("draft_n", 0) if server_timings else 0
        draft_accepted = server_timings.get("draft_n_accepted", 0) if server_timings else 0
        mtp_pct = round(draft_accepted / draft_n * 100, 1) if draft_n > 0 else 0

        vram_used_after, vram_free_after = get_vram()
        ram_free_after = get_ram_free()
        rss_after = get_rss()

        status = "ok"
        if vram_free_after < VRAM_OOM_THRESHOLD:
            status = "vram_exhausted"

        row = {
            "timestamp": datetime.now().isoformat(),
            "model": get_model_file(),
            "n_ctx": n_ctx,
            "mtp_n": None,
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
            "prefill_tps": round(prefill_tps, 1),
            "decode_tps": round(decode_tps, 1),
            "prompt_per_token_ms": prompt_per_token_ms,
            "predicted_per_token_ms": predicted_per_token_ms,
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
        log(f"Resultado: {completion_tokens} tokens | "
            f"TTFT={prompt_time:.1f}s prefill={prefill_tps:.1f}t/s "
            f"decode={tok_per_sec:.1f}t/s (server:{server_tok_per_sec:.1f}) | "
            f"MTP: {draft_accepted}/{draft_n} ({mtp_pct}%) | "
            f"VRAM: {vram_used_after}/{vram_free_after} MiB")
        return row

    except requests.exceptions.ConnectionError:
        log("!! Conexao perdida — servidor crashou?")
        return {"timestamp": datetime.now().isoformat(), "model": get_model_file(),
                "n_ctx": n_ctx, "mtp_n": None,
                "status": "oom", "tokens_gen": 0, "tok_per_sec": 0,
                "server_tok_per_sec": 0,
                "prefill_tps": 0, "decode_tps": 0,
                "prompt_per_token_ms": 0, "predicted_per_token_ms": 0,
                "draft_n": 0, "draft_accepted": 0, "mtp_acceptance_pct": 0,
                "fill_pct": fill_pct, "prompt_tokens_est": 0,
                "prompt_tokens": 0, "completion_tokens": 0,
                "prompt_time_s": 0, "gen_time_s": 0, "total_time_s": 0,
                "vram_used": 0, "vram_free": 0, "ram_free_before": 0,
                "ram_free_after": 0, "ram_delta": 0, "rss": 0}
    except Exception as e:
        log(f"ERRO: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="MTP sweep — testa MTP_TOKENS n=1..max-n")
    parser.add_argument("--max-n", type=int, default=DEFAULT_MAX_N,
                        help=f"Max MTP_TOKENS (padrao: {DEFAULT_MAX_N})")
    parser.add_argument("--n-ctx", type=int, default=DEFAULT_N_CTX,
                        help=f"N_CTX fixo para todos os testes (padrao: {DEFAULT_N_CTX})")
    parser.add_argument("--fill", type=int, default=DEFAULT_FILL)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--output", type=str)
    parser.add_argument("--resume", type=str)
    args = parser.parse_args()

    model_file = get_model_file()
    log(f"Modelo: {model_file}")

    if args.output:
        csv_path = Path(args.output)
    elif args.resume:
        csv_path = Path(args.resume)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = Path(model_file).stem
        csv_path = TEMP_DIR / f"sweep_mtp_{name}_{ts}.csv"

    pdf_text = load_pdf()
    log(f"PDF: {len(pdf_text):,} chars")

    mtp_values = list(range(1, args.max_n + 1))
    log(f"Sweep MTP: {mtp_values} | N_CTX fixo = {args.n_ctx} ({args.n_ctx // 1024}k)")

    tested = set()
    if args.resume and csv_path.exists():
        df_existing = load_csv(csv_path)
        if "mtp_n" in df_existing.columns:
            tested = set(df_existing["mtp_n"].astype(int).tolist())
        log(f"Resume: {len(tested)} MTP n ja testados")

    remaining = [n for n in mtp_values if n not in tested]
    if not remaining:
        log("Nenhum MTP n restante para testar")
        return

    set_env_n_ctx(args.n_ctx)
    log(f"N_CTX={args.n_ctx} setado no .env")

    total = len(remaining)
    for i, mtp_n in enumerate(remaining, 1):
        log(f"\n{'=' * 60}")
        log(f"[{i}/{total}] MTP_TOKENS={mtp_n}")
        log(f"{'=' * 60}")

        set_env_mtp(mtp_n)
        stop_server()
        log("Servidor parado. Reiniciando...")

        if not start_server():
            log(f"ERRO: servidor nao iniciou com MTP_TOKENS={mtp_n}")
            fail_row = {
                "timestamp": datetime.now().isoformat(),
                "model": model_file, "n_ctx": args.n_ctx, "mtp_n": mtp_n,
                "fill_pct": args.fill, "prompt_tokens_est": 0,
                "prompt_tokens": 0, "completion_tokens": 0, "tokens_gen": 0,
                "prompt_time_s": 0, "gen_time_s": 0, "total_time_s": 0,
                "tok_per_sec": 0, "server_tok_per_sec": 0,
                "prefill_tps": 0, "decode_tps": 0,
                "prompt_per_token_ms": 0, "predicted_per_token_ms": 0,
                "draft_n": 0, "draft_accepted": 0, "mtp_acceptance_pct": 0,
                "vram_used": 0, "vram_free": 0,
                "ram_free_before": 0, "ram_free_after": 0,
                "ram_delta": 0, "rss": 0, "status": "fail",
            }
            save_csv_row(fail_row, csv_path)
            continue

        row = run_test(pdf_text, args.n_ctx, args.fill, args.max_tokens)
        if row:
            row["mtp_n"] = mtp_n
            save_csv_row(row, csv_path)
        else:
            fail_row = {
                "timestamp": datetime.now().isoformat(),
                "model": model_file, "n_ctx": args.n_ctx, "mtp_n": mtp_n,
                "fill_pct": args.fill, "prompt_tokens_est": 0,
                "prompt_tokens": 0, "completion_tokens": 0, "tokens_gen": 0,
                "prompt_time_s": 0, "gen_time_s": 0, "total_time_s": 0,
                "tok_per_sec": 0, "server_tok_per_sec": 0,
                "prefill_tps": 0, "decode_tps": 0,
                "prompt_per_token_ms": 0, "predicted_per_token_ms": 0,
                "draft_n": 0, "draft_accepted": 0, "mtp_acceptance_pct": 0,
                "vram_used": 0, "vram_free": 0,
                "ram_free_before": 0, "ram_free_after": 0,
                "ram_delta": 0, "rss": 0, "status": "fail",
            }
            save_csv_row(fail_row, csv_path)

    stop_server()

    # Restaurar MTP_TOKENS padrao (2)
    set_env_mtp(2)

    df = load_csv(csv_path)
    ok = df[df["status"] == "ok"]

    log(f"\n{'=' * 60}")
    log("RESUMO MTP SWEEP")
    log(f"{'=' * 60}")
    for _, r in df.iterrows():
        icon = "✓" if r["status"] == "ok" else "✗"
        mtp = int(r["mtp_n"]) if pd.notna(r.get("mtp_n")) else "?"
        log(f"  {icon} MTP n={mtp}: decode={r['tok_per_sec']}t/s "
            f"prefill={r['prefill_tps']}t/s TTFT={r['prompt_time_s']}s | "
            f"MTP {r['draft_accepted']}/{r['draft_n']} ({r['mtp_acceptance_pct']}%), "
            f"status={r['status']}")

    if not ok.empty:
        best = ok.loc[ok["tok_per_sec"].idxmax()]
        best_mtp = int(best["mtp_n"]) if pd.notna(best.get("mtp_n")) else "?"
        log(f"\nMelhor MTP: n={best_mtp} @ {best['tok_per_sec']} tok/s")
        log(f"Prefill medio: {ok['prefill_tps'].mean():.1f} t/s")

    log(f"\nCSV: {csv_path}")
    log(f"Linhas: {len(df)}")


if __name__ == "__main__":
    main()
