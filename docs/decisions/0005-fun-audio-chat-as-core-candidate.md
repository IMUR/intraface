# 0005. Fun-Audio-Chat-8B as a peer Core candidate

Date: 2026-07-11
Status: superseded by [0006]

## Context

The Executor currently has two Core candidates on disk:

- **GLM-4.7-Flash-Q8_0** at `~/.intraface/models/core/glm-4.7-flash/` —
  text-only, ~31.8 GB, served via ik_llama.cpp's `llama-server`. Peer
  Core candidate (not currently resident). Baseline recorded at
  `docs/core-model-baselines/glm-4.7-flash.md`.
- **Qwen3.6-35B-A3B-Q8_0** at `~/.intraface/models/core/qwen3.6-35b-a3b/` —
  text-only, ~36.9 GB, served via ik_llama.cpp's `llama-server`. Currently
  resident. Evaluation framework at
  `docs/core-model-baselines/qwen3.6-35b-a3b-evaluation.md`.

Per ADR 0001, multiple Core candidates may coexist on disk with at most
one resident at a time. The user wants to evaluate
**FunAudioLLM/Fun-Audio-Chat-8B** as a third candidate.

## Why Fun-Audio-Chat-8B doesn't fit the existing mold

The two existing Core candidates share a shape:

- Text-in, text-out (via OpenAI-completions HTTP)
- Served by ik_llama.cpp's `llama-server` exposing port 7712
- Pi talks to them via standard chat-completions API
- ~30-40 GB VRAM, GGUF format

Fun-Audio-Chat-8B is a different shape:

- **Audio-in, audio-out** (also supports text I/O)
- **No HTTP server** in the documented quick-start; pure Python inference
  scripts (`examples/infer_s2t.py`, `infer_s2s.py`)
- **Python dependency stack** (transformers, PyTorch, TensorRT, onnxruntime)
  entirely separate from the llama.cpp/ik_llama.cpp substrate
- **~24 GB VRAM** for main model + companion TTS model
  (`Fun-CosyVoice3-0.5B-2512`) recommended on separate GPU
- **Apache 2.0**, ~19 GB safetensors

This raised an initial question: does Fun-Audio-Chat-8B even qualify as
a "Core candidate" or does it require a new tier (sensorimotor layer,
modal bridge, etc.)?

## Decision

**Fun-Audio-Chat-8B is accepted as a peer Core candidate**, not a new
tier. The Core role is "single resident model," not "single resident
text model." When Fun-Audio-Chat is resident, the Executor is in
voice-interaction mode; when Qwen3.6 is resident, it's in
text-reasoning mode. Both are valid Core modes.

This interpretation is consistent with ADR 0001, which already
accommodates multiple Core candidates on disk (active + fallback +
eval + rollback) under a single tier.

### What this ADR does NOT decide

- **Whether Fun-Audio-Chat actually works on this hardware.** That's the
  evaluation, captured at
  `docs/core-model-baselines/fun-audio-chat-8b-evaluation.md`.
- **How Pi integrates with an audio-native Core.** Pi talks
  OpenAI-completions HTTP; Fun-Audio-Chat ships as Python scripts.
  Bridging requires either a custom HTTP wrapper, a standalone web_demo
  deployment, or a hybrid STT+TTS arrangement. Deferred to evaluation
  Phase 3.
- **Whether the runtime stack divergence (Python/PyTorch/UV vs
  llama.cpp) creates charter incompatibility.** The charter's Test 4
  (substrate) says "cheapest sufficient worker." Fun-Audio-Chat's heavier
  substrate is justified by the audio capability it provides, which no
  llama.cpp-served model can match. Defensible.
- **Where source and model files live.** Per ADR 0001 the model files
  land under `~/.intraface/models/core/fun-audio-chat-8b/`. Source
  checkout lives under `~/prj/intraface/vendor/Fun-Audio-Chat/` per
  ADR 0002's dev/tree-is-runtime-target pattern; `vendor/` is in
  `.gitignore` (same rationale as `node_modules/`).

## Consequences

**Positive:**

- **Voice-interaction capability** enters the system as a Core mode,
  not a peripheral feature.
- **ADR 0001's "multiple candidates on disk" pattern** is exercised for
  a meaningfully different shape of model, validating that the pattern
  scales beyond text-only candidates.
- **The charter's Core/Unit taxonomy holds** without modification.
  Adding a new tier would have been a charter change; this avoids it.

**Negative:**

- **No concurrent mode.** Fun-Audio-Chat (~24 GB) + Qwen3.6 (~38 GB) =
  ~62 GB > 48 GB VRAM. Switching between them requires stopping one and
  starting the other — minutes-scale VRAM shuffle, not instant toggle.
- **Python substrate adds operational surface.** UV venv, PyTorch,
  TensorRT, onnxruntime — all need to be installed and maintained
  alongside the existing llama.cpp binaries. Increases the system's
  dependency footprint.
- **Pi integration is unsolved.** Until evaluation Phase 3 happens, we
  don't know whether voice mode goes through Pi at all, runs as a
  separate web_demo, or requires a hybrid two-model flow.
- **Mutual-exclusion enforcement becomes more urgent.** With two
  candidates that could both try to grab VRAM, the lack of a real
  Core-server wrapper script (flagged since 2026-07-07, never built)
  becomes a real risk, not a theoretical one.
- **Correction (2026-07-13):** the earlier addition describing drtr's
  Parakeet/Chatterbox services as an existing Intraface voice pipeline
  was wrong. Those services existed independently and were not wired
  into this stack at the time. Their APIs were later reused by the
  separate LiveKit voice evaluation documented after ADR 0006.

**Charter compatibility:**

- Test 4 (substrate): justified — heavier substrate is the cost of
  audio capability, which text-only candidates cannot provide.
- Test 5 (custody): reinforced — model files land in
  `~/.intraface/models/core/` like the other candidates; source stays
  in `~/prj/intraface/vendor/` per ADR 0002's dev-as-deployment pattern.

## Trigger conditions for revisit

This decision should be revisited if:

1. **Evaluation fails** — Fun-Audio-Chat doesn't run on this hardware
   at acceptable latency/quality. Then this ADR is superseded by a
   "Fun-Audio-Chat rejected" finding, and the candidate stays on disk
   only as a future-VRAM-upgrade option. **(2026-07-12: evaluation did
   not cleanly fail. Phase 1 passed; Phase 2 conditional-passed on
   quality, failed on latency against the stock script. Trigger not
   met on inference grounds alone.)**
2. **Pi integration proves intractable** — the voice mode is so
   operationally different from text mode that it warrants a separate
   tier after all. Then this ADR is superseded by a charter change.
3. **Hardware changes** — if a third GPU or VRAM upgrade makes
   concurrent mode possible, the "peer candidate" framing may give way
   to "always-on voice layer alongside text Core," which would be a
   different architecture.
4. **(Added 2026-07-12) Audio-native reasoning fails to materialize as
   a concrete requirement.** The existing parakeet + chatterbox stack
   on drtr solves the STT/TTS problem at lower operational cost than
   running Fun-Audio-Chat as a resident Core. If no use case emerges
   that specifically requires audio-native reasoning (prosody, tone,
   interruption handling — things the text intermediate throws away),
   this ADR should be superseded by a "peer application" or "deferred
   indefinitely" decision. See the evaluation doc's "Phase 3:
   reframe" section for the three honest paths forward.

## References

- `docs/core-model-baselines/fun-audio-chat-8b-evaluation.md` — the
  evaluation framework with pass/fail criteria.
- `docs/decisions/0001-core-unit-model-custody.md` — the multiple-
  candidates-on-disk pattern this decision relies on.
- `https://huggingface.co/FunAudioLLM/Fun-Audio-Chat-8B` — model card.
- `https://github.com/FunAudioLLM/Fun-Audio-Chat` — source repo with
  inference scripts.
- `.archive/Orchestrator_Model_Investigation_Report.md` — earlier analysis that
  flagged "voice pipeline — confirmed to be an I/O layer" as an open
  question. This ADR partially answers it: voice I/O is delivered by
  swapping Core mode, not by an external STT/TTS layer.
