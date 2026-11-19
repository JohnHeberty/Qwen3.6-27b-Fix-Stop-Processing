"""Utilitários comuns dos testes do kit LoRA (só stdlib).

Tudo aponta por padrão para a instância de TESTE (http://127.0.0.1:18021). A produção
(18020) é recusada, a menos que ALLOW_PROD=1 (ex.: para comparar números).
"""
import collections
import json
import os
import re
import time
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("LORA_URL", "http://127.0.0.1:18021")
BASE_MODEL = "qwen3.8-27b"
LORA_MODEL = os.environ.get("LORA_NAME", "opencode-adapted")

# Amostragem do card do adaptador (treino e avaliação): temperature 0.8, top_p 1.0,
# thinking off. O card NÃO diz top_k nem presence_penalty; a avaliação foi num
# `vllm serve` sem --override-generation-config, logo presence_penalty=0 e top_k=20
# (vem do generation_config.json do Qwen3.8, que o vLLM aplica por padrão).
CARD_SAMPLING = {"temperature": 0.8, "top_p": 1.0, "presence_penalty": 0.0}
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}

# Braços do A/B. "extra" é mesclado no corpo do request.
ARMS = {
    # adaptador como no card: thinking off, amostragem do treino
    "lora-nothink": {"model": LORA_MODEL, "extra": {**CARD_SAMPLING, **NO_THINK}},
    # base nas MESMAS condições (controle direto do efeito do adaptador)
    "base-nothink": {"model": BASE_MODEL, "extra": {**CARD_SAMPLING, **NO_THINK}},
    # base como a produção serve hoje: thinking ON (effort medium), presence_penalty 1.0,
    # temp 1.0/top_p 0.95/top_k 20, teto de thinking 8192 e alarme de repetição (patch local).
    # Nenhum campo de amostragem é enviado: valem os defaults do servidor.
    "base-think-prod": {"model": BASE_MODEL, "extra": {}},
    # opcional: adaptador com os defaults de amostragem da produção (o que um cliente
    # que só desliga o thinking receberia: presence_penalty 1.0, temp 1.0)
    "lora-nothink-prod": {"model": LORA_MODEL, "extra": {**NO_THINK}},
}
DEFAULT_ARMS = ["lora-nothink", "base-nothink", "base-think-prod"]


def check_url(url):
    if ":18020" in url and os.environ.get("ALLOW_PROD") != "1":
        raise SystemExit(f"{url} é a PRODUÇÃO. Os testes do kit rodam contra a instância LoRA "
                         "(18021). Use ALLOW_PROD=1 só se souber o que está fazendo.")
    return url.rstrip("/")


def http_json(url, payload=None, timeout=1800):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def chat(url, body, timeout=1800):
    """POST /v1/chat/completions não-streaming. Devolve (json, segundos)."""
    t0 = time.time()
    d = http_json(url + "/v1/chat/completions", body, timeout)
    return d, time.time() - t0


def chat_stream(url, body, timeout=1800):
    """Streaming: devolve dict com texto, reasoning, tokens, ttft e tok/s de decode."""
    body = {**body, "stream": True, "stream_options": {"include_usage": True}}
    req = urllib.request.Request(url + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t0 = time.time()
    first = None
    content, reasoning, usage, finish = [], [], {}, None
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            p = line[6:]
            if p == "[DONE]":
                break
            try:
                ch = json.loads(p)
            except ValueError:
                continue
            if ch.get("usage"):
                usage = ch["usage"]
            for c in ch.get("choices", []):
                dl = c.get("delta") or {}
                piece = (dl.get("content") or "") + (dl.get("reasoning") or dl.get("reasoning_content") or "")
                if piece and first is None:
                    first = time.time()
                if dl.get("content"):
                    content.append(dl["content"])
                if dl.get("reasoning") or dl.get("reasoning_content"):
                    reasoning.append(dl.get("reasoning") or dl.get("reasoning_content"))
                if c.get("finish_reason"):
                    finish = c["finish_reason"]
    t1 = time.time()
    n = usage.get("completion_tokens", 0)
    dec = (t1 - first) if first else 0.0
    return {"content": "".join(content), "reasoning": "".join(reasoning), "finish": finish,
            "completion_tokens": n, "prompt_tokens": usage.get("prompt_tokens", 0),
            "ttft": round((first or t1) - t0, 3), "seconds": round(t1 - t0, 3),
            # decode tok/s exclui o TTFT (prefill); o 1o token conta como já emitido
            "decode_tok_s": round((n - 1) / dec, 1) if dec > 0 and n > 1 else 0.0}


RE_METRIC = re.compile(r"^(vllm:spec_decode_num_(?:drafts|draft_tokens|accepted_tokens)_total)\{[^}]*\}\s+([0-9.eE+-]+)")


def spec_counters(url):
    """Contadores cumulativos de spec decoding do /metrics (somados entre labels)."""
    out = collections.Counter()
    try:
        with urllib.request.urlopen(url + "/metrics", timeout=30) as r:
            for line in r.read().decode("utf-8", "replace").splitlines():
                m = RE_METRIC.match(line)
                if m:
                    out[m.group(1).split("num_")[1].replace("_total", "")] += float(m.group(2))
    except (urllib.error.URLError, OSError):
        pass
    return dict(out)


def spec_delta(c0, c1):
    d = {k: c1.get(k, 0) - c0.get(k, 0) for k in ("drafts", "draft_tokens", "accepted_tokens")}
    d["accept_rate"] = round(d["accepted_tokens"] / d["draft_tokens"], 3) if d["draft_tokens"] else None
    # tokens emitidos por passo de verify = 1 (bônus/correção) + aceitos/rodada
    d["mean_accept_len"] = round(1 + d["accepted_tokens"] / d["drafts"], 2) if d["drafts"] else None
    return d


def loop_score(text, tail_lines=200):
    """Fração das últimas linhas não vazias que se repetem >= 3x (mesma métrica do scripts/loop_stress.py)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 20:
        return 0.0
    tail = lines[-tail_lines:]
    c = collections.Counter(tail)
    return round(sum(v for v in c.values() if v >= 3) / len(tail), 3)


def distinct_word_ratio(text, last=300):
    """Gotcha 49 do upstream: texto colapsado tem razão de palavras distintas ~0,05 (normal 0,77-0,83)."""
    w = re.findall(r"\w+", text[-last * 12:])[-last:]
    return round(len(set(w)) / len(w), 3) if len(w) >= 50 else None


def is_degenerate(text):
    ls = loop_score(text)
    dw = distinct_word_ratio(text)
    return ls > 0.5 or (dw is not None and dw < 0.2)


def list_models(url):
    d = http_json(url + "/v1/models", timeout=30)
    return {m["id"]: m for m in d.get("data", [])}
