#!/usr/bin/env python3
"""
src/server.py — Servidor llama-cpp-python com template customizado em runtime.

Substitui 'python -m llama_cpp.server' — carrega o modelo GGUF e
sobrescreve o chat_template embutido com o arquivo de template do projeto,
sem precisar patchear o arquivo GGUF.
"""

import os
import sys
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="llama-cpp-python server com template customizado")
    parser.add_argument("--model",         required=True)
    parser.add_argument("--n_gpu_layers",  type=int,   default=-1)
    parser.add_argument("--n_ctx",         type=int,   default=63488)
    parser.add_argument("--n_batch",       type=int,   default=512)
    parser.add_argument("--host",          default="0.0.0.0")
    parser.add_argument("--port",          type=int,   default=8000)
    parser.add_argument("--model_alias",   default="qwen3")
    parser.add_argument("--template_file", default=None)
    args = parser.parse_args()

    # Carregar template customizado se especificado
    chat_handler = None
    if args.template_file and Path(args.template_file).exists():
        from llama_cpp.llama_chat_format import Jinja2ChatFormatter
        template = Path(args.template_file).read_text(encoding="utf-8")
        print(f"[server] Usando template: {args.template_file} ({len(template):,} chars)")
        chat_handler = Jinja2ChatFormatter(
            template=template,
            bos_token="",
            eos_token="<|im_end|>",
            add_generation_prompt=True,
        )
    else:
        print("[server] Usando template embutido no GGUF")

    from llama_cpp.server.settings import ModelSettings, ServerSettings
    from llama_cpp.server.app import create_app
    import uvicorn

    model_settings = ModelSettings(
        model=args.model,
        n_gpu_layers=args.n_gpu_layers,
        n_ctx=args.n_ctx,
        n_batch=args.n_batch,
        model_alias=args.model_alias,
        chat_format="jinja" if chat_handler is None else None,
        chat_handler=chat_handler,
        verbose=False,
    )

    server_settings = ServerSettings(
        host=args.host,
        port=args.port,
    )

    app = create_app(
        server_settings=server_settings,
        model_settings=[model_settings],
    )

    print(f"[server] Modelo   : {args.model}")
    print(f"[server] GPU layers: {args.n_gpu_layers}")
    print(f"[server] Contexto : {args.n_ctx} tokens")
    print(f"[server] API      : http://{args.host}:{args.port}/v1")

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
