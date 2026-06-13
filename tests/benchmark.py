#!/usr/bin/env python3
"""
Benchmark oficial — Testa diferentes N_CTX com multiplicadores reiniciando o servidor entre testes.
Usa data/temp/RL_OREILLY_full.md para sobrecarregar o contexto e medir performance real.

Uso:
    python3 tests/benchmark.py                          # Base 32768, multiplicadores 0.5x a 3x
    python3 tests/benchmark.py --base 16384             # Base 16384, multiplicadores padrão
    python3 tests/benchmark.py --multipliers 0.5,1,2    # Multiplicadores específicos
    python3 tests/benchmark.py --fill 90                # Preenchimento fixo (padrão: 90%)
    python3 tests/benchmark.py --resume data/temp/benchmark_partial_XXX.json
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
    import requests
except ImportError:
    print("Instalando requests...")
    subprocess.run([sys.executable, "-m", "pip", "install", "requests", "-q"], check=True)
    import requests

# Configuração
API_URL = "http://localhost:8000/v1/chat/completions"
HEALTH_URL = "http://localhost:8000/health"
PROPS_URL = "http://localhost:8000/props"
PDF_PATH = "data/temp/RL_OREILLY_full.md"
TEMP_DIR = "data/temp"
LOGS_DIR = "data/logs"
README_PATH = "README.md"

# Padrões de multiplicadores padrão
DEFAULT_BASE_CTX = 32768
DEFAULT_MULTIPLIERS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
DEFAULT_FILL_PERCENT = 90


def save_partial_results(results, output_path):
    """Salva resultados parciais em JSON para checkpoint."""
    os.makedirs(TEMP_DIR, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(results),
            "results": results
        }, f, indent=2, ensure_ascii=False)
    print(f"  [checkpoint] {len(results)} resultado(s) salvo(s): {output_path}")


def load_partial_results(input_path):
    """Carrega resultados parciais para retomar benchmark."""
    if not os.path.exists(input_path):
        print(f"ERRO: Arquivo parcial não encontrado: {input_path}")
        return None
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["results"]


def get_vram():
    """Coleta VRAM usada e livre via nvidia-smi."""
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    used, free = result.stdout.strip().split(", ")
    return int(used), int(free)


def get_ram():
    """Coleta RAM do sistema usada e livre via /proc/meminfo."""
    with open("/proc/meminfo", "r") as f:
        lines = f.readlines()
    
    mem_total = mem_available = 0
    for line in lines:
        if line.startswith("MemTotal:"):
            mem_total = int(line.split()[1]) // 1024  # kB to MB
        elif line.startswith("MemAvailable:"):
            mem_available = int(line.split()[1]) // 1024
    
    mem_used = mem_total - mem_available
    return mem_used, mem_available


def get_process_rss():
    """Coleta RSS do processo llama-server em MB."""
    result = subprocess.run(
        ["ps", "-o", "rss=", "-C", "llama-server"],
        capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        # Pode haver múltiplos processos (main + workers)
        total_kb = sum(int(x) for x in result.stdout.strip().split() if x.isdigit())
        return total_kb // 1024
    return 0


def wait_for_server(timeout=120):
    """Aguarda servidor ficar pronto."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(HEALTH_URL, timeout=2)
            if r.status_code == 200:
                return True
        except:
            pass
        time.sleep(2)
    return False


def stop_server():
    """Para o servidor."""
    subprocess.run(["pkill", "-f", "llama-server"], capture_output=True)
    time.sleep(5)


def start_server_with_ctx(n_ctx):
    """Inicia servidor com N_CTX específico, editando .env."""
    print(f"\nIniciando servidor com N_CTX={n_ctx}...")
    
    # Ler .env atual
    env_vars = {}
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env_vars[key] = val
    
    # Atualizar N_CTX
    env_vars["N_CTX"] = str(n_ctx)
    
    # Escrever .env
    with open(".env", "w") as f:
        for key, val in env_vars.items():
            f.write(f"{key}={val}\n")
    
    # Iniciar servidor em background
    subprocess.Popen(
        ["make", "start-bg"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Aguardar ficar pronto
    if not wait_for_server(timeout=120):
        print("ERRO: Servidor não iniciou em 120s")
        return False
    
    time.sleep(5)  # Estabilizar
    return True


def load_pdf():
    """Carrega o PDF completo."""
    if not os.path.exists(PDF_PATH):
        print(f"ERRO: PDF não encontrado em {PDF_PATH}")
        print("Execute primeiro: python3 -c \"import fitz; ...\" para extrair o PDF")
        sys.exit(1)
    
    with open(PDF_PATH, "r", encoding="utf-8") as f:
        return f.read()


def truncate_to_tokens(text, target_tokens):
    """Trunca texto para aproximadamente target_tokens (estimativa: 3.5 chars/token)."""
    target_chars = int(target_tokens * 3.5)
    return text[:target_chars]


def run_test(book_text, test_name, n_ctx, fill_percent, max_output=4096):
    """Executa um teste com o contexto especificado."""
    print(f"\n{'='*70}")
    print(f"Teste: {test_name}")
    print(f"N_CTX: {n_ctx:,} tokens")
    print(f"Preenchimento: {fill_percent}%")
    print(f"{'='*70}")
    
    # Calcular tokens do livro
    target_tokens = int(n_ctx * fill_percent / 100)
    
    # Truncar PDF
    truncated = truncate_to_tokens(book_text, target_tokens)
    actual_chars = len(truncated)
    estimated_tokens = actual_chars // 3.5
    
    print(f"Texto truncado: {actual_chars:,} caracteres (~{estimated_tokens:,.0f} tokens)")
    
    # Construir prompt
    prompt = f"""Você recebeu um livro completo sobre Reinforcement Learning. Analise o conteúdo e forneça:

1. **Resumo Executivo** (3-5 parágrafos): Visão geral do livro, principais temas e objetivos
2. **Estrutura do Livro**: Lista dos principais capítulos/tópicos cobertos
3. **Conceitos-Chave**: Top 10 conceitos mais importantes explicados brevemente
4. **Aplicações Práticas**: Exemplos de aplicações industriais mencionadas
5. **Conclusões Principais**: Insights e recomendações do autor

Conteúdo do livro:

{truncated}
"""
    
    prompt_tokens = len(prompt) // 3.5
    print(f"Prompt total: ~{prompt_tokens:,.0f} tokens (livro + instrução)")
    
    # Coletar VRAM antes
    vram_before_used, vram_before_free = get_vram()
    ram_before_used, ram_before_free = get_ram()
    rss_before = get_process_rss()
    print(f"VRAM antes: {vram_before_used} MiB usada, {vram_before_free} MiB livre")
    print(f"RAM antes: {ram_before_used} MiB usada, {ram_before_free} MiB livre")
    print(f"RSS antes: {rss_before} MiB")
    
    # Fazer request com streaming para medir tempo do primeiro token
    print("Enviando request...")
    start_time = time.time()
    first_token_time = None
    response_text = ""
    token_count = 0
    
    try:
        stream = requests.post(
            API_URL,
            json={
                "model": "qwen3",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_output,
                "temperature": 0.6,
                "stream": True
            },
            stream=True,
            timeout=600
        )
        
        if stream.status_code != 200:
            print(f"ERRO HTTP {stream.status_code}: {stream.text[:500]}")
            return None
        
        for line in stream.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            if first_token_time is None:
                                first_token_time = time.time()
                            response_text += content
                            token_count += 1
                    except:
                        pass
        
        total_time = time.time() - start_time
        prompt_time = (first_token_time - start_time) if first_token_time else total_time
        generation_time = (time.time() - first_token_time) if first_token_time else 0
        
        # Coletar VRAM e RAM depois
        vram_after_used, vram_after_free = get_vram()
        ram_after_used, ram_after_free = get_ram()
        rss_after = get_process_rss()
        
        # Calcular métricas
        tok_per_sec = token_count / generation_time if generation_time > 0 else 0
        
        result = {
            "test_name": test_name,
            "n_ctx": n_ctx,
            "fill_percent": fill_percent,
            "prompt_tokens_est": int(prompt_tokens),
            "tokens_generated": token_count,
            "prompt_time_s": round(prompt_time, 1),
            "generation_time_s": round(generation_time, 1),
            "total_time_s": round(total_time, 1),
            "tok_per_sec": round(tok_per_sec, 1),
            "vram_used_mib": vram_after_used,
            "vram_free_mib": vram_after_free,
            "ram_used_mib": ram_after_used,
            "ram_free_mib": ram_after_free,
            "rss_mib": rss_after,
        }
        
        print(f"\n✓ Resultado:")
        print(f"  Tempo prompt: {prompt_time:.1f}s")
        print(f"  Tempo geração: {generation_time:.1f}s")
        print(f"  Tokens gerados: {token_count:,}")
        print(f"  Velocidade: {tok_per_sec:.1f} tok/s")
        print(f"  VRAM: {vram_after_used} MiB usada, {vram_after_free} MiB livre")
        print(f"  RAM: {ram_after_used} MiB usada, {ram_after_free} MiB livre")
        print(f"  RSS: {rss_after} MiB")
        
        return result
        
    except Exception as e:
        print(f"ERRO: {e}")
        return None


def update_readme(results, book_text):
    """Atualiza a seção de benchmarks no README.md com os resultados."""
    if not os.path.exists(README_PATH):
        print(f"AVISO: {README_PATH} não encontrado, pulando atualização")
        return
    
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Gerar tabela de resultados
    table_lines = [
        "| `N_CTX` | Context | VRAM used | VRAM free | RAM used | RAM free | RSS | Prompt time | Tokens gen | tok/s | Viable? |",
        "|---|---|---|---|---|---|---|---|---|---|---|"
    ]
    
    # Encontrar melhor resultado (maior contexto viável com boa velocidade)
    best_ctx = None
    for r in results:
        # Viável se VRAM livre > 2GB e velocidade >= 20 tok/s
        viable = r['vram_free_mib'] > 2000 and r['tok_per_sec'] >= 20.0
        viable_str = "✓" if viable else "✗"
        if viable and (best_ctx is None or r['n_ctx'] > best_ctx['n_ctx']):
            best_ctx = r
        if best_ctx and r['n_ctx'] == best_ctx['n_ctx']:
            viable_str = "✓ padrão"
        
        table_lines.append(
            f"| {r['n_ctx']:,} | {r['n_ctx']//1024}k | {r['vram_used_mib']:,} MiB | "
            f"{r['vram_free_mib']:,} MiB | {r['ram_used_mib']:,} MiB | {r['ram_free_mib']:,} MiB | "
            f"{r['rss_mib']:,} MiB | {r['prompt_time_s']} s | {r['tokens_generated']:,} | "
            f"{r['tok_per_sec']} | {viable_str} |"
        )
    
    new_table = "\n".join(table_lines)
    
    # Substituir tabela existente no README
    # Padrão: entre "| `N_CTX`" e linha vazia após a tabela
    pattern = r'\| `N_CTX` \| Context.*?\n\|---\|---\|---\|---\|---\|---\|---\|---\|---\|---\|---\|.*?(?=\n\n|\n>)'
    
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, new_table, content, flags=re.DOTALL)
        print(f"✓ Tabela de benchmarks atualizada no {README_PATH}")
    else:
        print(f"AVISO: Padrão de tabela não encontrado no {README_PATH}")
        return
    
    # Atualizar recomendação
    if best_ctx:
        rec_pattern = r'\*\*Recomendação:\*\* `N_CTX=\d+`.*?(?=\n\n|\n>)'
        rec_text = f"**Recomendação:** `N_CTX={best_ctx['n_ctx']}` ({best_ctx['n_ctx']//1024}k — equilíbrio entre performance e espaço com Q5_K_M)"
        
        if re.search(rec_pattern, content):
            content = re.sub(rec_pattern, rec_text, content)
            print(f"✓ Recomendação atualizada: N_CTX={best_ctx['n_ctx']}")
    
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    parser = argparse.ArgumentParser(description="Benchmark oficial com PDF de ~250k tokens")
    parser.add_argument("--base", type=int, default=DEFAULT_BASE_CTX,
                        help=f"Contexto base (padrão: {DEFAULT_BASE_CTX})")
    parser.add_argument("--multipliers", type=str, default=None,
                        help=f"Multiplicadores separados por vírgula (padrão: {','.join(str(m) for m in DEFAULT_MULTIPLIERS)})")
    parser.add_argument("--fill", type=int, default=DEFAULT_FILL_PERCENT,
                        help=f"Preenchimento do contexto em %% (padrão: {DEFAULT_FILL_PERCENT})")
    parser.add_argument("--output", type=str, help="Arquivo de saída (padrão: data/logs/benchmark_YYYYMMDD_HHMMSS.md)")
    parser.add_argument("--resume", type=str, help="Retomar benchmark de um arquivo parcial JSON")
    parser.add_argument("--no-update-readme", action="store_true", help="Não atualizar README.md")
    args = parser.parse_args()
    
    # Carregar PDF
    book_text = load_pdf()
    print(f"✓ PDF carregado: {len(book_text):,} caracteres (~{len(book_text)//3.5:,.0f} tokens)")

    # Timestamp único para esta sessão
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    partial_path = f"{TEMP_DIR}/benchmark_partial_{timestamp}.json"

    # Parse multiplicadores
    if args.multipliers:
        multipliers = [float(x) for x in args.multipliers.split(",")]
    else:
        multipliers = DEFAULT_MULTIPLIERS
    
    # Gerar lista de contextos
    contexts = [int(args.base * m) for m in multipliers]
    fills = [args.fill] * len(contexts)

    # Retomar de checkpoint se --resume
    results = []
    if args.resume:
        loaded = load_partial_results(args.resume)
        if loaded:
            results = loaded
            print(f"\n✓ Checkpoint carregado: {len(results)} resultado(s) existentes")
            save_partial_results(results, partial_path)

    # Filtrar contextos já testados ao retomar
    tested_ctxs = {r["n_ctx"] for r in results}
    if tested_ctxs:
        remaining = [(ctx, fill) for ctx, fill in zip(contexts, fills) if ctx not in tested_ctxs]
        skipped = len(contexts) - len(remaining)
        if skipped > 0:
            print(f"\n  [skip] {skipped} contexto(s) já testado(s) no checkpoint")
        contexts, fills = zip(*remaining) if remaining else ([], [])

    print(f"\nBase: {args.base:,} tokens")
    print(f"Multiplicadores: {multipliers}")
    print(f"\nTestes planejados: {len(contexts)}")
    for ctx, fill, mult in zip(contexts, fills, multipliers):
        target = int(ctx * fill / 100)
        print(f"  - {mult}x → N_CTX={ctx:,} ({fill}%): ~{target//1024}k tokens de livro")

    # Executar testes
    for i, (ctx, fill) in enumerate(zip(contexts, fills), 1):
        mult = multipliers[i - 1] if i <= len(multipliers) else ctx / args.base
        test_name = f"{mult}x (N_CTX={ctx//1024}k, {fill}%)"
        
        # Parar servidor
        print(f"\n[{i}/{len(contexts)}] Preparando teste...")
        stop_server()
        
        # Iniciar servidor com N_CTX específico
        if not start_server_with_ctx(ctx):
            print(f"ERRO: Falha ao iniciar servidor com N_CTX={ctx}")
            continue
        
        # Executar teste
        result = run_test(book_text, test_name, ctx, fill)
        if result:
            results.append(result)
            save_partial_results(results, partial_path)

    # Parar servidor no final
    stop_server()
    
    # Gerar relatório
    if not results:
        print("\nERRO: Nenhum teste completou com sucesso")
        sys.exit(1)
    
    # Salvar relatório em data/logs/
    os.makedirs(LOGS_DIR, exist_ok=True)
    output_file = args.output or f"{LOGS_DIR}/benchmark_{timestamp}.md"
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# Benchmark Oficial — {datetime.now()}\n\n")
        f.write(f"**Modelo:** Qwen3.6-27B-Q5_K_M.gguf\n")
        f.write(f"**PDF:** {PDF_PATH} (~{len(book_text)//3.5:,.0f} tokens)\n\n")
        
        # Configuração
        f.write(f"**Configuração:**\n")
        f.write(f"- Base N_CTX: {args.base:,}\n")
        f.write(f"- Multiplicadores: {multipliers}\n")
        f.write(f"- Preenchimento: {args.fill}%\n")
        f.write(f"- CACHE_TYPE_K: q8_0\n")
        f.write(f"- CACHE_TYPE_V: q8_0\n")
        f.write(f"- CTX_CHECKPOINTS: 8\n")
        f.write(f"- CACHE_RAM: 2048\n")
        f.write(f"- N_BATCH: 4096\n\n")
        
        # Tabela de resultados
        f.write("## Resultados\n\n")
        f.write("| N_CTX | Context | Preenchimento | Livro (est.) | Tempo prompt | Tokens gerados | Tempo geração | Velocidade | VRAM usada | VRAM livre | RAM usada | RAM livre | RSS |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        
        for r in results:
            f.write(f"| {r['n_ctx']:,} | {r['n_ctx']//1024}k | {r['fill_percent']}% | ~{r['prompt_tokens_est']:,} | {r['prompt_time_s']}s | {r['tokens_generated']:,} | {r['generation_time_s']}s | {r['tok_per_sec']} tok/s | {r['vram_used_mib']} MiB | {r['vram_free_mib']} MiB | {r['ram_used_mib']} MiB | {r['ram_free_mib']} MiB | {r['rss_mib']} MiB |\n")
        
        f.write("\n## Análise\n\n")
        
        # Calcular médias
        avg_speed = sum(r['tok_per_sec'] for r in results) / len(results)
        avg_prompt_time = sum(r['prompt_time_s'] for r in results) / len(results)
        
        f.write(f"- **Velocidade média:** {avg_speed:.1f} tok/s\n")
        f.write(f"- **Tempo médio de prompt:** {avg_prompt_time:.1f}s\n")
        f.write(f"- **VRAM média:** {sum(r['vram_used_mib'] for r in results)//len(results)} MiB\n")
        
        # Recomendação
        best = max(results, key=lambda r: r['tok_per_sec'])
        f.write(f"\n**Recomendação:** N_CTX={best['n_ctx']:,} ({best['n_ctx']//1024}k) oferece melhor equilíbrio com {best['tok_per_sec']} tok/s\n")
    
    # Atualizar README.md
    if not args.no_update_readme:
        update_readme(results, book_text)
    
    print(f"\n{'='*70}")
    print(f"✓ Benchmark completo!")
    print(f"{'='*70}")
    print(f"\nRelatório final: {output_file}")
    print(f"Checkpoint parcial: {partial_path}")
    print(f"\nResumo:")
    for r in results:
        print(f"  - N_CTX={r['n_ctx']//1024}k: {r['tok_per_sec']} tok/s, {r['vram_used_mib']} MiB VRAM")


if __name__ == "__main__":
    main()
