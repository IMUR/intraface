# 0002. Dev tree is the runtime target (collapsed deployment)

Date: 2026-07-07
Status: accepted

## Context

The Intraface system is currently operated with **no install step between
source and runtime.** The dev checkout at `~/prj/intraface/` is *also* the
runtime target: Pi's extension shim imports the Unit via an absolute path
straight into the source tree —

```ts
// extensions/pi/extract.ts
import { extract } from "/home/prtr/prj/intraface/units/extract/extract.ts";
```

— and the `extract` Unit in turn reads its model from `~/.intraface/models/`
via `os.homedir()`, which *is* portable. The asymmetry is real: **runtime
data is portable; runtime code is not.**

This collapse has concrete implications:

- **Edit-in-place is mandatory.** An uncommitted change in the working
  tree *is* a deployed change. There is no "stable install" distinct from
  "dev checkout."
- **Rollback is `git checkout`.** No way to revert the live system without
  reverting source.
- **Machine-coupling.** Cloning the repo to `/home/someoneelse/prj/intraface/`
  would require editing the shim's import path before the system would
  work — which would then commit machine-specific paths into git.
- **`SPECIALIST_MODEL_PATH` is overridable; the import path is not.** The
  env-var escape hatch on the model side has no analog on the code side.

This is currently **charter-compatible.** Per `docs/charter.md` §"What
Intraface is not": *"Not a framework or a product. It is a discipline
applied to one deployment. One machine, one operator."* A single deployment
does not require a stable/dev separation. This ADR records that the collapse
is a deliberate current-state choice, not an oversight, and names the
conditions under which it should be revisited.

## Decision

Accept the dev-as-deployment collapse as the current operating mode.

- Runtime data (models, state) lives under `~/.intraface/` and is
  portable via `os.homedir()`.
- Runtime code lives at `~/prj/intraface/` and is **not** portable; the
  Pi shim's import path is absolute.
- No install step exists between source and runtime.
- The asymmetry between portable data and machine-coupled code is
  acknowledged debt, not a bug.

This debt is **not** to be paid reflexively. It is paid only when one of
the trigger conditions in §"Trigger conditions" fires.

## Consequences

**Positive (today):**

- Zero install-step overhead. Edits take effect on next Pi restart.
- No drift between "what's in the repo" and "what's running" — they
  are by construction the same thing.
- Simpler mental model for a one-machine, one-operator system.

**Negative (today):**

- Uncommitted experiments are live. A breakage in the working tree is a
  breakage in the deployed system.
- No way to A/B two versions of the Unit on the same machine without
  filesystem gymnastics.
- The repo cannot be cloned-and-run on another machine without source
  edits.

**Negative (future, if unpaid):**

- Portability debt compounds. Every new shim (Slack? MCP? CLI?) that
  hardcodes `/home/prtr/prj/intraface/...` adds another edit-site to
  fix when the migration finally happens.
- The temptation to "clean it up later" increases as the system grows.

## Trigger conditions

Revisit this decision — and likely supersede via a new ADR — when **any**
of these becomes true:

1. **Second machine.** Intraface needs to run on a node other than prtr.
2. **Second operator.** Someone other than prtr's user operates the system.
3. **Stable/dev split needed.** Experiments in the working tree start
   conflicting with the need for a reliable live system (e.g. an
   `extract` regression takes down Pi mid-session).
4. **Atomic rollback needed.** A bad Unit change needs to be reverted
   without `git checkout` (which would also revert any in-flight work).
5. **Second deployment surface.** A non-Pi shim (CLI subcommand, MCP
   server, HTTP endpoint) lands and the per-surface import path
   hardcoding becomes obviously wrong.

## Shape of the likely supersession

When triggered, the fix is an install layer between source and runtime:

```
~/.intraface/
├── models/      (already portable)
├── state/       (already portable)
├── bin/         ← NEW: installed Units + shims
│   ├── units/extract/...
│   └── extensions/pi/...
└── lib/         ← NEW: shared helpers (when runLlama is factored out)
```

Plus an install command (`make install`, a tiny shell script, or similar)
that bridges `~/prj/intraface/` → `~/.intraface/bin/`. The Pi shim's
import path then becomes `os.homedir()`-relative and the system is
portable.

Three real mechanism choices at that point (symlinks vs. copy vs. proper
package) — decision deferred to the superseding ADR.

## References

- `docs/charter.md` §"What Intraface is not" — "discipline applied to one
  deployment" framing that makes this collapse acceptable today.
- `extensions/pi/extract.ts` — the absolute-path import that is the most
  concrete symptom of this collapse.
- `units/extract/extract.ts` — the `os.homedir()`-relative `MODEL_PATH`
  showing the data side is already portable; the asymmetry.
- `docs/decisions/0001-core-unit-model-custody.md` — same series, same
  custody-thinking applied to models rather than code.
