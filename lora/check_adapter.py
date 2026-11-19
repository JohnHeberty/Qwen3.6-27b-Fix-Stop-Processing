#!/usr/bin/env python3
"""CPU-only inspection of the LoRA adapter against the installed vLLM and the production W4A16 model.

  CUDA_VISIBLE_DEVICES= qwen38-27b-rtx3090/venv/bin/python -I lora/check_adapter.py

Reads ONLY the JSON header of the safetensors (no weights loaded, nothing executed from the
download) and checks:
  1. adapter_config: r, alpha, PEFT targets, no DoRA/rsLoRA/bias/modules_to_save
  2. the 512 keys -> vLLM's module names (same parse_fine_tuned_lora_name + hf_to_vllm_mapper
     that the engine uses for Qwen3_5ForConditionalGeneration), and that each module exists in the
     W4A16 checkpoint (q_proj.weight_packed etc.)
  3. PEFTHelper.validate_legal with the LoRAConfig from lora.env (rank 32, target modules)
  4. per-GPU VRAM estimate of the LoRA buffers (TP=2, bf16, max_loras=1)
Conclusion on 2026-11-18: no key conversion needed (vLLM maps
`base_model.model.model.language_model.layers.N...` -> `language_model.model.layers.N...` by itself).
"""
import collections
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAPTER = os.environ.get("LORA_PATH", os.path.join(ROOT, "lora/adapters/opencode-adapted"))
MODEL = os.environ.get("MODEL", os.path.join(ROOT, "qwen38-27b-rtx3090/models/Qwen3.8-27B-W4A16-AutoRound"))
TARGETS = ["qkv_proj", "o_proj", "gate_up_proj", "down_proj"]
TP, RANK = 2, 32

cfg = json.load(open(os.path.join(ADAPTER, "adapter_config.json")))
print("adapter_config:", {k: cfg[k] for k in ("r", "lora_alpha", "target_modules", "use_dora", "use_rslora",
                                               "bias", "modules_to_save", "base_model_name_or_path")})
assert cfg["r"] <= RANK and not cfg["use_dora"] and not cfg["use_rslora"] and cfg["bias"] == "none"

with open(os.path.join(ADAPTER, "adapter_model.safetensors"), "rb") as f:
    n = struct.unpack("<Q", f.read(8))[0]
    hdr = json.loads(f.read(n))
hdr.pop("__metadata__", None)
print(f"tensors: {len(hdr)}  dtypes: {collections.Counter(v['dtype'] for v in hdr.values())}")

from vllm.lora.peft_helper import PEFTHelper  # noqa: E402
from vllm.lora.utils import parse_fine_tuned_lora_name  # noqa: E402
from vllm.config.lora import LoRAConfig  # noqa: E402
from vllm.model_executor.models.qwen3_5 import Qwen3_5ForConditionalGeneration as M  # noqa: E402

mapper = M.hf_to_vllm_mapper.get_rename_mapper()
mods = {parse_fine_tuned_lora_name(k, mapper)[0] for k in hdr}
prefixes = collections.Counter(m.split(".layers.")[0] for m in mods)
print("vLLM prefixes:", dict(prefixes))
idx = json.load(open(os.path.join(MODEL, "model.safetensors.index.json")))["weight_map"]
base = {k.rsplit(".", 1)[0] for k in idx}
missing = [m for m in mods if m.replace("language_model.model.", "model.language_model.") not in base]
print(f"modules: {len(mods)}  missing from W4A16 checkpoint: {len(missing)} {missing[:3]}")
quant = collections.Counter(k.rsplit(".", 1)[1] for k in idx
                            if k.rsplit(".", 1)[0].replace("model.language_model.", "language_model.model.") in mods)
print("base tensors of these modules (compressed-tensors):", dict(quant))

lc = LoRAConfig(max_lora_rank=RANK, max_loras=1, target_modules=TARGETS)
ph = PEFTHelper.from_local_dir(ADAPTER, 262144)
ph.validate_legal(lc)
print(f"PEFTHelper.validate_legal OK (scaling alpha/r = {ph.vllm_lora_scaling_factor})")

mc = json.load(open(os.path.join(MODEL, "config.json")))["text_config"]
H, I, nh, nkv, hd, L = (mc["hidden_size"], mc["intermediate_size"], mc["num_attention_heads"],
                        mc["num_key_value_heads"], mc["head_dim"], mc["num_hidden_layers"])
n_attn = sum(t == "full_attention" for t in mc["layer_types"])
gate_up = 2 * RANK * H + 2 * (I // TP) * RANK          # column: A full, B sharded
down = RANK * (I // TP) + H * RANK                      # row: A sharded, B full
qkv = 3 * RANK * H + (2 * nh * hd // TP + 2 * (nkv * hd // TP)) * RANK   # q includes the attn_output_gate
o = RANK * (nh * hd // TP) + H * RANK
elems = L * (gate_up + down) + n_attn * (qkv + o)
print(f"LoRA buffers per GPU (TP={TP}, bf16, 1 slot): {elems / 1e6:.1f} M elems = {elems * 2 / 2**30:.3f} GiB")
sys.exit(1 if missing or len(prefixes) != 1 else 0)
