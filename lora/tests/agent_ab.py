#!/usr/bin/env python3
"""A/B agêntico multi-turno: base vs adaptador LoRA (e controle com thinking da produção).

Um mini-harness que imita o OpenCode 2.2.7 (o harness do treino do adaptador): mesmo system
prompt e MESMOS schemas de ferramentas (read/write/edit/glob/grep/shell), capturados do
próprio OpenCode 2.2.7 em tests/opencode2_capture.json. O modelo trabalha num diretório
temporário até parar de chamar ferramentas (ou estourar --max-turns); no fim o harness
restaura os testes originais e roda a suíte: sucesso = exit 0.

  python3 -I lora/tests/agent_ab.py --reps 2 --out lora/results/ab-<ts>
  python3 -I lora/tests/agent_ab.py --arms lora-nothink,base-nothink --tasks slugify-bug --reps 1
  python3 -I lora/tests/agent_ab.py --selftest      # sem servidor: valida tarefas e ferramentas

Métricas por episódio (JSONL) e por braço (summary.json + tabela):
  sucesso, turnos (chamadas ao modelo), tool calls, erros de ferramenta, maior sequência de
  tool calls IDÊNTICAS (o "repete o mesmo comando" do card), finish_reason, turnos
  degenerados (repetição de linhas no fim / razão de palavras distintas -- gotcha 49),
  tokens gerados / de raciocínio, tok/s ponta a ponta, e aceitação do DFlash2 via /metrics
  (só com --concurrency 1, o default: os contadores são globais do servidor).

SEGURANÇA: o `shell` executa comandos escritos pelo modelo. Roda como `nobody` (setpriv),
em diretório próprio, com timeout e PATH mínimo -- isolamento leve, não um sandbox. Não
rode isto com um modelo/adaptador em que você não confia.
"""
import argparse
import collections
import concurrent.futures as cf
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
from tasks import TASKS, TEST_CMD  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURE = json.load(open(os.path.join(HERE, "opencode2_capture.json")))
TOOL_NAMES = ["read", "write", "edit", "glob", "grep", "shell"]
TOOLS = [t for t in CAPTURE["tools"] if t["function"]["name"] in TOOL_NAMES]
assert len(TOOLS) == len(TOOL_NAMES), "opencode2_capture.json sem alguma ferramenta esperada"
MAX_OUT = 30000  # caracteres de saída de ferramenta devolvidos ao modelo
MAX_MODEL_LEN = 142080  # max_model_len do servidor; o max_tokens de cada chamada é encolhido para caber
# Histórico de "sessão anterior" (--prefill-tokens): o agente lê arquivos reais da stdlib copiados
# para vendor/, como num OpenCode já fundo numa sessão. É a faixa (60k-120k) em que os loops apareciam.
VENDOR_SRC = os.path.dirname(os.__file__)
VENDOR_FILES = ["argparse.py", "configparser.py", "statistics.py", "textwrap.py", "csv.py", "shlex.py",
                "json/decoder.py", "json/encoder.py", "email/message.py", "logging/__init__.py",
                "http/client.py", "pathlib/_local.py", "tarfile.py", "zipfile/__init__.py", "difflib.py"]
CHARS_PER_TOKEN = 3.3


def prefill_history(sb, root, target_tokens):
    """Mensagens de uma sessão anterior: user pede revisão de vendor/, assistente lê arquivo a
    arquivo (tool calls reais, resultados reais), até ~target_tokens."""
    msgs = [{"role": "user", "content": "Before the real task, get familiar with the vendored libraries in "
             "vendor/: read each file and keep its API in mind, we will need it later."}]
    budget = target_tokens * CHARS_PER_TOKEN
    used, k = 0, 0
    for rel in VENDOR_FILES:
        src = os.path.join(VENDOR_SRC, rel)
        if not os.path.exists(src):
            continue
        dst = os.path.join(root, "vendor", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        if used >= budget:
            continue
        k += 1
        cid = f"call_prefill_{k}"
        args = json.dumps({"path": "vendor/" + rel})
        res = str(sb.call("read", {"path": "vendor/" + rel}))[-MAX_OUT:]
        msgs.append({"role": "assistant", "content": "",
                     "tool_calls": [{"id": cid, "type": "function", "function": {"name": "read", "arguments": args}}]})
        msgs.append({"role": "tool", "tool_call_id": cid, "content": res})
        used += len(res)
    msgs.append({"role": "assistant", "content": f"I have reviewed {k} vendored modules in vendor/. Ready for the task."})
    return msgs


def system_prompt(workdir):
    s = CAPTURE["system_prompt"]
    # Tira a seção Code Mode/skills: ela descreve ferramentas (execute, skill, subagent...)
    # que este harness não oferece. O resto (Harness, Communication, env) fica igual.
    a, b = s.find("# Code Mode"), s.find("Today's date:")
    if a != -1 and b > a:
        s = s[:a] + s[b:]
    return s.replace("{WORKDIR}", workdir).replace("{DATE}", time.strftime("%a %b %d %Y"))


# ------------------------------------------------------------------------- ferramentas
class Sandbox:
    def __init__(self, root):
        self.root = os.path.realpath(root)
        self.as_nobody = os.geteuid() == 0 and shutil.which("setpriv") is not None

    def path(self, p):
        p = p or "."
        full = os.path.realpath(p if os.path.isabs(p) else os.path.join(self.root, p))
        if full != self.root and not full.startswith(self.root + os.sep):
            raise ValueError(f"path outside the working directory: {p}")
        return full

    def fix_perms(self):
        if self.as_nobody:
            for d, dirs, files in os.walk(self.root):
                os.chown(d, 65534, 65534)
                for f in files:
                    os.chown(os.path.join(d, f), 65534, 65534)

    def run(self, cmd, workdir=None, timeout_s=120):
        cwd = self.path(workdir) if workdir else self.root
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": self.root, "LANG": "C.UTF-8",
               "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": self.root}
        argv = ["bash", "-c", cmd]
        if self.as_nobody:
            argv = ["setpriv", "--reuid=65534", "--regid=65534", "--clear-groups", "--"] + argv
        try:
            p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True,
                               timeout=timeout_s, stdin=subprocess.DEVNULL)
            out = (p.stdout or "") + (p.stderr or "")
            return p.returncode, out
        except subprocess.TimeoutExpired as e:
            out = ((e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
            return 124, out + f"\n[command timed out after {timeout_s}s]"

    # --- as ferramentas, com a semântica do OpenCode 2 o mais próxima possível -----------
    def t_read(self, path, offset=1, limit=2000):
        full = self.path(path)
        if os.path.isdir(full):
            ents = sorted(e + ("/" if os.path.isdir(os.path.join(full, e)) else "") for e in os.listdir(full))
            ents = ents[max(0, (offset or 1) - 1):][: limit or 2000]
            return "\n".join(ents) if ents else "(empty directory)"
        lines = open(full, errors="replace").read().splitlines()
        start = max(1, offset or 1)
        sel = lines[start - 1: start - 1 + min(limit or 2000, 2000)]
        return "\n".join(f"{i}: {ln}" for i, ln in enumerate(sel, start)) or "(empty file)"

    def t_write(self, path, content):
        full = self.path(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)
        self.fix_perms()
        return f"Wrote {len(content)} characters to {os.path.relpath(full, self.root)}"

    def t_edit(self, path, oldString, newString, replaceAll=False):
        full = self.path(path)
        s = open(full).read()
        if oldString == newString:
            raise ValueError("oldString and newString must differ")
        n = s.count(oldString)
        if n == 0:
            raise ValueError("oldString not found in file")
        if n > 1 and not replaceAll:
            raise ValueError(f"oldString found {n} times; add more context or set replaceAll")
        s = s.replace(oldString, newString) if replaceAll else s.replace(oldString, newString, 1)
        open(full, "w").write(s)
        return f"Edited {os.path.relpath(full, self.root)} ({n if replaceAll else 1} replacement)"

    def t_glob(self, pattern, path=None, hidden=False, limit=100):
        base = pathlib.Path(self.path(path))
        out = []
        for p in sorted(base.glob(pattern)):
            rel = str(p.relative_to(self.root))
            if not hidden and any(part.startswith(".") for part in pathlib.Path(rel).parts):
                continue
            out.append(rel)
        return "\n".join(out[: limit or 100]) or "No files found"

    def t_grep(self, pattern, path=None, include=None, literal=False, caseSensitive=True, limit=100):
        base = self.path(path)
        rx = re.compile(re.escape(pattern) if literal else pattern, 0 if caseSensitive else re.I)
        files = [base] if os.path.isfile(base) else [os.path.join(d, f) for d, _, fs in os.walk(base) for f in fs]
        out = []
        for f in sorted(files):
            rel = os.path.relpath(f, self.root)
            if any(part.startswith(".") for part in pathlib.Path(rel).parts):
                continue
            if include and not fnmatch.fnmatch(os.path.basename(f), include):
                continue
            try:
                for i, ln in enumerate(open(f, errors="replace"), 1):
                    if rx.search(ln):
                        out.append(f"{rel}:{i}: {ln.rstrip()[:300]}")
            except (OSError, UnicodeDecodeError):
                continue
        return "\n".join(out[: limit or 100]) or "No matches found"

    def t_shell(self, command, workdir=None, timeout=120000, background=False):
        if background:
            return "Background commands are not supported in this environment."
        t = 120 if not timeout else max(1, min(int(timeout) // 1000, 300))
        rc, out = self.run(command, workdir, t)
        return f"{out}\n[exit code: {rc}]"

    def call(self, name, args):
        fn = getattr(self, "t_" + name, None)
        if fn is None:
            raise ValueError(f"unknown tool: {name}")
        return fn(**args)


def setup_task(task, root):
    for rel, content in TASKS[task]["files"].items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(content)


def grade(task, sb):
    # restaura os testes originais (o modelo não pode "passar" editando o teste)
    for rel, content in TASKS[task]["files"].items():
        if rel.startswith("tests/"):
            p = os.path.join(sb.root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").write(content)
    sb.fix_perms()
    rc, out = sb.run(TEST_CMD, None, 120)
    return rc == 0, out[-2000:]


# ----------------------------------------------------------------------------- episódio
def episode(url, arm, task, rep, max_turns, max_tokens, keep_dir, prefill_tokens=0):
    spec = C.ARMS[arm]
    root = tempfile.mkdtemp(prefix=f"lora-ab-{arm}-{task}-{rep}-", dir=keep_dir)
    sb = Sandbox(root)
    setup_task(task, root)
    sb.fix_perms()
    os.chmod(root, 0o755)
    msgs = [{"role": "system", "content": system_prompt(root)}]
    if prefill_tokens:
        msgs += prefill_history(sb, root, prefill_tokens)
        sb.fix_perms()
    msgs.append({"role": "user", "content": TASKS[task]["prompt"]})
    ep = {"arm": arm, "model": spec["model"], "task": task, "rep": rep, "turns": 0, "tool_calls": 0,
          "tool_errors": 0, "finish": collections.Counter(), "degenerate_turns": 0, "completion_tokens": 0,
          "reasoning_tokens": 0, "max_prompt_tokens": 0, "gen_seconds": 0.0, "max_identical_streak": 0,
          "ended_by": "max_turns", "workdir": root}
    last_sig, streak = None, 0
    last_prompt, n_at_last = 0, 0
    c0 = C.spec_counters(url)
    t_start = time.time()
    for turn in range(max_turns):
        seed = int(hashlib.sha1(f"{task}/{rep}/{turn}".encode()).hexdigest()[:8], 16)
        # cabe no contexto? estima o prompt pelo último prompt_tokens + o que entrou desde então
        est_prompt = (last_prompt + sum(len(json.dumps(x)) for x in msgs[n_at_last:]) / CHARS_PER_TOKEN
                      if last_prompt else sum(len(json.dumps(x)) for x in msgs) / CHARS_PER_TOKEN)
        mt = min(max_tokens, int(MAX_MODEL_LEN - est_prompt - 2000))
        if mt < 1024:
            ep["ended_by"] = "context_full"
            break
        body = {"model": spec["model"], "messages": msgs, "tools": TOOLS, "tool_choice": "auto",
                "max_tokens": mt, "seed": seed, **spec["extra"]}
        try:
            d, secs = C.chat(url, body, 1800)
        except Exception as e:  # noqa: BLE001  (ex.: 400 de contexto estourado)
            ep["ended_by"] = "error"
            ep["error"] = repr(e)[:500]
            if hasattr(e, "read"):
                try:
                    ep["error"] += " | " + e.read().decode(errors="replace")[:500]
                except Exception:  # noqa: BLE001
                    pass
            break
        ep["turns"] += 1
        ep["gen_seconds"] += secs
        u = d.get("usage") or {}
        ep["completion_tokens"] += u.get("completion_tokens", 0)
        ep["reasoning_tokens"] += ((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
        ep["max_prompt_tokens"] = max(ep["max_prompt_tokens"], u.get("prompt_tokens", 0))
        last_prompt, n_at_last = u.get("prompt_tokens", 0), len(msgs)
        ch = d["choices"][0]
        m = ch["message"]
        fr = ch.get("finish_reason")
        ep["finish"][fr] += 1
        text = (m.get("reasoning") or m.get("reasoning_content") or "") + "\n" + (m.get("content") or "")
        if C.is_degenerate(text):
            ep["degenerate_turns"] += 1
        tcs = m.get("tool_calls") or []
        amsg = {"role": "assistant", "content": m.get("content") or ""}
        if tcs:
            amsg["tool_calls"] = [{"id": t["id"], "type": "function", "function": t["function"]} for t in tcs]
        msgs.append(amsg)
        if fr in ("length", "repetition") and not tcs:
            ep["ended_by"] = fr
            break
        if not tcs:
            ep["ended_by"] = "done"
            break
        for t in tcs:
            ep["tool_calls"] += 1
            name = t["function"]["name"]
            raw = t["function"].get("arguments") or "{}"
            sig = (name, raw)
            streak = streak + 1 if sig == last_sig else 1
            last_sig = sig
            ep["max_identical_streak"] = max(ep["max_identical_streak"], streak)
            try:
                res = sb.call(name, json.loads(raw))
            except Exception as e:  # noqa: BLE001
                ep["tool_errors"] += 1
                res = f"Error: {e}"
            msgs.append({"role": "tool", "tool_call_id": t["id"], "content": str(res)[-MAX_OUT:]})
    ep["wall_seconds"] = round(time.time() - t_start, 1)
    ep["spec"] = C.spec_delta(c0, C.spec_counters(url))
    ep["success"], ep["test_tail"] = grade(task, sb)
    ep["finish"] = dict(ep["finish"])
    ep["e2e_tok_s"] = round(ep["completion_tokens"] / ep["gen_seconds"], 1) if ep["gen_seconds"] else 0.0
    ep["looped"] = (ep["degenerate_turns"] > 0 or ep["max_identical_streak"] >= 3
                    or ep["ended_by"] in ("length", "repetition"))
    if not keep_dir:
        shutil.rmtree(root, ignore_errors=True)
    return ep


# ------------------------------------------------------------------------------ resumo
def summarize(eps, valid_spec):
    by = collections.defaultdict(list)
    for e in eps:
        by[e["arm"]].append(e)
    out = {}
    for arm, es in by.items():
        med = lambda k, xs=None: round(statistics.median([e[k] for e in (xs or es)]), 1) if (xs or es) else None  # noqa: E731
        succ = [e for e in es if e["success"]]
        clean = [e for e in es if not e["looped"]]
        fin = collections.Counter()
        for e in es:
            fin.update(e["finish"])
        s = {"n": len(es), "success_rate": round(len(succ) / len(es), 3),
             "loop_rate": round(sum(e["looped"] for e in es) / len(es), 3),
             "median_turns": med("turns"), "median_tool_calls": med("tool_calls"),
             "median_turns_success": med("turns", succ) if succ else None,
             "median_completion_tokens": med("completion_tokens"),
             "median_reasoning_tokens": med("reasoning_tokens"),
             "median_e2e_tok_s": med("e2e_tok_s"), "tool_errors": sum(e["tool_errors"] for e in es),
             "ended_by": dict(collections.Counter(e["ended_by"] for e in es)), "finish": dict(fin),
             "max_identical_streak": max(e["max_identical_streak"] for e in es)}
        if valid_spec:
            for label, xs in (("all", es), ("clean", clean)):
                acc = sum(e["spec"]["accepted_tokens"] for e in xs)
                dr = sum(e["spec"]["draft_tokens"] for e in xs)
                nd = sum(e["spec"]["drafts"] for e in xs)
                s[f"spec_accept_rate_{label}"] = round(acc / dr, 3) if dr else None
                s[f"spec_mean_accept_len_{label}"] = round(1 + acc / nd, 2) if nd else None
        out[arm] = s
    return out


def print_table(summ):
    cols = ["n", "success_rate", "loop_rate", "median_turns", "median_tool_calls", "median_completion_tokens",
            "median_reasoning_tokens", "median_e2e_tok_s", "spec_accept_rate_clean", "spec_mean_accept_len_clean",
            "max_identical_streak"]
    print("\n" + "arm".ljust(20) + "".join(c[:14].rjust(15) for c in cols))
    for arm, s in summ.items():
        print(arm.ljust(20) + "".join(str(s.get(c)).rjust(15) for c in cols))
    for arm, s in summ.items():
        print(f"{arm}: ended_by={s['ended_by']} finish={s['finish']}")


def selftest():
    """Sem servidor: cada tarefa FALHA no estado inicial e as ferramentas funcionam."""
    ok = True
    for task in TASKS:
        root = tempfile.mkdtemp(prefix=f"lora-selftest-{task}-")
        sb = Sandbox(root)
        setup_task(task, root)
        sb.fix_perms()
        os.chmod(root, 0o755)
        passed, tail = grade(task, sb)
        print(f"{task}: estado inicial {'PASSA (ERRADO)' if passed else 'falha (certo)'}")
        ok &= not passed
        assert "1: " in sb.t_read(next(r for r, c in TASKS[task]["files"].items() if c))
        if "solution" in TASKS[task]:  # tarefas difíceis: a solução de referência passa
            for rel, content in TASKS[task]["solution"].items():
                open(os.path.join(root, rel), "w").write(content)
            sb.fix_perms()
            solved, tail = grade(task, sb)
            print(f"{task}: solução de referência {'passa (certo)' if solved else 'FALHA (ERRADO)'}")
            ok &= solved
        assert sb.t_glob("**/*.py") != "No files found"
        assert "test" in sb.t_grep("unittest", "tests")
        rc_out = sb.t_shell("id -u && touch x && ls")
        assert ("65534" in rc_out) == sb.as_nobody, rc_out
        try:
            sb.t_read("../../etc/passwd")
            ok = False
            print("ESCAPE de diretório não bloqueado!")
        except ValueError:
            pass
        shutil.rmtree(root, ignore_errors=True)
    print("SELFTEST", "OK" if ok else "FALHOU", "| shell como nobody:", Sandbox("/tmp").as_nobody)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=C.DEFAULT_URL)
    ap.add_argument("--arms", default=",".join(C.DEFAULT_ARMS), help=f"de: {','.join(C.ARMS)}")
    ap.add_argument("--tasks", default=",".join(TASKS))
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--max-tokens", type=int, default=16384, help="por chamada (OpenCode: limit.output)")
    ap.add_argument("--concurrency", type=int, default=1, help=">1 invalida a aceitação por braço")
    ap.add_argument("--out", default="")
    ap.add_argument("--keep", action="store_true", help="mantém os diretórios de trabalho")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--prefill-tokens", type=int, default=0,
                    help="histórico de sessão anterior (~tokens) antes da tarefa; 0 = sem")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    url = C.check_url(a.url)
    arms = [x for x in a.arms.split(",") if x]
    tasks = [x for x in a.tasks.split(",") if x]
    for x in arms:
        assert x in C.ARMS, f"braço desconhecido: {x}"
    for x in tasks:
        assert x in TASKS, f"tarefa desconhecida: {x}"
    out = a.out or os.path.join(os.path.dirname(HERE), "results", "ab-" + time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out, exist_ok=True)
    keep_dir = os.path.join(out, "work") if a.keep else None
    if keep_dir:
        os.makedirs(keep_dir, exist_ok=True)
    # intercalado (rep, tarefa, braço) para não confundir deriva térmica/cache com o braço
    jobs = [(arm, t, r) for r in range(a.reps) for t in tasks for arm in arms]
    print(f"{len(jobs)} episódios: braços={arms} tarefas={tasks} reps={a.reps} -> {out}", flush=True)
    eps = []
    with open(os.path.join(out, "episodes.jsonl"), "a") as fh:
        def done(ep):
            eps.append(ep)
            fh.write(json.dumps(ep, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[{len(eps)}/{len(jobs)}] {ep['arm']:<17} {ep['task']:<16} r{ep['rep']} "
                  f"ok={ep['success']!s:<5} turns={ep['turns']:<3} tools={ep['tool_calls']:<3} "
                  f"end={ep['ended_by']:<10} loop={ep['looped']!s:<5} tok={ep['completion_tokens']:<6} "
                  f"acc={ep['spec'].get('accept_rate')} {ep['wall_seconds']}s", flush=True)
        if a.concurrency <= 1:
            for j in jobs:
                done(episode(url, *j, a.max_turns, a.max_tokens, keep_dir, a.prefill_tokens))
        else:
            with cf.ThreadPoolExecutor(a.concurrency) as ex:
                for ep in ex.map(lambda j: episode(url, *j, a.max_turns, a.max_tokens, keep_dir, a.prefill_tokens), jobs):
                    done(ep)
    summ = summarize(eps, valid_spec=a.concurrency <= 1)
    json.dump({"args": vars(a), "summary": summ}, open(os.path.join(out, "summary.json"), "w"), indent=1)
    print_table(summ)
    print(f"\nresultados: {out}/episodes.jsonl e {out}/summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
