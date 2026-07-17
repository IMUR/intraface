# Intraface — Handoff

**Date:** 2026-07-15
**For:** Next agent or session picking up Intraface work
**Status:** Fun-Audio-Chat evaluation closed as a Core no-go (ADR 0006).
Qwen3.6 Uncensored Aggressive Q6_K_P is the resident dual-GPU Core at
262K context. LiveKit Agents automatic half-duplex voice chat passed a
two-turn human test across trtr → drtr → prtr. Voice latency retest after
lowering Pi thinking is next.

---

## Current task (in progress)

**Modular hands-free voice chat evaluation.**

- Evaluation: `docs/voice-chat-evaluation.md`
- Implementation: `experiments/livekit-voice-agent/`
- Runtime: LiveKit Agents + local Silero + remote Parakeet/Chatterbox +
  persistent Pi/Qwen session.

**Current status (2026-07-13):**

- All STT/Pi/TTS adapters pass independent smoke tests.
- Silero assets are local and PortAudio runtime is installed.
- LiveKit console mode initializes microphone and speaker transport.
- Automatic endpointing is configured for 700ms silence.
- Interruptions are disabled for Phase 1 half-duplex stability.
- Human test passed: automatic endpointing, transcription, Pi response,
  playback, and return to listening all worked.
- Turn latency measured ~7.6s and ~13.9s before tuning.
- Voice A2A facade now forces Pi `--thinking low`; direct A2A response
  measured ~1.9s. Human latency retest is next.

The user wants UV (not pip, not conda) for the Python environment. UV v0.11.28 is available via mise.

## What exists

### Repo: `~/prj/intraface/` (Forgejo: `rtr/intraface`, branch `main`)

```
~/prj/intraface/
├── HANDOFF.md                              this file
├── engines.toml                            pinned engine commits + roles
├── package.json, .gitignore                minimal project metadata
├── docs/
│   ├── charter.md                          conceptual model + five tests
│   ├── features.md                         Unit backlog (pre-charter vocab)
│   ├── voice-chat-evaluation.md            current voice evaluation
│   ├── core-model-baselines/
│   │   ├── README.md                       resident/peer/rejected index
│   │   ├── glm-4.7-flash.md                verified-good baseline (peer candidate, not resident)
│   │   ├── qwen3.6-35b-a3b-evaluation.md   stock Q8 evaluation
│   │   ├── qwen3.6-35b-a3b-uncensored-aggressive.md
│   │   └── fun-audio-chat-8b-evaluation.md completed no-go evidence
│   └── decisions/
│       ├── README.md                       decision status index
│       ├── 0001-core-unit-model-custody.md
│       ├── 0002-dev-tree-is-runtime-target.md
│       ├── 0003-subprocess-over-bindings.md
│       ├── 0004-engine-builds-under-intraface.md     (deferred)
│       ├── 0005-fun-audio-chat-as-core-candidate.md  (superseded)
│       ├── 0006-reject-fun-audio-chat-as-core.md
│       └── 0007-explicit-per-node-runtime-deployment.md
├── extensions/
│   └── pi/
│       └── extract.ts                      Pi shim (DEPLOYED to ~/.pi/)
├── lib/                                    empty — runLlama is inlined for now
├── experiments/
│   ├── a2a-voice-bridge/                   retained FAC/A2A evidence
│   └── livekit-voice-agent/                current hands-free voice implementation
└── units/
    └── extract/
        ├── extract.ts                      the Unit (path-param, provenance)
        ├── schema.ts                       TS types + doc-only JSON Schema
        └── grammar.gbnf                    runtime constraint (-j broken)
```

### Runtime: `~/.intraface/`

```
~/.intraface/
├── models/
│   ├── README.md
│   ├── core/
│   │   ├── README.md
│   │   ├── glm-4.7-flash/                  GLM-4.7-Flash-Q8_0.gguf (31.8G) + .cache/
│   │   ├── qwen3.6-35b-a3b/                Qwen3.6-35B-A3B-Q8_0.gguf (36.9G)
│   │   ├── qwen3.6-35b-a3b-uncensored-aggressive/
│   │   │   ├── ...IQ4_XS.gguf              18.7G single-GPU profile
│   │   │   └── ...Q6_K_P.gguf              30.6G current dual-GPU resident
│   │   └── fun-audio-chat-8b/              retained no-go evaluation assets
│   └── unit/
│       ├── README.md
│       └── lfm2.5-1.2b-instruct/
│           └── LFM2.5-1.2B-Instruct-Q4_K_M.gguf   (731M)
├── state/                                   runtime logs; do not trust stale pidfiles
```

## State of the world (verified 2026-07-12)

- **Qwen3.6 Uncensored Aggressive Q6_K_P is resident** on both GPUs at
  262,144 context. The earlier IQ4_XS/FAC tandem is stopped.
- **A2A Pi facade is live** on `127.0.0.1:9999` for the trtr voice
  client, using low Pi thinking and a persistent session.
- **Reasoning display works** — `--reasoning-format deepseek` on the server side causes thinking to be sent in the `reasoning_content` field, which Pi renders properly.
- **Pi is running** with `extract.ts` + `herdr-agent-state.ts` extensions. The broken `summarize.ts` was removed; the new shim was deployed.
- **`models.json` context window fixed (2026-07-11).** Was 98304, now 262144 to match the server's `-c 262144`.
- **GLM is on disk but not currently resident.** It remains a peer Core candidate alongside Qwen3.6 and (pending evaluation) Fun-Audio-Chat-8B. Per ADR 0001, no candidate supersedes another; the resident is an operational choice. Verified-good baseline + swap procedure at `docs/core-model-baselines/glm-4.7-flash.md`.
- **`extract` Unit plumbing works** but **the LFM2.5 model produces garbage JSON** for non-trivial inputs. Smoke test from 2026-07-07 showed 0/5 verified quotes; later test showed zero JSON output at all. The Unit substrate is too small; deferred as separate iteration work.
- **`llama-cli` constraint mechanism is `--grammar-file`**, not `-j`/`--json-schema` (broken on mainline 9861). ADR-implicit; documented in `engines.toml [defects.json_schema]` and `units/extract/schema.ts` header.

## Known issues (real, not theoretical)

1. **Pidfile drift (2026-07-11).** The pidfile pointed at a dead PID while the real llama-server ran under a different one. Identify live processes by listening port / GPU process, not stale pidfiles.
2. **`extract` Unit substrate broken.** LFM2.5-1.2B is too small to follow the extract grammar reliably.
3. **Voice STT/TTS are batch endpoints.** Phase 1 is automatic
   half-duplex; streaming and barge-in remain Phase 2 work.

## What to read first (in order)

1. `docs/charter.md` — the conceptual model and five tests.
2. `docs/decisions/0001-core-unit-model-custody.md` — why `models/{core,unit}/`.
3. `docs/core-model-baselines/qwen3.6-35b-a3b-uncensored-aggressive.md`
   — current resident profiles and measurements.
4. `docs/decisions/0006-reject-fun-audio-chat-as-core.md` — why the FAC
   path stopped.
5. `docs/decisions/0007-explicit-per-node-runtime-deployment.md` —
   current cross-node deployment policy.
6. `docs/core-model-baselines/fun-audio-chat-8b-evaluation.md` — retained
   feasibility/A2A evidence.

## Open follow-ups (in priority order)

### Active

1. **Voice latency retest.** Re-run the trtr LiveKit console after the
   A2A facade's `--thinking low` change; compare end-of-speech to first
   audio against the prior 7.6s / 13.9s turns.
2. **Q6_K_P quality comparison.** Compare against IQ4_XS on identical
   coding, tool-use, reasoning, and long-context prompts.
3. **Long-context validation.** Exercise retrieval near the configured
   262K limit.

### Should-have-been-done-by-now

4. **`extract` Unit substrate iteration.** Either larger model (per
   `.archive/Orchestrator_Model_Investigation_Report.md` recommendations:
   Qwen3-Coder-30B-A3B, Devstral-Small) or improved prompt/grammar for
   LFM2.5.

### Deferred (waiting on trigger conditions)

5. **Core management approach** — launch profiles and mutual exclusion
   remain manual; stale pidfile drift has occurred before.
6. **Versioned cross-node deployment.** ADR 0007 currently uses manual
   rsync + `uv sync`; formalize only when a second deployed component or
   drift failure appears.
7. **Factor `runLlama()` into `lib/spawn-llama.ts`** when a second Unit exists.
8. **`docs/features.md`** still uses pre-charter vocab ("specialist" = "Unit"). Worth a terminology pass when convenient; not blocking.
9. **AGENTS.md** does not exist in this repo yet. Optional per cluster convention; not blocking.

## Critical verified facts (don't re-litigate)

- **`-j` / `--json-schema` is broken** on mainline llama.cpp `9861 (c8ae9a750)`. `--grammar-file *.gbnf` is the runtime mechanism.
- **`-st` / `--single-turn`** is the correct flag for non-interactive `llama-cli`. Not `--simple-io`, not `--no-conversation` alone.
- **`spawn("llama-cli", args)` with argv array** — never `spawn("sh", ["-c", ...])`. The latter caused three orphan processes earlier in the project history.
- **Engine versions** (from `--version`, captured in `engines.toml`): mainline `9861 (c8ae9a750)` for Units, ik_llama `4681 (86d8e9a1)` for the Core.
- **`--reasoning-format deepseek`** is required on ik_llama.cpp's `llama-server` to put thinking in `reasoning_content` field (separate from `content`). Without it, `<think>` tags appear inline in `content` and Pi displays them as regular text.
- **Qwen3.6 KV cache advantage verified at runtime**: 5,120 MiB at 262K context vs GLM's 5,076 MiB at 96K context. 2.7× larger context for the same KV memory.
- **GPU discipline.** Units run with `CUDA_VISIBLE_DEVICES=""` to keep them off the GPU the Core is saturating (see `extract.ts` line where `spawn()` env is constructed).

## Pointers

- Charter (canonical): `docs/charter.md` in this repo
- Old working dir (cold archive, read-only): `~/prj/archive/subagent-summarize/`
- Old remote (cold backup): `rtr/subagent-summarize` on Forgejo
- Oversight agent's terminal: `/home/prtr/.cursor/projects/home-prtr-prj-prtr-config/terminals/`
- Live Qwen3.6 Q6_K_P service: `127.0.0.1:7712`, dual GPU, 262K context.
- Live A2A Pi facade: `127.0.0.1:9999`.
- Fun-Audio-Chat model card: https://huggingface.co/FunAudioLLM/Fun-Audio-Chat-8B
- Fun-Audio-Chat source: https://github.com/FunAudioLLM/Fun-Audio-Chat (cloned to `~/prj/intraface/vendor/Fun-Audio-Chat/`)
- Fun-Audio-Chat venv: under the vendor checkout (created 2026-07-11; UV-managed; requires `--index-strategy unsafe-best-match` to reproduce)
- Current voice source: `experiments/livekit-voice-agent/`.
- Retained FAC/A2A evidence: `experiments/a2a-voice-bridge/`.
