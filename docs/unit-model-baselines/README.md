# Unit model baselines

Verified profiles and evaluation records for models under Intraface Unit
custody (`~/.intraface/models/unit/`).

Runtime authority: ADR [0008](../decisions/0008-unit-cpu-runtime-mainstream-llama.md).
Engine: mainstream `llama.cpp` (see `engines.toml` → `engines.llama_cpp`).

Last live-state check: **2026-08-01**

## Current default

### LFM2.5-1.2B-Instruct Q4_K_M

- Path: `~/.intraface/models/unit/lfm2.5-1.2b-instruct/LFM2.5-1.2B-Instruct-Q4_K_M.gguf`
- Role: default model for `units/extract`
- Runtime: warm CPU `llama-server` on `127.0.0.1:7713` (`-ngl 0`)
- Fallback: `llama-cli` subprocess with `CUDA_VISIBLE_DEVICES=""` (ADR 0003)
- Baseline status: **incumbent, not yet measured** — replace guessed
  `PREFILL_TPS` / `DECODE_TPS` / `LOAD_OVERHEAD_S` in `extract.ts` after
  `llama-bench` and a fixture pack run

## Conventions

- A **baseline** records measured CPU runtime (tps, load, verify-rate on
  the fixture pack) for a model that may be the Unit default.
- An **evaluation** records a candidate that has not earned default status.
- Many Unit models may coexist on disk; the warm server's `-m` (or
  `UNIT_MODEL_PATH` / `SPECIALIST_MODEL_PATH`) selects the active one.
- Units must not use Ollama `:7711` or Core `:7712`.

## How to measure a candidate

```bash
# Throughput (CPU)
CUDA_VISIBLE_DEVICES= llama-bench \
  -m ~/.intraface/models/unit/<family>/model.gguf \
  -p 8192 -n 128 -ngl 0

# Start / swap warm server
UNIT_MODEL_PATH=~/.intraface/models/unit/<family>/model.gguf \
  systemctl --user restart intraface-unit-server.service

# Prove no GPU
curl -sS http://127.0.0.1:7713/health
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
# unit-server must not appear; Core llama-server on both 3090s is expected
```

## Out of Unit custody (do not treat as provisioned)

Ollama may still list `LFM2-1.2B` / `LFM2.5-Thinking` blobs. Those are not
Intraface Unit models until copied under `models/unit/` and baselined here.
