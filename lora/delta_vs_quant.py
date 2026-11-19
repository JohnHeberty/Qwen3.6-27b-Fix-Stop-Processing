#!/usr/bin/env python3
"""Route B (merge + requantize) sanity check, CPU only: does the adapter's delta survive INT4?

For a sample of modules, computes dW = (alpha/r) * B @ A (fp32) and compares it to the
INT4 quantization step of the SAME module in the production checkpoint (weight_scale,
group 128, symmetric: one level = scale). Reports:
  - median |dW| / scale
  - fraction of weights where |dW| > scale/2 (only those can change level in a naive RTN
    requantization over the same scales; the rest of the update is rounded away)
If the fraction is tiny, a merge + requantize (Route B) erases most of the adapter
and runtime LoRA (bf16 delta on top of W4A16) is the only route that preserves it.

  CUDA_VISIBLE_DEVICES= qwen38-27b-rtx3090/venv/bin/python -I lora/delta_vs_quant.py
"""
import json
import os

import torch
from safetensors import safe_open

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAPTER = os.path.join(ROOT, "lora/adapters/opencode-adapted")
MODEL = os.environ.get("MODEL", os.path.join(ROOT, "qwen38-27b-rtx3090/models/Qwen3.8-27B-W4A16-AutoRound"))
SCALING = 64 / 32
SAMPLE = [(0, "mlp.gate_proj"), (0, "mlp.down_proj"), (31, "mlp.up_proj"), (63, "mlp.down_proj"),
          (3, "self_attn.q_proj"), (3, "self_attn.o_proj"), (31, "self_attn.v_proj"), (63, "self_attn.k_proj")]

idx = json.load(open(os.path.join(MODEL, "model.safetensors.index.json")))["weight_map"]
ad = safe_open(os.path.join(ADAPTER, "adapter_model.safetensors"), "pt")
rows = []
for layer, mod in SAMPLE:
    base = f"model.language_model.layers.{layer}.{mod}"
    a = ad.get_tensor(f"base_model.model.{base}.lora_A.weight").float()
    b = ad.get_tensor(f"base_model.model.{base}.lora_B.weight").float()
    dw = SCALING * (b @ a)                                   # [out, in]
    with safe_open(os.path.join(MODEL, idx[base + ".weight_scale"]), "pt") as f:
        sc = f.get_tensor(base + ".weight_scale").float().abs()  # [out, in/128]; ~50% are stored negative
    step = sc.repeat_interleave(dw.shape[1] // sc.shape[1], dim=1)
    ratio = dw.abs() / step.clamp_min(1e-12)
    r = {"module": base.replace("model.language_model.", ""), "shape": list(dw.shape),
         "median_abs_dW_over_step": round(ratio.median().item(), 4),
         "p99_abs_dW_over_step": round(ratio.flatten()[::97].quantile(0.99).item(), 4),
         "frac_over_half_step": round((ratio > 0.5).float().mean().item(), 5)}
    rows.append(r)
    print(json.dumps(r), flush=True)
    del a, b, dw, sc, step, ratio
print("mean fraction > step/2:", round(sum(r["frac_over_half_step"] for r in rows) / len(rows), 5))
