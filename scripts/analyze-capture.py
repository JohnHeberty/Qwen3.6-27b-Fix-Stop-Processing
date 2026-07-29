#!/usr/bin/env python3
"""
analyze-capture.py — analisa logs do vLLM e gera relatório de diagnóstico.

Lê:
  data/logs/vllm.log                     (log principal do vLLM)
  data/logs/capture/*.log                (captura de debug, se ativa)

Emite:
  - relatório legível com contadores de warnings, erros e eventos
  - estatísticas de startup e performance

Diferente do analyze-capture.py do llama.cpp (que parseava token-a-token),
este script foca em:
  - erros e warnings do vLLM
  - tempos de startup (carregamento, compilação, warmup)
  - uso de memória VRAM
  - problemas de conexão (500s, timeouts)

Uso:
  python3 scripts/analyze-capture.py [--log-file PATH] [--since HH:MM] [--jsonl out.jsonl]
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = PROJECT_ROOT / "data" / "logs" / "vllm.log"


def parse_vllm_log(log_path: str, since: str | None = None) -> dict:
    """Parse vLLM log file and extract events."""
    events = {
        "startup": [],
        "warnings": [],
        "errors": [],
        "kv_cache": [],
        "memory": [],
        "requests": [],
        "connections": [],
    }

    if not os.path.exists(log_path):
        print(f"  Log não encontrado: {log_path}")
        return events

    since_time = None
    if since:
        try:
            since_time = datetime.strptime(since, "%H:%M").time()
        except ValueError:
            print(f"  AVISO: formato --since inválido (use HH:MM): {since}")

    with open(log_path, "r", errors="replace") as f:
        for line in f:
            # Extract timestamp
            ts_match = re.search(r"(\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            if ts_match:
                try:
                    ts = datetime.strptime(f"2026-{ts_match.group(1)}", "%Y-%m-%d %H:%M:%S")
                    if since_time and ts.time() < since_time:
                        continue
                except ValueError:
                    pass

            # Classify line
            if "WARNING" in line:
                events["warnings"].append(line.strip())
            elif "ERROR" in line or "Traceback" in line or "Exception" in line:
                events["errors"].append(line.strip())
            elif "GPU KV cache size" in line:
                events["kv_cache"].append(line.strip())
            elif "memory" in line.lower() and ("GiB" in line or "MiB" in line):
                events["memory"].append(line.strip())
            elif "non-default args" in line:
                events["startup"].append(line.strip())
            elif "took" in line and ("seconds" in line or "s" in line):
                events["startup"].append(line.strip())
            elif "Connection" in line and ("error" in line or "refused" in line):
                events["connections"].append(line.strip())
            elif "500" in line or "InternalServer" in line:
                events["errors"].append(line.strip())

    return events


def print_report(events: dict, log_path: str):
    """Print formatted diagnostic report."""
    print(f"\n{'='*60}")
    print(f"  Relatório de Diagnóstico — vLLM")
    print(f"{'='*60}")
    print(f"  Log: {log_path}")
    print()

    # Startup
    if events["startup"]:
        print(f"  STARTUP ({len(events['startup'])} eventos)")
        print(f"  {'-'*40}")
        for e in events["startup"][:10]:
            # Truncate long lines
            if len(e) > 120:
                e = e[:117] + "..."
            print(f"    {e}")
        if len(events["startup"]) > 10:
            print(f"    ... +{len(events['startup'])-10} mais")
        print()

    # KV Cache
    if events["kv_cache"]:
        print(f"  KV CACHE ({len(events['kv_cache'])} entradas)")
        print(f"  {'-'*40}")
        for e in events["kv_cache"]:
            print(f"    {e}")
        print()

    # Memory
    if events["memory"]:
        print(f"  MEMÓRIA ({len(events['memory'])} entradas)")
        print(f"  {'-'*40}")
        for e in events["memory"][-5:]:  # Last 5
            if len(e) > 120:
                e = e[:117] + "..."
            print(f"    {e}")
        print()

    # Warnings
    if events["warnings"]:
        print(f"  WARNINGS ({len(events['warnings'])})")
        print(f"  {'-'*40}")
        # Deduplicate
        unique_warnings = list(dict.fromkeys(events["warnings"]))
        for e in unique_warnings[:15]:
            if len(e) > 120:
                e = e[:117] + "..."
            print(f"    {e}")
        if len(unique_warnings) > 15:
            print(f"    ... +{len(unique_warnings)-15} mais")
        print()

    # Errors
    if events["errors"]:
        print(f"  ERROS ({len(events['errors'])})")
        print(f"  {'-'*40}")
        for e in events["errors"][:20]:
            if len(e) > 120:
                e = e[:117] + "..."
            print(f"    {e}")
        if len(events["errors"]) > 20:
            print(f"    ... +{len(events['errors'])-20} mais")
        print()

    # Connections
    if events["connections"]:
        print(f"  PROBLEMAS DE CONEXÃO ({len(events['connections'])})")
        print(f"  {'-'*40}")
        for e in events["connections"][:10]:
            if len(e) > 120:
                e = e[:117] + "..."
            print(f"    {e}")
        print()

    # Summary
    print(f"  RESUMO")
    print(f"  {'-'*40}")
    print(f"    Startup events:    {len(events['startup'])}")
    print(f"    KV cache entries:  {len(events['kv_cache'])}")
    print(f"    Memory entries:    {len(events['memory'])}")
    print(f"    Warnings:          {len(events['warnings'])}")
    print(f"    Errors:            {len(events['errors'])}")
    print(f"    Connection issues: {len(events['connections'])}")

    # Health assessment
    print()
    if events["errors"]:
        print(f"  ⚠️  STATUS: ERROS DETECTADOS — investigue acima")
    elif events["connections"]:
        print(f"  ⚠️  STATUS: PROBLEMAS DE CONEXÃO — vLLM pode estar offline")
    elif events["warnings"]:
        print(f"  ✓ STATUS: Funcional com warnings ({len(events['warnings'])})")
    else:
        print(f"  ✓ STATUS: Limpo — nenhum erro ou warning")

    print(f"{'='*60}\n")


def export_jsonl(events: dict, output_path: str):
    """Export events as JSONL."""
    with open(output_path, "w") as f:
        for category, items in events.items():
            for item in items:
                record = {
                    "category": category,
                    "message": item,
                    "source": "vllm-log",
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"  JSONL exportado: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Análise de logs do vLLM"
    )
    parser.add_argument(
        "--log-file",
        default=str(DEFAULT_LOG),
        help=f"Arquivo de log (default: {DEFAULT_LOG})",
    )
    parser.add_argument(
        "--since",
        help="Filtrar desde HH:MM",
    )
    parser.add_argument(
        "--jsonl",
        help="Exportar como JSONL para PATH",
    )
    args = parser.parse_args()

    events = parse_vllm_log(args.log_file, since=args.since)
    print_report(events, args.log_file)

    if args.jsonl:
        export_jsonl(events, args.jsonl)


if __name__ == "__main__":
    main()
