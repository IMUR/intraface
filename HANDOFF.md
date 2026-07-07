# Intraface — Handoff

**Date:** 2026-07-07
**For:** Next agent or session picking up Intraface work
**Status:** First charter-compliant Unit exists on disk and in repo. Not yet verified working end-to-end. Several follow-ups queued.

---

## What exists

### Repo: `~/prj/intraface/` (Forgejo: `rtr/intraface`, branch `main`)

```
~/prj/intraface/
├── HANDOFF.md                              this file
├── engines.toml                            pinned engine commits + roles
├── docs/
│   ├── charter.md                          conceptual model + five tests
│   ├── features.md                         Unit backlog (pre-charter vocab)
│   ├── glm-migration.md                    GLM→intraface-custody runbook
│   └── decisions/
│       ├── 0001-core-unit-model-custody.md
│       └── 0002-dev-tree-is-runtime-target.md
├── extensions/
│   └── pi/
│       └── extract.ts                      Pi shim (NOT yet deployed)
├── lib/                                    empty — runLlama is inlined for now
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
│   ├── core/        empty — GLM migration is a queued follow-up
│   │   └── README.md                       states the pending plan
│   └── unit/
│       ├── README.md
│       └── lfm2.5-1.2b-instruct/
│           └── LFM2.5-1.2B-Instruct-Q4_K_M.gguf   (731M, verified)
└── state/                                  empty — runtime PIDs go here
```

## State of the world (verified 2026-07-07)

- **First charter-compliant Unit (`extract`) exists on disk.** Fails Test 1 by zero (path-param input, not source-text); fails Test 2 by zero (per-item quote + computed span + verified boolean).
- **GLM is live** at PID 634777, `127.0.0.1:7712`, manually launched (no systemd), cwd `~/prj/ik_llama.cpp`. Untouched.
- **`llama-cli` constraint mechanism is `--grammar-file`, not `-j`/`--json-schema`.** Mainline build 9861 (`c8ae9a750`) throws on sampler init for `-j`. Documented in `engines.toml [defects.json_schema]` and `units/extract/schema.ts` header. Revisit when upstream fixes.
- **Old work archived.** `~/prj/subagent-summarize/` moved to `~/prj/archive/subagent-summarize/`. The 3 rejected model files (Q4/Q5 Transcript, 8B A1B) were deleted; only the surviving LFM2.5 was migrated to intraface custody. The Forgejo `rtr/subagent-summarize` remote is left as a cold backup.
- **Pi extension not yet swapped.** `~/.pi/agent/extensions/summarize.ts` is still the old v1 (imports from the archived dir — that import is now broken). The new shim at `extensions/pi/extract.ts` has not been deployed. Swapping them is a follow-up gated on the smoke test below.

## What to read first (in order)

1. `docs/charter.md` — the conceptual model and five tests.
2. `docs/decisions/0001-core-unit-model-custody.md` — why `models/{core,unit}/`.
3. `docs/decisions/0002-dev-tree-is-runtime-target.md` — why the dev tree IS the runtime target, and when to revisit that.
4. `docs/glm-migration.md` — runbook for moving GLM into intraface custody.

## Smallest next step

**Smoke-test the extract Unit before any deployment or commit-into-Pi.** Run via CLI to bypass Pi:

```bash
cd ~/prj/intraface/units/extract && \
  node --experimental-strip-types extract.ts \
    /home/prtr/prj/intraface/HANDOFF.md 1 50
```

The smoke test exercises: `llama-cli` on PATH, model loads from `~/.intraface/`, grammar-file enforcement, JSON parse, quote-location verification. Until this passes, "exists on disk" does not mean "works."

**If smoke test passes:**

1. Deploy the new shim: `cp ~/prj/intraface/extensions/pi/extract.ts ~/.pi/agent/extensions/extract.ts`
2. Remove the broken old one: `rm ~/.pi/agent/extensions/summarize.ts`
3. Restart Pi.

**If smoke test fails:** the failure mode tells you what to fix (PATH, grammar path, model path, or model output shape). Common-cases checklist is in `extract.ts` header comments.

## Critical verified facts (don't re-litigate)

- **`-j` / `--json-schema` is broken** on mainline llama.cpp `9861 (c8ae9a750)`. `--grammar-file *.gbnf` is the runtime mechanism.
- **`-st` / `--single-turn`** is the correct flag for non-interactive `llama-cli`. Not `--simple-io`, not `--no-conversation` alone.
- **`spawn("llama-cli", args)` with argv array** — never `spawn("sh", ["-c", ...])`. The latter caused three orphan processes earlier in the project history.
- **Engine versions** (from `--version`, captured in `engines.toml`): mainline `9861 (c8ae9a750)` for Units, ik_llama `4681 (86d8e9a1)` for the Core.
- **GPU discipline.** Units run with `CUDA_VISIBLE_DEVICES=""` to keep them off the GPU the Core is saturating (see `extract.ts` line where `spawn()` env is constructed).

## Open follow-ups

1. **Smoke-test `extract`** (the smallest next step above). Gated nothing; just needs to run.
2. **Deploy Pi shim** once smoke test passes.
3. **GLM migration** into `~/.intraface/models/core/`. Runbook at `docs/glm-migration.md`. High priority but service-disruptive — schedule a window.
4. **Factor `runLlama()` into `lib/spawn-llama.ts`** when a second Unit exists. Charter Test 5 custody argument; not needed at N=1.
5. **Revisit ADR 0002** (dev-as-deployment) when its trigger conditions fire (second machine, second operator, stable/dev split, atomic rollback, second deployment surface).
6. **`docs/features.md`** still uses pre-charter vocab ("specialist" = "Unit"). Worth a terminology pass when convenient; not blocking.
7. **AGENTS.md** does not exist in this repo yet. Optional per cluster convention; not blocking.

## Pointers

- Charter (canonical): `docs/charter.md` in this repo
- Old working dir (cold archive, read-only): `~/prj/archive/subagent-summarize/`
- Old remote (cold backup): `rtr/subagent-summarize` on Forgejo
- Oversight agent's terminal: `/home/prtr/.cursor/projects/home-prtr-prj-prtr-config/terminals/`
- Live GLM service: PID 634777 on `127.0.0.1:7712` (do not disturb — ~95% VRAM)
