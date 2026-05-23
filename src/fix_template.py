#!/usr/bin/env python3
"""
src/fix_template.py — Aplica o chat_template corrigido (froggeric) ao Qwen3.6 GGUF

Suporta dois formatos:
  - GGUF (.gguf): patcha o metadado tokenizer.chat_template dentro do arquivo
  - Safetensors: substitui o campo chat_template no tokenizer_config.json

Uso:
  python3 src/fix_template.py                          (usa template padrão: chat_template.jinja)
  python3 src/fix_template.py --model-dir data/models --template data/templates/chat_template.jinja
  make update-template                                 (download + aplicação automática)
"""

import argparse
import json
import shutil
import struct
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent

DEFAULT_MODEL_DIR  = _PROJECT_ROOT / "data" / "models"
DEFAULT_TEMPLATE   = _PROJECT_ROOT / "data" / "templates" / "chat_template.jinja"
DEFAULT_BACKUP_DIR = _PROJECT_ROOT / "data" / "backups"


def parse_args():
    p = argparse.ArgumentParser(description="Aplica template corrigido (froggeric) no modelo Qwen3.6")
    p.add_argument("--model-dir",  type=Path, default=DEFAULT_MODEL_DIR)
    p.add_argument("--template",   type=Path, default=DEFAULT_TEMPLATE)
    p.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    p.add_argument("--dry-run",    action="store_true")
    return p.parse_args()


# ── GGUF ──────────────────────────────────────────────────────────────────────

def find_gguf(model_dir: Path) -> Path | None:
    for f in model_dir.iterdir():
        if f.suffix == ".gguf":
            return f
    return None


def patch_gguf(gguf_path: Path, new_template: str, backup_dir: Path, dry_run: bool):
    """
    Patcha o template no GGUF com streaming binário + alinhamento correto.

    Algoritmo:
    1. GGUFReader → tensor_data_base_abs (onde começa dados dos tensores)
    2. Scan binário → posição exata do template no arquivo
    3. Scan backwards → old_padding (zeros antes dos dados de tensor)
    4. Streaming copy:
       prefix + new_len_field + new_bytes +
       (bytes template_end → tensor_base - old_padding) +   ← metadata real
       new_padding + tensor_data                             ← alinhamento correto
    """
    try:
        from gguf import GGUFReader
        import numpy as np
    except ImportError:
        print("ERRO: pacote 'gguf' nao encontrado. Execute: pip install gguf")
        sys.exit(1)

    print(f"Formato    : GGUF")
    print(f"Arquivo    : {gguf_path}")

    # ── 1. Encontrar tensor_data_base_abs via parsing do header GGUF ──────────
    # Lemos os primeiros 256 MB para ter header + KV + tensor_info na memória
    SCAN_SIZE = min(256 * 1024 * 1024, gguf_path.stat().st_size)
    with open(gguf_path, "rb") as fh:
        hdr = fh.read(SCAN_SIZE)

    # Header GGUF: magic(4) + version(4) + n_tensors(8) + n_kv(8) = 24 bytes
    n_tensors = struct.unpack_from("<Q", hdr, 8)[0]
    n_kv      = struct.unpack_from("<Q", hdr, 16)[0]

    # GGUF value type sizes: 0=u8,1=i8,2=u16,3=i16,4=u32,5=i32,6=f32,7=bool,
    #                        8=str(var),9=array(var),10=u64,11=i64,12=f64
    _VSIZES = {0:1, 1:1, 2:2, 3:2, 4:4, 5:4, 6:4, 7:1, 10:8, 11:8, 12:8}

    def skip_val(buf, pos, vtype):
        """Avança pos além de um valor do tipo vtype; retorna novo pos."""
        if vtype == 8:   # STRING
            slen = struct.unpack_from("<Q", buf, pos)[0]
            return pos + 8 + slen
        if vtype == 9:   # ARRAY
            elem_t = struct.unpack_from("<I", buf, pos)[0]
            count  = struct.unpack_from("<Q", buf, pos + 4)[0]
            pos += 12
            esz = _VSIZES.get(elem_t, 0)
            if esz > 0:  # tipos de tamanho fixo: pular em bloco (muito mais rápido)
                return pos + count * esz
            # Strings: precisam ser percorridas individualmente
            for _ in range(count):
                slen = struct.unpack_from("<Q", buf, pos)[0]
                pos += 8 + slen
            return pos
        sz = _VSIZES.get(vtype, 0)
        if sz == 0:
            raise ValueError(f"Tipo desconhecido: {vtype}")
        return pos + sz

    pos = 24  # após header
    for _ in range(n_kv):
        # key: uint64 length + bytes
        klen = struct.unpack_from("<Q", hdr, pos)[0]
        pos += 8 + klen
        # value type (uint32)
        vtype = struct.unpack_from("<I", hdr, pos)[0]
        pos += 4
        pos = skip_val(hdr, pos, vtype)

    # Agora pos aponta para início da seção de tensor_info
    for _ in range(n_tensors):
        tname_len = struct.unpack_from("<Q", hdr, pos)[0]
        pos += 8 + tname_len
        n_dims = struct.unpack_from("<I", hdr, pos)[0]
        pos += 4 + n_dims * 8 + 4 + 8  # dims + dtype + offset

    # Alinhar para GGUF_ALIGN = 32
    GGUF_ALIGN = 32
    tensor_data_base_abs = ((pos + GGUF_ALIGN - 1) // GGUF_ALIGN) * GGUF_ALIGN

    # ── 2. Localizar template no binário ──────────────────────────────────────
    KEY        = b"tokenizer.chat_template"
    key_prefix = struct.pack("<Q", len(KEY)) + KEY
    CHUNK      = 64 * 1024 * 1024
    GGUF_ALIGN = 32

    file_size = gguf_path.stat().st_size

    with open(gguf_path, "rb") as f:
        header = f.read(min(CHUNK, file_size))

    idx = header.find(key_prefix)
    if idx == -1:
        print("ERRO: chave tokenizer.chat_template nao encontrada no GGUF")
        sys.exit(1)

    meta_pos  = idx + len(key_prefix)
    val_type  = struct.unpack_from("<I", header, meta_pos)[0]
    if val_type != 8:
        print(f"ERRO: tipo esperado STRING (8), encontrado {val_type}")
        sys.exit(1)
    meta_pos += 4
    old_len   = struct.unpack_from("<Q", header, meta_pos)[0]
    meta_pos += 8

    template_data_start = meta_pos
    template_data_end   = meta_pos + old_len
    old_template        = header[template_data_start:template_data_end].decode("utf-8")
    # posição do campo comprimento (8 bytes antes dos dados)
    len_field_pos = template_data_start - 8

    print(f"Tensor data base abs : {tensor_data_base_abs:,} bytes")
    print(f"\nTemplate original  : {len(old_template):,} chars")
    print(f"Template corrigido : {len(new_template):,} chars")

    if old_template == new_template:
        print("\nTemplate ja e identico — nada a fazer.")
        sys.exit(0)

    print()
    print("--- Original (primeiros 100 chars):")
    print(f"    {old_template[:100].replace(chr(10), ' ')!r}")
    print()
    print("--- Corrigido (primeiros 100 chars):")
    print(f"    {new_template[:100].replace(chr(10), ' ')!r}")
    print()

    if dry_run:
        print("DRY RUN: nenhum arquivo foi modificado.")
        return

    # Backup
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"gguf_template_backup_{ts}.jinja"
    backup_file.write_text(old_template, encoding="utf-8")
    print(f"Backup salvo em: {backup_file}")

    # ── 3. Calcular real_metadata_end pelo forward scan (mais preciso) ─────────
    # pos já é o fim exato da seção tensor_info (antes do padding)
    # tensor_data_base_abs = align_up(pos, 32)
    real_metadata_end = pos   # end of tensor info (exact, from forward scan)
    old_padding = tensor_data_base_abs - pos
    print(f"Old padding: {old_padding} bytes | Real metadata ends at: {real_metadata_end:,}")

    # ── 4. Calcular novo padding ───────────────────────────────────────────────
    new_bytes     = new_template.encode("utf-8")
    new_len_field = struct.pack("<Q", len(new_bytes))
    delta         = len(new_bytes) - old_len

    # tamanho da seção real (sem padding) no novo arquivo:
    # prefix + new_len_field + new_bytes + (real_metadata_end - template_data_end)
    new_real_section = len_field_pos + 8 + len(new_bytes) + (real_metadata_end - template_data_end)
    new_padding = (GGUF_ALIGN - (new_real_section % GGUF_ALIGN)) % GGUF_ALIGN

    print(f"New padding: {new_padding} bytes | Delta: {delta:+,} bytes")

    # ── 5. Streaming copy ──────────────────────────────────────────────────────
    tmp_path = Path(tempfile.mktemp(suffix=".gguf", dir="/tmp"))
    tensor_data_size = file_size - tensor_data_base_abs
    new_size = len_field_pos + 8 + len(new_bytes) + (real_metadata_end - template_data_end) + new_padding + tensor_data_size
    print(f"Novo tamanho: {new_size / 1024**3:.2f} GB | Escrevendo em {tmp_path} ...")

    written = 0
    with open(gguf_path, "rb") as src, open(tmp_path, "wb") as dst:

        # a) prefix (bytes 0 → len_field_pos)
        remaining = len_field_pos
        while remaining > 0:
            chunk = src.read(min(CHUNK, remaining))
            dst.write(chunk)
            remaining -= len(chunk)
            written   += len(chunk)

        # b) novo comprimento + novo template
        dst.write(new_len_field)
        dst.write(new_bytes)
        written += 8 + len(new_bytes)

        # c) metadata real após o template (sem padding antigo)
        src.seek(template_data_end)
        remaining = real_metadata_end - template_data_end
        while remaining > 0:
            chunk = src.read(min(CHUNK, remaining))
            dst.write(chunk)
            remaining -= len(chunk)
            written   += len(chunk)

        # d) novo padding
        dst.write(b"\x00" * new_padding)
        written += new_padding

        # e) tensor data
        src.seek(tensor_data_base_abs)
        while True:
            chunk = src.read(CHUNK)
            if not chunk:
                break
            dst.write(chunk)
            written += len(chunk)
            print(f"\r  {written / new_size * 100:.1f}%", end="", flush=True)

    print(f"\r  100.0%")
    print(f"Substituindo original...")
    shutil.move(str(tmp_path), str(gguf_path))
    print(f"\n[OK] GGUF patcheado com sucesso: {gguf_path}")
    print("\nProximo passo:")
    print("  make start")


# ── Safetensors ───────────────────────────────────────────────────────────────

def patch_safetensors(model_dir: Path, new_template: str, backup_dir: Path, dry_run: bool):
    tokenizer_cfg = model_dir / "tokenizer_config.json"

    print(f"Formato    : Safetensors")
    print(f"Config     : {tokenizer_cfg}")

    if not tokenizer_cfg.exists():
        print(f"ERRO: tokenizer_config.json nao encontrado em {model_dir}")
        sys.exit(1)

    with open(tokenizer_cfg, "r", encoding="utf-8") as f:
        config = json.load(f)

    old_template = config.get("chat_template", "")

    print(f"\nTemplate original  : {len(old_template):,} chars")
    print(f"Template corrigido : {len(new_template):,} chars")

    if old_template == new_template:
        print("\nTemplate ja e identico ao v18 — nada a fazer.")
        sys.exit(0)

    print()
    print("--- Original (primeiros 100 chars):")
    print(f"    {old_template[:100].replace(chr(10), ' ')!r}")
    print()
    print("--- Corrigido (primeiros 100 chars):")
    print(f"    {new_template[:100].replace(chr(10), ' ')!r}")
    print()

    if dry_run:
        print("DRY RUN: nenhum arquivo foi modificado.")
        return

    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"tokenizer_config.backup_{ts}.json"
    shutil.copy2(tokenizer_cfg, backup)
    print(f"Backup salvo em: {backup}")

    config["chat_template"] = new_template
    with open(tokenizer_cfg, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    verify = json.load(open(tokenizer_cfg, encoding="utf-8"))
    if verify.get("chat_template") == new_template:
        print(f"\n[OK] tokenizer_config.json patcheado com sucesso.")
    else:
        print(f"\n[ERRO] Verificacao falhou. Restaure: cp {backup} {tokenizer_cfg}")
        sys.exit(1)

    print("\nProximo passo:")
    print("  make start")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    print("\n=== fix_template.py — Aplicar template corrigido (froggeric) ===\n")

    if not args.model_dir.exists():
        print(f"ERRO: Pasta do modelo nao encontrada: {args.model_dir}")
        print("      Execute scripts/setup.sh para baixar o modelo primeiro.")
        sys.exit(1)

    if not args.template.exists():
        print(f"ERRO: Template nao encontrado: {args.template}")
        sys.exit(1)

    print(f"Modelo     : {args.model_dir}")
    print(f"Template   : {args.template}")
    print(f"Dry run    : {'SIM' if args.dry_run else 'NAO'}")

    new_template = args.template.read_text(encoding="utf-8")

    gguf_file = find_gguf(args.model_dir)
    if gguf_file:
        patch_gguf(gguf_file, new_template, args.backup_dir, args.dry_run)
    else:
        patch_safetensors(args.model_dir, new_template, args.backup_dir, args.dry_run)


if __name__ == "__main__":
    main()
