# Intraface — Handoff

**Date:** 2026-07-06
**For:** Next agent or session picking up Intraface work
**Status:** Scaffold laid. No code yet. Critical decisions still open.

---

## What exists right now

```
~/prj/intraface/         (NEW — created today)
├── docs/
│   └── charter.md       # Intraface charter, clean (stale refs fixed)
├── lib/                 # empty — spawn-llama.ts lands here
├── units/
│   └── summarize/       # empty — first Unit code lands here
└── HANDOFF.md           # this file

~/.intraface/            (NEW — created today)
├── models/
│   └── lfm2.5-1.2b-instruct/   # empty — model moves here in Phase 2
└── state/                      # empty — runtime state (PIDs, etc.)

~/prj/prtr-config/
├── intraface-charter.md                  # original (still here; cleaned copy is in intraface/docs/)
└── docs/
    ├── features.md                       # specialist backlog (pre-charter vocab)
    ├── oversight-agent-prd.md            # oversight behavior spec
    └── intraface-restructure-plan.md     # full execution plan (798 lines)
```

## What doesn't exist yet (despite mentions elsewhere)

**No code has been ported.** The old `~/prj/subagent-summarize/` is untouched. The new `~/prj/intraface/{lib,units}/` directories are empty.

**No models have moved.** All four model files are still at `~/prj/subagent-summarize/models/`.

**No Pi extension swap.** The deployed extension at `~/.pi/agent/extensions/summarize.ts` is unchanged and still imports from `/home/prtr/prj/subagent-summarize/summarize.ts`.

## The charter's first workout

The charter was applied as a review framework to the restructure plan. It caught real defects:

1. The on-disk `summarize.ts` code fails **Test 1 (attention)** — `source: string` parameter puts full bulk through Core context twice.
2. The on-disk `summary.gbnf` grammar fails **Test 2 (proof)** — enforces structure but no provenance (no quote/span/source fields).
3. The plan's Phase 7 attempt to "port the spawn helper only" was caught as incoherent — it actually re-implemented the broken summarize function under new authorship.

So the right move is not "port and refactor later." The right move is **build the first charter-compliant Unit from scratch** at `units/extract/` (or `units/summarize/` — naming TBD) with the right shape from day one.

## What the first Unit needs (the real work)

Per charter Tests 1 and 2:

- **Path parameter, not source text.** `parameters: Type.Object({ source_path: Type.String(...) })`. The Unit reads the file itself; the bulk never transits Core context.
- **Schema-with-provenance output.** Not just `{summary, key_points, ...}` but `{text, quote, span: [start,end], source, hash, moment, executor}` — output that can be verified by string-match against the source without re-reading the source.
- **Domain primer in prompt.** "This is the Reactor (rtr) cluster: prtr/drtr/crtr/trtr are nodes, GLM is the orchestrator LLM..." — kills the "RTR = Remote Transfer Service" hallucination class.
- **Grammar that matches the schema.** The current `summary.gbnf` enforces the v1 shape without provenance. A new grammar is needed that enforces the v2 shape.

## Critical verified facts (don't re-litigate)

These were checked against live state on 2026-07-06:

- **`-j` / `--json-schema` is broken** on mainline llama.cpp build `9861 (c8ae9a750)`. Sampler init throws `Failed to initialize samplers: std::exception`. Grammar file approach (`--grammar-file *.gbnf`) is the only working constraint mechanism. Revisit when mainline updates.
- **`-st` / `--single-turn` is the correct flag** for non-interactive llama-cli runs. Not `--simple-io` (display-only), not `--no-conversation` alone (still loops).
- **`spawn("llama-cli", args)` with argv array** is the correct invocation pattern. Never `spawn("sh", ["-c", command])` — that caused three orphan processes this session via shell-mangled prompts.
- **Engine versions** (from `--version`): mainline `9861 (c8ae9a750)`, ik_llama `4681 (86d8e9a1)`.
- **Model file sizes** (from `stat -c %s`): LFM2.5-1.2B-Instruct-Q4_K_M is 730,895,168 bytes; GLM-4.7-Flash-Q8_0 is 31,842,799,488 bytes.
- **GLM launch line** captured from `/proc/634777/cmdline`: see plan Phase 6 for the full flag list.

## Open decisions (need user input before execution)

1. **Tree shape inside `units/`.** Folder-per-Unit (recommended per charter custody) vs file-type grouping. Currently laid out for folder-per-Unit. Lockable by either proceeding as-is or renaming.

2. **What to do with `~/prj/subagent-summarize/`** (the old working dir). Its git repo is pushed to `rtr/subagent-summarize` on Forgejo with two commits. Three options: delete repo + dir; rename repo + re-init; leave alone. User's call.

3. **The "Phase A files" question.** A parallel Claude session claims to have produced charter-compliant code (extract.ts, schema.ts, etc.) with path-parameter, provenance schema, and domain primer. **I have not seen these files.** If they exist in that session's outputs, paste them into the next session and they land at `units/extract/`. If they don't exist, the first Unit gets built fresh.

## What the previous oversight session got wrong

Naming these so the next session doesn't repeat them:

1. **The original restructure plan proposed porting the broken `summarize.ts` as an "interim shim."** That was incoherent — porting charter-violating code into a clean home while labeling it interim is the anti-pattern the charter exists to prevent.
2. **The plan's registry files had `9_000_000_000 # approx` for GLM size** next to `verified = "2026-07-06"`. Actual size is 31.8 GB. The 3.5× error was caught by the charter's D1 (cite or retract) applied to the plan itself.
3. **The plan originally used a symlink for the deployed extension.** Node's module resolver dereferences symlinks, so `typebox` would have failed to resolve. Use a real-file shim with absolute imports instead.

## What to read first

In order:

1. `docs/charter.md` (in this repo) — the conceptual model and five tests
2. `~/prj/prtr-config/docs/intraface-restructure-plan.md` — full execution plan with phases, but **read critically** — Phase 7's "interim shim" approach is wrong per the above
3. `~/prtr/prtr-config/docs/oversight-agent-prd.md` — oversight behavior (relevant if you're operating as oversight)
4. `~/prj/prtr-config/docs/features.md` — specialist backlog (uses pre-charter vocab: "specialist" = "Unit")

## Smallest next step

If you want to make progress without committing to the full restructure:

1. **Write `lib/spawn-llama.ts`** — the verified subprocess helper. This is charter-neutral (just plumbing) and unblocks any Unit work. See plan Phase 4 for the code.
2. **Stop.** Don't port the summarize function. Don't write the extension shim yet. Get the spawn helper right, then design the first Unit against the charter from scratch.

That's the minimal forward motion that doesn't carry charter debt.

## Verification recipes (from oversight PRD, repeated here for convenience)

- Process state: `Read /proc/<pid>/status` (text), `Read /proc/<pid>/io` (text, wchar = output volume)
- Cmdline: `/proc/<pid>/cmdline` is binary NUL-separated. Decode: `tr '\0' ' ' < /proc/<pid>/cmdline`
- Service health: `ss -tlnp | rg ':<port>'` (real shell, not sandbox)
- Sandbox limitation: Cursor's sandbox kills `ls /proc`, `ps`, most piped commands. Bare `echo` works. When blocked, ask the user.

## Pointers

- Charter original (with stale refs): `~/prj/prtr-config/intraface-charter.md`
- Plan: `~/prj/prtr-config/docs/intraface-restructure-plan.md`
- Old working dir (untouched): `~/prj/subagent-summarize/`
- Oversight agent's terminal: `/home/prtr/.cursor/projects/home-prtr-prj-prtr-config/terminals/`
- Live GLM service: PID 634777 on `127.0.0.1:7712` (do not disturb — 95% VRAM)
