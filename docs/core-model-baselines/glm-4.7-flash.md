# GLM-4.7-Flash — Core candidate baseline

**Status:** peer Core candidate alongside the Qwen3.6 profiles. Not
currently resident; Qwen3.6 Uncensored Aggressive Q6_K_P is resident as
of 2026-07-15. This file captures the verified working configuration so
swapping GLM in is mechanical. Fun-Audio-Chat was rejected as a Core
candidate by ADR 0006.

## Model file

- Path: `~/.intraface/models/core/glm-4.7-flash/zai-org_GLM-4.7-Flash-Q8_0.gguf`
- Size: 31,842,799,488 bytes (~31.8 GB)
- Quant: Q8_0
- Architecture: `glm4_moe_lite` (MLA attention)
- Native context: 202,752 tokens
- Activated parameters: ~3B of ~30B total

## Engine

- Binary: `~/prj/ik_llama.cpp/build/bin/llama-server`
- Version: `4681 (86d8e9a1)` — pinned in `engines.toml`
- Why ik_llama: GLM-specific flags (`-cram`, `--ctx-checkpoints`,
  `--n-cpu-moe`) not available in mainstream llama.cpp.

## Verified-working launch command

Captured from `/proc/<pid>/cmdline` on 2026-07-07 while GLM was the
resident Core:

```bash
cd ~/prj/ik_llama.cpp && ./build/bin/llama-server \
  -m ~/.intraface/models/core/glm-4.7-flash/zai-org_GLM-4.7-Flash-Q8_0.gguf \
  --host 127.0.0.1 --port 7712 \
  -c 98304 -np 1 -ngl 99 --n-cpu-moe 4 -cram 0 --ctx-checkpoints 0 --jinja
```

### Flag rationale

- `-c 98304` — 96K context. Conservative for safety; well below the
  202K native max.
- `-np 1` — single slot (single-user, no concurrent requests).
- `-ngl 99` — all layers on GPU.
- `--n-cpu-moe 4` — first 4 layers' MoE experts in CPU RAM. This was
  needed to fit in VRAM; log showed overrides on layers 22, 23, 45, 46.
- `-cram 0` — disable the GLM-specific RAM-backed context cache. Was
  the verified-working setting.
- `--ctx-checkpoints 0` — disable GLM-specific context checkpointing.
- `--jinja` — required for tool-calling template.

## Runtime characteristics (measured at PID 2303271, 2026-07-07)

- VRAM GPU 0: 21,936 MiB used / 2,304 free
- VRAM GPU 1: 22,058 MiB used / 2,175 free
- Total VRAM: 43,994 MiB (~95% of 48 GB)
- KV cache at 96K context: 5,076 MiB total (2,592 + 2,484)
- Compute buffers: 5,168 MiB per GPU + 100 MiB host

## Pi configuration when GLM was Core

```json
{
  "id": "glm-4.7-flash",
  "name": "GLM-4.7-Flash (local, Q8_0)",
  "reasoning": true,
  "input": ["text"],
  "contextWindow": 98304,
  "maxTokens": 8192
}
```

## To swap GLM in as resident

1. Stop the current resident Core (whichever candidate that is).
2. Start GLM with the launch command above.
3. Restore `~/.pi/agent/models.json` to the GLM entry above.
4. Restart Pi.

This is a routine candidate swap, not an emergency revert. Per ADR 0001,
all Core candidates are peers — the act of switching is operational, not
a response to failure.

## Notes

- GLM-4.7-Flash had been the resident Core since before Intraface was
  formalized. Its behavior was well-known and predictable.
- The ik_llama-specific flags (`-cram`, `--ctx-checkpoints`,
  `--n-cpu-moe`) are GLM-specific optimizations; Qwen3.6 doesn't take
  them.
- VRAM was tight at 95%; the current Q6_K_P profile uses about 35.6 GB
  total at 262K context, leaving about 12.9 GB free across both GPUs.
