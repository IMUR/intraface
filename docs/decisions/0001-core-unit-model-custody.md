# 0001. Core/Unit model custody distinction

Date: 2026-07-07
Status: accepted

## Context

The `~/.intraface/models/` directory holds model weights the Intraface
system has custody of. Two kinds of model are consumed by the Executor
(per charter `docs/charter.md`):

- **Core models** — the single resident model. Long-running,
  VRAM-continuously-allocated, mutually exclusive with each other.
- **Unit models** — spawned à la carte by Units. Per-call processes,
  mutually non-contending, mmap-shared between Units that want the same
  weights.

Initially only one model was slated for Intraface custody
(LFM2.5-1.2B-Instruct, a Unit model). The Core model (GLM-4.7-Flash)
lives at `/home/prtr/models/glm-4.7-flash/` and migration was deferred
because it requires stopping a live service.

Three layout options were considered:

- **A.** `models/core/` and `models/unit/` subdirectories from day one.
- **B.** `models/unit/` only, with the Core situation documented in a
  README; revisit layout when/if GLM actually migrates.
- **C.** Flat `models/<model-name>/`, with role as metadata.

C was rejected because the Core/Unit distinction is **lifecycle-class**,
not labeling: Core models are subject to offload discipline and mutual
exclusion that Unit models are not. That is a real operational difference,
worth encoding in filesystem layout rather than metadata.

## Decision

Adopt **option A**: `~/.intraface/models/{core,unit}/` from day one.

Each Core-model *candidate* lives in its own subdirectory under `core/`
(`glm-4.7-flash/`, etc.); at most one is resident at a time. Multiple
candidates may coexist on disk (active + staged fallback + eval candidate +
rollback), which the `core/` bucket accommodates.

Each Unit model lives in its own subdirectory under `unit/`, named
`<family>-<size>-<variant>/`.

The `core/` directory starts **empty**, with a README stating that GLM
migration is pending (see `docs/glm-migration.md`) and naming the current
location. This is a documented plan, not a silent placeholder.

The charter's claim that "Core — the single resident model" remains
unchanged: "single resident" means one in memory at a time, not one in
existence.

## Consequences

**Positive:**

- The Core/Unit distinction is visible to any agent reading the directory
  from day one, without requiring them to read documentation first.
- Multiple Core candidates on disk (the anticipated future) is
  structurally accommodated without a future rename.
- Role-aware operations ("pause Core for swap-in of new candidate," "spawn
  Unit model with VRAM exclusion") have an obvious filesystem handle.

**Negative:**

- An empty `core/` directory must be accompanied by a README stating the
  migration plan; otherwise it misleadingly implies custody that doesn't
  yet exist.
- The Core/Unit split is duplicated at the engine layer (see `engines.toml`
  `role = "core" | "unit"`), so the two must be kept in sync.

**Charter compatibility:**

- Test 5 (custody): satisfied — `~/.intraface/` reflects what Intraface
  owns (Unit models today; Core model on pending migration).
- Test 4 (substrate): reinforced — the layout makes the role distinction
  that determines substrate selection visible.

## References

- `docs/charter.md` — Core/Unit taxonomy, "single resident model" definition.
- `docs/glm-migration.md` — implications of moving GLM into `core/`
  custody.
- `engines.toml` — pins engine commits and mirrors the core/unit
  distinction at the engine layer.
