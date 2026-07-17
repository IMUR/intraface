# 0003. Subprocess over in-process bindings for Unit inference

Date: 2026-07-07
Status: accepted

## Context

Units invoke small local models (today: LFM2.5-1.2B-Instruct) on behalf
of the Core. Two architectural options existed for how a Unit's TypeScript
code talks to the model:

- **Bindings** — import a native Node.js addon (`node-llama-cpp` was the
  specific package evaluated) that compiles llama.cpp *into* the Node
  process. The Unit calls functions like `model.createContext()` and
  `session.prompt()` directly.
- **Subprocess** — use Node's `child_process.spawn()` to launch a
  standalone `llama-cli` binary as a separate OS process. Pass
  arguments, read stdout, the process exits.

The pre-Intraface `subagent-summarize` project initially chose bindings.
A working spike (`test-model.ts` in the archive) proved `node-llama-cpp`
v3.19.0 could load LFM2 models and produce output.

The shipped `summarize.ts` and the current `extract.ts` Unit both use
subprocess. The switch happened without a recorded rationale.

## Decision

**Units spawn `llama-cli` as a subprocess.** They do not import
`node-llama-cpp` or any other native bindings.

The pattern is encoded in `units/extract/extract.ts`:

- `spawn(LLAMA_CLI, args, { env: { ...process.env, CUDA_VISIBLE_DEVICES: "" } })`
- argv-array, never `spawn("sh", ["-c", ...])` (the latter caused three
  orphan processes earlier in the project history)
- timeout derived from input size, `SIGKILL` on overrun
- JSON extracted from stdout via regex

## Consequences

**Positive:**

- **Engine swappability.** `LLAMA_CLI` is an env-overridable path. A
  different engine build (a newer `llama-cli`, an experimental fork,
  `nlc` from a hypothetical future `node-llama-cpp` CLI mode) drops in
  without Unit-code changes. With bindings, the engine version is
  whatever the npm package bundles.
- **Memory isolation.** A Unit crash takes down only its own OS process.
  With bindings, a llama.cpp crash would take down the Node process
  running Pi.
- **No Node-version coupling.** Subprocess works with any Node version.
  Native N-API addons require a matching Node ABI; Node upgrades can
  break them.
- **Substrate freshness.** The mainstream llama.cpp build is at upstream
  HEAD (`9861` as of last pull). `node-llama-cpp` v3.19.0 bundles
  `b9842`, which is older. Subprocess lets Units track upstream directly.

**Negative:**

- **Per-call cold start.** Each `extract()` invocation re-loads the model
  from disk (~10-20s). With bindings, the model could load once and stay
  resident across calls. Acceptable for the current use case (summarizing
  long inputs where the load is amortized); would be unacceptable for a
  future low-latency interactive Unit.
- **No shared KV cache across calls.** Each call recomputes the prompt
  prefill. Bindings would let a long-lived session reuse cached state.
- **Subprocess overhead.** Process spawn + model load is more expensive
  than a function call into a resident model. Matters for high-frequency
  invocation; doesn't matter for the current per-document shape.

## Why subprocess won for Intraface specifically

The charter's Test 4 (substrate) requires "code before small model; small
model before Core; Core before human." Units are the *small model* tier.
Their substrate should be the simplest sufficient thing — and the simplest
sufficient thing is a CLI binary launched on demand. Bindings add an NPM
dependency, a Node-version constraint, and a native addon that must
recompile on Node upgrades, in exchange for performance characteristics
Units don't need.

The Core is a different shape — resident, VRAM-continuously allocated,
and served through `ik_llama.cpp`'s `llama-server` over HTTP. Core
profiles and measurements live under `docs/core-model-baselines/`.

## Status of `node-llama-cpp` on this box

As of 2026-07-07, `node-llama-cpp` has been **fully extricated from
active code paths**:

- `~/prj/archive/subagent-summarize/node_modules/` was deleted (733M,
  including the bundled `@node-llama-cpp/` prebuilt libraries).
- No file in `~/prj/intraface/` or `~/.pi/agent/extensions/` imports it.
- The dead spike `test-model.ts` in the archive still references it as
  text, but is no longer runnable — preserved as historical artifact.

**Known straggler:** `~/prj/prtr-config/package.json` still declares
`node-llama-cpp` as a dependency, but `prtr-config` has no `node_modules/`
installed and no active code imports it. That declaration is stale and
lives outside this repo's custody. Cleanup is the prtr-config repo's
concern.

## References

- `units/extract/extract.ts` — the subprocess pattern in production use.
- `~/prj/archive/subagent-summarize/test-model.ts` — the bindings spike
  that was abandoned.
- `engines.toml` — pins the mainstream `llama-cli` build (9861) that
  the subprocess pattern depends on.
- `docs/charter.md` §"The substrate test" — Test 4, the principle that
  informs the decision.

## Outcome (verified 2026-07-15)

The decision remains active for Units. The `extract` Unit still spawns
mainstream `llama-cli` with an argv array and CPU-only GPU visibility.

The same subprocess isolation pattern is also used by the LiveKit voice
adapter to invoke persistent Pi turns. That is a separate caller, not a
Unit inference substrate, but reinforces the process-isolation benefit.
