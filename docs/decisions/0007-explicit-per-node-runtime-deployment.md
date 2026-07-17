# 0007. Explicit per-node runtime deployment

Date: 2026-07-15
Status: accepted

Supersedes: [0002]

## Context

ADR 0002 accepted a temporary collapse in which the prtr development
checkout was also the runtime target. It explicitly required
reconsideration when a second machine, operator, or deployment surface
appeared.

Those triggers fired:

- The LiveKit voice client runs on trtr because the microphone and
  speakers are physically attached there.
- Pi/Qwen and the A2A facade run on prtr.
- Parakeet STT and Chatterbox TTS run on drtr.
- The trtr client is copied from the canonical prtr checkout and creates
  its own UV environment.

The statement "the dev tree is the runtime target" is no longer true for
the complete system.

## Decision

The Intraface repository remains the canonical source, but runtime
deployment is explicit per node.

- **prtr-local incubating code** may still execute directly from the
  checkout while ADR 0002's technical debt remains unresolved.
- **Cross-node components** must be copied or installed to a
  node-specific runtime/project path with a documented command.
- Dependencies are recreated from lockfiles; `.venv` and generated
  artifacts are never copied.
- Runtime configuration must identify the actual resident model,
  context window, endpoints, and node.

Current voice deployment:

```text
prtr source:
  ~/prj/intraface/experiments/livekit-voice-agent/

trtr runtime copy:
  ~/prj/intraface-client/livekit-voice-agent/

sync:
  rsync -az --exclude .venv --exclude __pycache__ \
    prtr:/home/prtr/prj/intraface/experiments/livekit-voice-agent/ \
    ~/prj/intraface-client/livekit-voice-agent/

install:
  uv sync
```

The prtr A2A facade remains a local runtime process sourced from
`experiments/a2a-voice-bridge/`. This is still direct-from-dev debt, but
it no longer defines the deployment policy for the whole system.

## Consequences

**Positive:**

- Source custody and runtime placement are no longer conflated across
  nodes.
- trtr can own its physical audio interface without moving Pi or model
  weights.
- UV lockfiles make the client environment reproducible.
- Node-specific failures are easier to isolate.

**Negative:**

- A sync/install step exists and can be forgotten.
- Source and deployed copies can drift.
- No automated release/version marker exists yet.
- prtr-local components still run directly from the checkout.

## Follow-up triggers

Introduce a formal install/release mechanism when:

- More than one cross-node component exists.
- Manual rsync drift causes a failure.
- Atomic rollback or versioned deployments are required.

## References

- [0002] `docs/decisions/0002-dev-tree-is-runtime-target.md`
- `docs/voice-chat-evaluation.md`
- `experiments/livekit-voice-agent/README.md`
