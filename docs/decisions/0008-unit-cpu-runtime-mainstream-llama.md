# 0008. Unit CPU runtime is mainstream llama.cpp (not Ollama)

Date: 2026-08-01
Status: accepted

Related: [0001](0001-core-unit-model-custody.md), [0003](0003-subprocess-over-bindings.md)

## Context

Units need small models on prtr that never contend with the resident Core
for VRAM. Today that means CPU inference under
`CUDA_VISIBLE_DEVICES=""`.

Two non-solutions were in view:

- **Ollama on `:7711`** — still running, but its systemd unit pins
  `CUDA_VISIBLE_DEVICES` to GPU UUIDs from the previous prtr hardware
  (unit description still says "1080s only"). It is neither a deliberate
  CPU-only policy nor a trustworthy Unit host.
- **SGLang / LocalAI as Unit runtime** — prefix-cache wins assume a large
  shared prompt. Unit calls share only a thin primer; the bulk is unique
  source text. Extra serving stacks do not pay for themselves here.

ADR 0003 chose `llama-cli` subprocess over in-process bindings. That
isolation story remains valid as a fallback. The operational pain it
accepted — per-call model load (~tens of seconds) — is now the dominant
cost for Tier-1 Units, and is solved by a **warm** mainstream
`llama-server` on CPU, not by switching engines.

## Decision

1. **Unit engine = mainstream `llama.cpp`** (pinned in `engines.toml` as
   `engines.llama_cpp`). Not ik_llama (Core), not Ollama, not SGLang,
   not LocalAI.
2. **Default Unit runtime = warm CPU `llama-server`** listening on
   `127.0.0.1:7713`, with `CUDA_VISIBLE_DEVICES=` empty for the process.
   Model weights stay under `~/.intraface/models/unit/` (ADR 0001).
3. **Fallback = ADR 0003 subprocess** (`llama-cli`, same weights, same
   grammar files) when the warm server is down or for one-shot eval.
4. **Ollama `:7711` is out of the Unit path.** Leave the leftover unit
   alone until a separate cleanup; do not route Units through it and do
   not "fix" its GPU pins as a Unit strategy.
5. **Eval and baselines** live under `docs/unit-model-baselines/`,
   mirroring Core. Candidates are staged on disk; the warm server's `-m`
   (or a Unit's `SPECIALIST_MODEL_PATH`) selects which is active.

Canonical warm serve (default Unit model):

```bash
CUDA_VISIBLE_DEVICES= \
  /home/prtr/prj/llama.cpp/build/bin/llama-server \
  -m ~/.intraface/models/unit/lfm2.5-1.2b-instruct/LFM2.5-1.2B-Instruct-Q4_K_M.gguf \
  --host 127.0.0.1 --port 7713 \
  -c 32768 -ngl 0
```

Repo helper: `scripts/unit-server.sh`. User unit:
`~/.config/systemd/user/intraface-unit-server.service`.

## Consequences

**Positive:**

- CPU-only is policy (`CUDA_VISIBLE_DEVICES=`), not accidental fallback
  from stale GPU UUIDs.
- One engine pin for all Units; Core remains ik_llama on `:7712`.
- Warm server removes per-call load; subprocess remains for isolation
  and offline smoke tests.
- Ollama leftover cannot silently steal VRAM from a "fixed" pin update
  while Units think they are on CPU.

**Negative:**

- A second long-lived process on prtr (Unit server) must be managed.
- Units that speak HTTP must tolerate server-down → subprocess fallback
  (or fail closed — per Unit).
- Port `:7713` must stay in the AI block and out of other services.

**Charter compatibility:**

- Test 4 (substrate): cheapest sufficient worker — small GGUF on CPU via
  the engine already pinned for Units.
- Test 5 (custody): weights and runtime config under `~/.intraface/`;
  Ollama remains a foreign leftover.
