# Qwen3.8-27B — local inference server

**Model:** Qwen3.8-27B Q8_0 (dense 27B, hybrid Gated DeltaNet + Attention, native MTP + native vision)
**GPU:** 2x RTX 3090 (48 GB) | **API:** `http://localhost:8080/v1` | **Context:** 262k (input 192k + output 65k)

## Configuration

- **Template:** embedded in the GGUF (no `--chat-template-file`)
- **Sampling:** official thinking-mode values — `temp=1.0, top_p=0.95, top_k=20, min_p=0.0`,
  no penalties (`presence=0.0, repeat=1.0, frequency=0.0`)
- **Reasoning:** `on`, format `deepseek` (exposes `message.reasoning_content`).
  Thinking depth is set by `REASONING_EFFORT=low` — the only value whose template branch actually
  asks for brief thinking (`medium` injects *nothing*, `xhigh` is the model's own default and asks
  for exhaustive deliberation). `REASONING_BUDGET=8192` is a safety net against thought-loops, not
  a verbosity brake: hitting it cuts the reasoning mid-thought and degrades tool calls.
  `REASONING_PRESERVE=false` keeps old `<think>` blocks out of the history.
- **Speculative decoding:** native MTP, `n=3` (`--spec-type draft-mtp`)
- **KV cache:** `q8_0` (f16 does not fit alongside a 29 GB Q8_0 model at 262k)
- **Vision:** native, via `mmproj-F16.gguf` from the same repo
- **DRY sampler:** off (`DRY_MULTIPLIER=0`) — never re-enable for coding, it corrupts long file paths

Full parameter reference: [`.env`](.env). Alternative model/GPU configs: [`env-examples/`](env-examples/).

## Commands

```bash
make start       # foreground
make start-bg    # background, logs to data/logs/server.log
make stop        # stop the server
make status      # is it up, and on which model
make test        # tests/test_api.py — API, tool calling, streaming
make logs        # tail the log
```

Full setup: `make setup` (zero-dependency pipeline: system deps → CUDA → venv → build
`llama-server` → download the GGUF). More targets: `make help`.

## Measured performance

| Metric | Q8_0 + MTP n=3 + q8_0 KV @ 262k |
|---|---|
| Decode, short context | 36-40 tok/s |
| Decode, real agent regime (long context) | 24-26 tok/s |
| Prompt processing | 355-715 tok/s |
| VRAM | ~21.4 GB (GPU 0) + ~22.7 GB (GPU 1) |

## Downstream

`infra/` holds the integration layer: LiteLLM gateway (`:4000`, `make litellm-start`), OpenCode
config, systemd units + watchdog, and logrotate. All of them point at `:8080` / model
`qwen3.8-27b` and must be kept in sync with `.env`.
