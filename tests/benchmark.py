#!/usr/bin/env python3
"""
Benchmark oficial — Testa diferentes N_CTX reiniciando o servidor entre testes.
Usa data/temp/RL_OREILLY_full.md para sobrecarregar o contexto e medir performance real.

Uso:
    python3 tests/benchmark.py                          # Testa contextos padrão (32k, 48k, 64k)
    python3 tests/benchmark.py --contexts 32768,49152   # Testa contextos específicos
    python3 tests/benchmark.py --fill 50,75,90          # Testa preenchimentos (%, máx do N_CTX base)
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
    print("Instalando requests...")
    subprocess.run([sys.executable, "-m", "pip", "install", "requests", "-q"], check=True)
    import requests

# Configuração
API_URL = "http://localhost:8000/v1/chat/completions"
HEALTH_URL = "http://localhost:8000/health"
PROPS_URL = "http://localhost:8000/props"
PDF_PATH = "data/temp/RL_OREILLY_full.md"


def get_vram():
    """Coleta VRAM usada e livre via nvidia-smi."""
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    used, free = result.stdout.strip().split(", ")
    return int(used), int(free)


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
    """Inicia servidor com N_CTX específico."""
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
    
    # Escrever .env temporário
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
    print(f"VRAM antes: {vram_before_used} MiB usada, {vram_before_free} MiB livre")
    
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
        
        # Coletar VRAM depois
        vram_after_used, vram_after_free = get_vram()
        
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
        }
        
        print(f"\n✓ Resultado:")
        print(f"  Tempo prompt: {prompt_time:.1f}s")
        print(f"  Tempo geração: {generation_time:.1f}s")
        print(f"  Tokens gerados: {token_count:,}")
        print(f"  Velocidade: {tok_per_sec:.1f} tok/s")
        print(f"  VRAM: {vram_after_used} MiB usada, {vram_after_free} MiB livre")
        
        return result
        
    except Exception as e:
        print(f"ERRO: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Benchmark oficial com PDF de ~250k tokens")
    parser.add_argument("--contexts", type=str, help="Contextos específicos (ex: 32768,49152,65536)")
    parser.add_argument("--fill", type=str, help="Preenchimentos em % (ex: 50,75,90)")
    parser.add_argument("--output", type=str, help="Arquivo de saída (padrão: data/logs/benchmark_YYYYMMDD_HHMMSS.md)")
    args = parser.parse_args()
    
    # Carregar PDF
    book_text = load_pdf()
    print(f"✓ PDF carregado: {len(book_text):,} caracteres (~{len(book_text)//3.5:,.0f} tokens)")
    
    # Determinar contextos para testar
    if args.contexts:
        contexts = [int(x) for x in args.contexts.split(",")]
        fills = [90] * len(contexts)  # Padrão: 90% de preenchimento
    elif args.fill:
        # Usar N_CTX base de 65536
        n_ctx_base = 65536
        fills = [int(x) for x in args.fill.split(",")]
        contexts = [n_ctx_base] * len(fills)
    else:
        # Padrão: testar 32k, 48k, 64k com 90% de preenchimento
        contexts = [32768, 49152, 65536]
        fills = [90, 90, 90]
    
    print(f"\nTestes planejados: {len(contexts)}")
    for ctx, fill in zip(contexts, fills):
        target = int(ctx * fill / 100)
        print(f"  - N_CTX={ctx:,} ({fill}%): ~{target//1024}k tokens de livro")
    
    # Executar testes
    results = []
    for i, (ctx, fill) in enumerate(zip(contexts, fills), 1):
        target = int(ctx * fill / 100)
        test_name = f"N_CTX={ctx//1024}k ({fill}%)"
        
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
    
    # Parar servidor no final
    stop_server()
    
    # Gerar relatório
    if not results:
        print("\nERRO: Nenhum teste completou com sucesso")
        sys.exit(1)
    
    # Obter info do modelo
    # (servidor já parou, então não podemos consultar)
    model_name = "qwen3"
    
    # Salvar relatório
    os.makedirs("data/logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = args.output or f"data/logs/benchmark_{timestamp}.md"
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# Benchmark Oficial — {datetime.now()}\n\n")
        f.write(f"**Modelo:** Qwen3.6-27B-Q5_K_M.gguf\n")
        f.write(f"**PDF:** {PDF_PATH} (~{len(book_text)//3.5:,.0f} tokens)\n\n")
        
        # Configuração
        f.write(f"**Configuração:**\n")
        f.write(f"- CACHE_TYPE_K: q8_0\n")
        f.write(f"- CACHE_TYPE_V: q8_0\n")
        f.write(f"- CTX_CHECKPOINTS: 8\n")
        f.write(f"- CACHE_RAM: 2048\n")
        f.write(f"- N_BATCH: 4096\n\n")
        
        # Tabela de resultados
        f.write("## Resultados\n\n")
        f.write("| N_CTX | Contexto | Preenchimento | Livro (est.) | Tempo prompt | Tokens gerados | Tempo geração | Velocidade | VRAM usada | VRAM livre |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|\n")
        
        for r in results:
            f.write(f"| {r['n_ctx']:,} | {r['n_ctx']//1024}k | {r['fill_percent']}% | ~{r['prompt_tokens_est']:,} | {r['prompt_time_s']}s | {r['tokens_generated']:,} | {r['generation_time_s']}s | {r['tok_per_sec']} tok/s | {r['vram_used_mib']} MiB | {r['vram_free_mib']} MiB |\n")
        
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
    
    print(f"\n{'='*70}")
    print(f"✓ Benchmark completo!")
    print(f"{'='*70}")
    print(f"\nResultados salvos em: {output_file}")
    print(f"\nResumo:")
    for r in results:
        print(f"  - N_CTX={r['n_ctx']//1024}k: {r['tok_per_sec']} tok/s, {r['vram_used_mib']} MiB VRAM")


if __name__ == "__main__":
    main()
