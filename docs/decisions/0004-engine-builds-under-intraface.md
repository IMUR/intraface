# 0004. Engine build outputs live in `~/.intraface/builds/<fork>/`

Date: 2026-07-07
Status: deprecated (execution abandoned 2026-07-07)

## Context

The Executor depends on **two forks of llama.cpp**:

- `~/prj/llama.cpp/` — mainstream, build `9861`. Serves Units via `llama-cli`.
- `~/prj/ik_llama.cpp/` — ikawrakow's fork, build `4681`. Serves the Core via `llama-server`, using fork-specific flags (`-cram`, `--ctx-checkpoints`, `--n-cpu-moe`).

The two forks are **not interchangeable** for the Core's purposes —
ik_llama-specific features are required for GLM. They are also not
interchangeable on disk: **both produce binaries and libraries with the
same names** (`llama-cli`, `llama-server`, `libllama.so`, `libggml.so`,
…). Any deployment scheme must namespace the forks apart; otherwise one
overwrites the other, or a binary from one fork tries to load a library
from the other and fails.

Today, build outputs from both forks live inside their respective source
trees at `~/prj/{llama,ik_llama}.cpp/build/bin/`. Four symlinks in
`~/.local/bin/llama-*` point at mainstream's build outputs and exist on
`PATH`. This is the ADR 0002 collapse (dev-tree-as-runtime) applied to
binaries: the "deployed" artifacts are build outputs in source trees.

Additionally, the symlink at `~/.local/bin/llama-server` is
**misleading**: it points at mainstream's `llama-server`, but the live
Core process runs ik_llama's `llama-server` via absolute path. The
symlink is unused by anything that matters and would do the wrong thing
if invoked.

## Decision

**Build outputs for both forks land in `~/.intraface/builds/<fork>/`**,
namespaced by fork:

```
~/.intraface/
├── models/                       (per ADR 0001)
├── state/
└── builds/
    ├── llama.cpp/                ← mainstream build output
    │   └── bin/
    │       ├── llama-cli
    │       └── *.so files
    └── ik_llama.cpp/             ← ik_llama build output
        └── bin/
            ├── llama-server
            └── *.so files
```

Each fork's build outputs live under their own subtree. **No fork's
output can collide with another's.** Source trees at `~/prj/{llama,
ik_llama}.cpp/` become just source — they can be deleted, re-cloned, or
experimented on without affecting the deployed binaries.

Mechanism for getting build outputs there is **a separate, deferred
decision** (see "Open questions" below). The layout itself is what this
ADR commits to.

### What this ADR does NOT decide

- **Source tree location.** The source checkouts stay at `~/prj/` for
  now. Moving them under `~/prj/intraface/vendor/` or submoduling them
  are separate decisions; this ADR doesn't require either.
- **The dispatch mechanism.** Whether callers invoke
  `~/.intraface/builds/llama.cpp/build/bin/llama-cli` directly, via a
  symlink, via PATH, or via a future `intraface` wrapper CLI is a
  separate decision. With only two call sites today (`extract.ts` for
  Units, the GLM launch command for the Core), a wrapper would be
  premature indirection.
- **The install step.** Whether build outputs land in
  `~/.intraface/builds/<fork>/` via `cmake -B`, via
  `-DCMAKE_RUNTIME_OUTPUT_DIRECTORY`, via `cmake --install`, or via a
  manual copy after each successful build is a separate decision. Each
  has different implications for `.so` file placement, RUNPATH, and
  update workflow.

## Consequences

**Positive:**

- **Fork namespace collision solved structurally.** Both forks produce
  same-named binaries; the directory layout keeps them apart by
  construction. No more "which `llama-server` did I just run?"
- **Source/build separation.** `~/prj/llama.cpp/` and
  `~/prj/ik_llama.cpp/` stop being runtime targets. A failed or
  in-progress build in the source tree cannot break the deployed
  binaries.
- **Install discipline emerges.** There is now a real step between
  "I ran `cmake --build`" and "the new binary is live." That step is
  where testing, rollback, and version-pinning happen — partially
  paying ADR 0002's debt early.
- **Consistent with ADR 0001.** `~/.intraface/` becomes the single
  runtime surface: models under `models/`, builds under `builds/`,
  state under `state/`. Source stays in `~/prj/`.

**Negative:**

- **An install step is introduced.** Every engine update now requires
  not just `cmake --build` but also whatever mechanism lands the output
  in `~/.intraface/builds/<fork>/`. Easy to forget; failure mode is
  "running an older binary than you thought."
- **RUNPATH may need attention.** Binaries built with absolute RUNPATH
  pointing at their source-tree build dir will still look there for
  `.so` files. If we want true source/build separation, RUNPATH needs
  to point at `~/.intraface/builds/<fork>/...` instead. Mechanism TBD.
- **Existing `~/.local/bin/llama-*` symlinks become stale** once this
  lands. They currently point at the source-tree build dirs. Either
  they get repointed at `~/.intraface/builds/llama.cpp/build/bin/*`,
  or they get removed (with PATH adjusted, or callers updated to use
  the new absolute paths).

**Charter compatibility:**

- Test 4 (substrate): reinforced. Two substrates for two tiers, with
  distinct custody.
- Test 5 (custody): improved. `~/.intraface/builds/` owns what Intraface
  deploys; `~/prj/{llama,ik_llama}.cpp/` owns what's source. Custody
  boundary is honest.
- ADR 0002 (dev-as-deployment): would have been superseded for binaries
  if this layout had shipped. It did not; engine binaries remain in the
  source-tree build directories.

## Open questions (deferred to execution time)

1. **Build mechanism.** `cmake -B ~/.intraface/builds/llama.cpp -S
   ~/prj/llama.cpp` is the leading candidate (out-of-source build with
   the build dir under `.intraface`). Need to verify both forks build
   cleanly this way without RUNPATH surprises.
2. **RUNPATH handling.** May need `-DCMAKE_BUILD_RPATH` or
   `-DCMAKE_INSTALL_RPATH` at configure time, or `patchelf` after the
   fact, to make binaries find their `.so` files in the new location.
3. **`~/.local/bin/llama-*` disposition.** Repoint, remove, or leave
   for now. The `llama-server` symlink is misleading and should
   probably go regardless; the others may stay until ADR 0002's full
   resolution.
4. **Whether to also move source trees.** Out of scope here.

## Status

Execution was attempted and abandoned. `cmake --install` produced a
clean prefix but stripped the binaries' runtime library paths; the
installed binaries could not find their shared libraries without
`LD_LIBRARY_PATH`, a rebuild with install RPATH, or `patchelf`.

The temporary build trees and unusable install were removed. Live
runtime remains:

- Mainstream llama.cpp from `~/prj/llama.cpp/build/bin/`
- ik_llama.cpp from `~/prj/ik_llama.cpp/build/bin/`
- Existing `~/.local/bin/llama-*` symlinks still target mainstream
  build outputs

ADR 0002 was therefore **not** partially superseded for binaries by this
decision. ADR 0007 later superseded ADR 0002 for cross-node deployment
for different reasons.

## References

- `engines.toml` — pins both forks' commits and records their roles.
- `docs/decisions/0002-dev-tree-is-runtime-target.md` — remained in
  force after this execution attempt; later superseded by ADR 0007.
- `docs/decisions/0003-subprocess-over-bindings.md` — how Units invoke
  `llama-cli`; the dispatch site that this ADR's layout affects.
- `.archive/glm-migration.md` — the Core launch record references
  `~/prj/ik_llama.cpp/build/bin/llama-server` today; will need updating
  when this ADR executes.
