#!/usr/bin/env python3
"""
Benchmark — Sweep incremental de contexto (8k→max) com MTP.

Testa N_CTX de --start ate --max, incremento de --step, reiniciando o
servidor entre cada teste. Para quando VRAM insuficiente ou servidor crasha.

Uso:
    python3 tests/benchmark.py                          # sweep 8k→131k, step 8k
    python3 tests/benchmark.py --start 16384 --step 16384
    python3 tests/benchmark.py --start 8192 --step 8192 --max 65536
    python3 tests/benchmark.py --fill 80 --max-tokens 4096
    python3 tests/benchmark.py --resume data/temp/bench_partial_XXX.json
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
LOGS_DIR = PROJECT_ROOT / "data" / "logs"

DEFAULT_START = 8192
DEFAULT_STEP = 8192
DEFAULT_MAX = 131072
DEFAULT_FILL = 90
DEFAULT_MAX_TOKENS = 2048
VRAM_OOM_THRESHOLD = 200  # MiB livre


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_vram():
    """ Retorna (used_mib, free_mib). """
    r = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used,memory.free",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    used, free = r.stdout.strip().split(", ")
    return int(used), int(free)


def get_ram_free():
    """ Retorna RAM livre em MiB. """
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    return 0


def get_rss():
    """ Retorna RSS total do llama-server em MiB. """
    r = subprocess.run(["ps", "-o", "rss=", "-C", "llama-server"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return sum(int(x) for x in r.stdout.strip().split() if x.isdigit()) // 1024
    return 0


def wait_server(timeout=180):
    """ Aguarda servidor ficar pronto. """
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
    """ Para o servidor. """
    subprocess.run(["pkill", "-f", "llama-server"], capture_output=True)
    time.sleep(3)
    subprocess.run(["pkill", "-9", "-f", "llama-server"], capture_output=True)
    time.sleep(2)


def start_server(n_ctx):
    """ Atualiza N_CTX no .env e inicia o servidor em background. """
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
    """ Trunca o PDF e monta o prompt. Retorna (prompt, estimated_tokens). """
    target_chars = int(target_tokens * 3.5)
    truncated = pdf_text[:target_chars]
    estimated = len(truncated) // 3.5

    prompt = (
        "Voce recebeu um livro completo sobre Reinforcement Learning. "
        "Analise e resuma em 3-5 paragrafos.\n\n"
        "Conteudo:\n\n" + truncated
    )
    return prompt, int(estimated)


# ── Teste individual ──────────────────────────────────────────────────────────

def run_test(pdf_text, n_ctx, fill_pct, max_tokens):
    """
    Executa um teste de contexto.
    Retorna dict com metricas ou None em falha.
    """
    target_tokens = int(n_ctx * fill_pct / 100)
    prompt, est_tokens = build_prompt(pdf_text, target_tokens)

    log(f"Prompt: ~{est_tokens:,} tokens ({fill_pct}% de {n_ctx // 1024}k)")

    vram_used, vram_free = get_vram()
    ram_free_before = get_ram_free()
    rss_before = get_rss()
    log(f"VRAM: {vram_used}/{vram_free} MiB | RAM livre: {ram_free_before} MiB | RSS: {rss_before} MiB")

    # Request com streaming
    start_time = time.time()
    first_token_time = None
    token_count = 0
    response_text = ""

    try:
        stream = requests.post(
            CHAT_URL,
            json={
                "model": "qwen3",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.3,
                "stream": True,
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
                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if delta:
                    if first_token_time is None:
                        first_token_time = time.time()
                    response_text += delta
                    token_count += 1
            except (json.JSONDecodeError, IndexError, KeyError):
                pass

        total_time = time.time() - start_time
        prompt_time = (first_token_time - start_time) if first_token_time else total_time
        gen_time = (time.time() - first_token_time) if first_token_time else 0
        tok_per_sec = token_count / gen_time if gen_time > 0 else 0

        # Medicoes pos-request
        vram_used_after, vram_free_after = get_vram()
        ram_free_after = get_ram_free()
        rss_after = get_rss()

        status = "ok"
        if vram_free_after < VRAM_OOM_THRESHOLD:
            status = "vram_exhausted"
            log(f"!! VRAM livre < {VRAM_OOM_THRESHOLD} MiB")

        result = {
            "n_ctx": n_ctx,
            "fill_pct": fill_pct,
            "prompt_tokens_est": est_tokens,
            "tokens_gen": token_count,
            "prompt_time_s": round(prompt_time, 2),
            "gen_time_s": round(gen_time, 2),
            "total_time_s": round(total_time, 2),
            "tok_per_sec": round(tok_per_sec, 1),
            "vram_used": vram_used_after,
            "vram_free": vram_free_after,
            "ram_free_before": ram_free_before,
            "ram_free_after": ram_free_after,
            "ram_delta": ram_free_before - ram_free_after,
            "rss": rss_after,
            "status": status,
        }

        log(f"Resultado: {token_count} tokens em {gen_time:.1f}s = {tok_per_sec:.1f} tok/s | "
            f"VRAM: {vram_used_after}/{vram_free_after} MiB | Status: {status}")

        return result

    except requests.exceptions.ConnectionError:
        log("!! Conexao perdida — servidor crashou?")
        return {"n_ctx": n_ctx, "status": "oom", "tokens_gen": 0, "tok_per_sec": 0}
    except Exception as e:
        log(f"ERRO: {e}")
        return None


# ── Checkpoint ────────────────────────────────────────────────────────────────

def save_checkpoint(results, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "count": len(results),
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    log(f"Checkpoint: {len(results)} resultado(s) -> {path.name}")


def load_checkpoint(path):
    if not path.exists():
        log(f"ERRO: Checkpoint nao encontrado: {path}")
        return None
    with open(path) as f:
        return json.load(f).get("results", [])


# ── Report ────────────────────────────────────────────────────────────────────

def generate_report(results, args):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.output) if args.output else LOGS_DIR / f"benchmark_{ts}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ok = [r for r in results if r.get("status") == "ok"]
    failed = [r for r in results if r.get("status") != "ok"]

    with open(out_path, "w") as f:
        f.write(f"# Benchmark Sweep — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"**Config:** start={args.start}, step={args.step}, max={args.max}, "
                f"fill={args.fill}%, max_tokens={args.max_tokens}\n\n")

        if ok:
            avg_speed = sum(r["tok_per_sec"] for r in ok) / len(ok)
            best = max(ok, key=lambda r: r["tok_per_sec"])
            f.write(f"**Resumo:** {len(ok)} testes OK | "
                    f"velocidade media {avg_speed:.1f} tok/s | "
                    f"melhor {best['n_ctx'] // 1024}k @ {best['tok_per_sec']} tok/s\n\n")

        f.write("## Resultados\n\n")
        f.write("| N_CTX | Context | Prompt (est.) | Tokens gen | Prompt s | Gen s | tok/s | "
                "VRAM used | VRAM free | RAM delta | RSS | Status |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|\n")

        for r in results:
            ctx = r["n_ctx"]
            status_icon = {"ok": "✓", "oom": "✗ OOM", "vram_exhausted": "✗ VRAM",
                           "fail": "✗ FAIL"}.get(r.get("status", ""), r.get("status", ""))
            f.write(
                f"| {ctx:,} | {ctx // 1024}k | "
                f"~{r.get('prompt_tokens_est', 0):,} | "
                f"{r.get('tokens_gen', 0):,} | "
                f"{r.get('prompt_time_s', 0)} | "
                f"{r.get('gen_time_s', 0)} | "
                f"{r.get('tok_per_sec', 0)} | "
                f"{r.get('vram_used', 0)} MiB | "
                f"{r.get('vram_free', 0)} MiB | "
                f"{r.get('ram_delta', 0)} MiB | "
                f"{r.get('rss', 0)} MiB | "
                f"{status_icon} |\n"
            )

        if failed:
            f.write(f"\n**Falhas:** {len(failed)} ({', '.join(str(r['n_ctx'] // 1024) + 'k' for r in failed)})\n")

    log(f"Relatorio: {out_path}")
    return out_path


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
    parser.add_argument("--output", type=str, help="Arquivo de saida (padrao: data/logs/benchmark_<ts>.md)")
    parser.add_argument("--resume", type=str, help="Retomar de checkpoint JSON")
    args = parser.parse_args()

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

    # Carregar checkpoint se --resume
    results = []
    checkpoint_path = TEMP_DIR / f"bench_partial_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    if args.resume:
        loaded = load_checkpoint(Path(args.resume))
        if loaded:
            results = loaded
            checkpoint_path = Path(args.resume)
            log(f"Checkpoint: {len(results)} resultado(s) carregados")

    # Filtrar contextos ja testados
    tested = {r["n_ctx"] for r in results}
    remaining = [c for c in contexts if c not in tested]
    if tested:
        log(f"Skip: {len(tested)} contexto(s) ja testados, {len(remaining)} restantes")

    if not remaining:
        log("Nenhum teste restante")
    else:
        log(f"\nIniciando sweep...")

    # Executar testes
    stopped = False
    for i, n_ctx in enumerate(remaining, 1):
        if stopped:
            break

        log(f"\n{'=' * 60}")
        log(f"[{i}/{len(remaining)}] N_CTX={n_ctx:,} ({n_ctx // 1024}k)")
        log(f"{'=' * 60}")

        stop_server()

        if not start_server(n_ctx):
            log(f"ERRO: Falha ao iniciar com N_CTX={n_ctx}")
            results.append({"n_ctx": n_ctx, "status": "fail", "tokens_gen": 0, "tok_per_sec": 0})
            save_checkpoint(results, checkpoint_path)
            continue

        result = run_test(pdf_text, n_ctx, args.fill, args.max_tokens)

        if result is None:
            results.append({"n_ctx": n_ctx, "status": "fail", "tokens_gen": 0, "tok_per_sec": 0})
        else:
            results.append(result)
            if result.get("status") in ("oom", "vram_exhausted"):
                stopped = True
                log(f"!! Sweep interrompido em N_CTX={n_ctx} ({result['status']})")

        save_checkpoint(results, checkpoint_path)

    stop_server()

    if not results:
        log("Nenhum teste executado")
        sys.exit(1)

    # Relatorio
    report_path = generate_report(results, args)

    # Resumo
    log(f"\n{'=' * 60}")
    log("RESUMO")
    log(f"{'=' * 60}")
    for r in results:
        icon = "✓" if r.get("status") == "ok" else "✗"
        log(f"  {icon} {r['n_ctx'] // 1024}k: {r.get('tok_per_sec', 0)} tok/s, "
            f"VRAM {r.get('vram_used', '?')}/{r.get('vram_free', '?')} MiB, "
            f"status={r.get('status', '?')}")
    log(f"\nRelatorio: {report_path}")
    log(f"Checkpoint: {checkpoint_path}")


if __name__ == "__main__":
    main()
