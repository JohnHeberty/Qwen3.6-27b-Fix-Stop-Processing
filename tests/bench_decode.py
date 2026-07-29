#!/usr/bin/env python3
"""
bench_decode.py — mede decode tok/s de forma comparável entre engines.

Agnóstico de engine: fala só OpenAI-compatible chat/completions com streaming.
Serve para llama-server e para vLLM sem alteração, que é o ponto — sem o mesmo
prompt e a mesma definição de tok/s, comparar as duas é chute.

Conta tokens pelo `usage.completion_tokens` do servidor (via
`stream_options.include_usage`), NUNCA por número de chunks SSE — um chunk pode
trazer zero, um ou vários tokens.

Cada execução usa um nonce único no início do prompt para invalidar o prefix
cache; sem isso a 2a execução em diante mede cache, não geração.

Uso:
    python3 tests/bench_decode.py --label "llamacpp-27b-q5"
    python3 tests/bench_decode.py --prompt-tokens 24000 --runs 5
"""

import argparse
import json
import statistics
import sys
import time
import uuid

import requests

# Parágrafo-semente repetido até atingir o tamanho de prompt pedido. Texto técnico
# em vez de lorem ipsum para o tokenizador se comportar como em uso real.
SEED = (
    "O servidor de inferência expõe uma API compatível com OpenAI na porta 8000. "
    "A janela de contexto é dividida entre o prompt de entrada e a reserva de saída. "
    "O cache de chave-valor cresce linearmente com o número de tokens processados, "
    "e a quantização desse cache é o principal parâmetro que troca VRAM por contexto. "
)

QUESTION = (
    "\n\nCom base apenas no texto acima, escreva um resumo técnico detalhado em "
    "português explicando como a janela de contexto é dividida e por que a "
    "quantização do cache importa. Seja minucioso e extenso."
)


def build_prompt(target_tokens: int) -> str:
    """~4 chars por token em português; aproximação suficiente — o tamanho real
    vem do `usage.prompt_tokens` que o servidor devolve e é o que reportamos."""
    repeats = max(1, (target_tokens * 4) // len(SEED))
    return (SEED * repeats) + QUESTION


def one_run(base_url, model, prompt, max_tokens, timeout):
    """Uma medição. Devolve dict ou None se falhar."""
    nonce = uuid.uuid4().hex
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": f"[{nonce}]\n{prompt}"}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    start = time.perf_counter()
    first_tok = None
    last_tok = None
    usage = None
    server_timings = None

    try:
        r = requests.post(
            f"{base_url}/v1/chat/completions", json=payload, stream=True, timeout=timeout
        )
    except requests.RequestException as e:
        print(f"    ERRO de conexão: {e}")
        return None

    if r.status_code != 200:
        print(f"    ERRO HTTP {r.status_code}: {r.text[:200]}")
        return None

    for line in r.iter_lines():
        if not line:
            continue
        d = line.decode("utf-8")
        if not d.startswith("data: ") or d == "data: [DONE]":
            continue
        try:
            chunk = json.loads(d[6:])
        except json.JSONDecodeError:
            continue

        if chunk.get("usage"):
            usage = chunk["usage"]
        if chunk.get("timings"):          # llama.cpp expõe; vLLM não
            server_timings = chunk["timings"]

        for ch in chunk.get("choices", []):
            delta = ch.get("delta", {})
            # O raciocínio conta: é token gerado, e um modelo thinking emite
            # bastante dele antes do content. Ignorar inflaria o tok/s.
            # O nome do campo MUDA por engine: llama.cpp manda `reasoning_content`
            # (--reasoning-format deepseek), o vLLM 0.26 manda `reasoning`.
            if (delta.get("content")
                    or delta.get("reasoning_content")
                    or delta.get("reasoning")):
                now = time.perf_counter()
                if first_tok is None:
                    first_tok = now
                last_tok = now

    if not usage:
        print("    ERRO: servidor não devolveu `usage` — sem isso não há medição confiável.")
        return None
    if first_tok is None:
        print("    ERRO: nenhum token gerado.")
        return None

    completion = usage.get("completion_tokens", 0)
    decode_s = (last_tok - first_tok) if last_tok > first_tok else 0.0

    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": completion,
        "ttft_s": round(first_tok - start, 3),
        "decode_s": round(decode_s, 3),
        "decode_tps": round(completion / decode_s, 2) if decode_s > 0 else 0.0,
        "wall_s": round(time.perf_counter() - start, 3),
        "server_decode_tps": round(server_timings.get("predicted_per_second", 0), 2)
        if server_timings else None,
        "server_prefill_tps": round(server_timings.get("prompt_per_second", 0), 2)
        if server_timings else None,
    }


def main():
    p = argparse.ArgumentParser(description="Decode tok/s comparável entre engines")
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--model", default="qwen3")
    p.add_argument("--prompt-tokens", type=int, default=8000, help="tamanho-alvo do prompt")
    p.add_argument("--max-tokens", type=int, default=512, help="tokens a gerar por execução")
    p.add_argument("--warmup", type=int, default=3)
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--label", default="sem-rotulo", help="identificação desta configuração")
    p.add_argument("--output", help="grava JSON com o resultado")
    a = p.parse_args()

    prompt = build_prompt(a.prompt_tokens)

    print(f"\n{'=' * 62}")
    print(f"  {a.label}")
    print(f"  {a.base_url}  modelo={a.model}")
    print(f"  prompt-alvo≈{a.prompt_tokens} tok · gerando {a.max_tokens} tok/execução")
    print(f"  {a.warmup} warm-up + {a.runs} medidas · nonce por execução (sem prefix cache)")
    print(f"{'=' * 62}\n")

    for i in range(a.warmup):
        print(f"  warm-up {i + 1}/{a.warmup}...", flush=True)
        if one_run(a.base_url, a.model, prompt, a.max_tokens, a.timeout) is None:
            print("\n  Warm-up falhou — abortando.")
            return 1

    runs = []
    for i in range(a.runs):
        print(f"  medida {i + 1}/{a.runs}...", end=" ", flush=True)
        r = one_run(a.base_url, a.model, prompt, a.max_tokens, a.timeout)
        if r is None:
            return 1
        runs.append(r)
        print(f"{r['decode_tps']} tok/s · TTFT {r['ttft_s']}s")

    def med(k):
        vals = [r[k] for r in runs if r.get(k) is not None]
        return round(statistics.median(vals), 2) if vals else None

    summary = {
        "label": a.label,
        "base_url": a.base_url,
        "model": a.model,
        "runs": a.runs,
        "prompt_tokens": runs[0]["prompt_tokens"],
        "max_tokens": a.max_tokens,
        "decode_tps_median": med("decode_tps"),
        "decode_tps_min": min(r["decode_tps"] for r in runs),
        "decode_tps_max": max(r["decode_tps"] for r in runs),
        "ttft_s_median": med("ttft_s"),
        "completion_tokens_median": med("completion_tokens"),
        "server_decode_tps_median": med("server_decode_tps"),
        "server_prefill_tps_median": med("server_prefill_tps"),
        "detail": runs,
    }

    print(f"\n{'-' * 62}")
    print(f"  prompt real        : {summary['prompt_tokens']} tokens")
    print(f"  decode tok/s       : {summary['decode_tps_median']} "
          f"(min {summary['decode_tps_min']} / max {summary['decode_tps_max']})")
    print(f"  TTFT               : {summary['ttft_s_median']} s")
    print(f"  tokens gerados     : {summary['completion_tokens_median']}")
    if summary["server_decode_tps_median"] is not None:
        print(f"  decode t/s (server): {summary['server_decode_tps_median']}")
        print(f"  prefill t/s        : {summary['server_prefill_tps_median']}")
    print(f"{'-' * 62}\n")

    if a.output:
        with open(a.output, "w") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"  → {a.output}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
