# LocalAI and SGLang evaluation — rejected for Intraface substrate

**Date:** 2026-08-01
**Host context:** prtr (dual RTX 3090, Qwen3.6 Core on `:7712`, LFM2.5
Unit on `:7713`), drtr (RTX 2080, Parakeet/Chatterbox + Protext llama stack)
**Evaluated against:** the Intraface charter and ADRs 0001–0008

## Verdict

Both **rejected** as Core/Unit/control-plane substrate. Neither is
adopted. The reasoning is recorded here so the question does not need to
be re-litigated without new evidence, following the same shape as the
TensorRT-LLM postmortem (`docs/trt-llm-postmortem.md`).

---

## LocalAI

**Source:** [mudler/LocalAI](https://github.com/mudler/LocalAI) (MIT,
48k stars, v4.3.0 May 2026)

### What was considered

LocalAI is an open-source AI engine that fronts many backends
(llama.cpp, ik-llama-cpp, vLLM, whisper, parakeet.cpp, TTS, embeddings,
rerank) behind OpenAI/Anthropic/ElevenLabs-compatible APIs. It also
offers a Realtime API (WebSocket + WebRTC), built-in agents (AgentHub),
distributed mode (Postgres + NATS), multi-user auth/quotas, and an OCI
backend gallery.

### Why it looked interesting

- **ik-llama-cpp backend** added April 2026 — could front the Core's
  ik_llama without a custom wrapper.
- **Realtime API pipeline** is the same shape ADR 0006 chose for voice
  (Silero VAD → STT → LLM → TTS), packaged with streaming stages and
  semantic VAD via Parakeet EOU models.
- **Classifier mode** scores fixed options with a small model — the
  docs even cite `lfm2.5-1.2b-instruct`, structurally close to Unit work.
- One OpenAI-shaped URL for every modality.

### Why it was rejected

**As Core substrate (charter failures):**

- LocalAI owns process lifecycle, model YAML, and backend versions.
  Intraface needs the Core's engine pinned at a specific ik_llama commit
  (`engines.toml`), with fork-specific flags (`--n-cpu-moe`, etc.) and
  measured VRAM profiles under `docs/core-model-baselines/`. LocalAI's
  control plane collides with that custody.
- **Test 5 (custody):** Gallery + OCI backends + LocalAI model dirs
  fight `~/.intraface/models/{core,unit}/` and `engines.toml` pin
  discipline.
- **Test 3 (router):** Built-in agents decide tool use themselves.
  Charter: "the router, never the expert, decides what fires."

**As Unit substrate:**

- Overkill vs `llama-cli`/`llama-server` (ADR 0008). Unit needs are
  narrow: GBNF, short ctx, CPU, mmap-friendly weights.
- Adds gallery/OCI/agent surface Intraface does not need for `extract`.
- Classifier mode is a *different Unit shape* (score fixed options), not
  a drop-in for grounded extraction.

**As voice/control plane:**

- Vice already proved Pipecat + OpenAI adapters + Forgejo auth +
  SurrealDB memory. LocalAI Realtime would compete with that product
  surface and pull LLM into LocalAI's pipeline.
- Distributed mode + OIDC + quotas + AgentHub are multi-tenant platform
  features. rtr is single-user, per-node, port-block discipline.

### LocalAI verdict

LocalAI's June 2026 speech stack (parakeet.cpp, realtime streaming,
classifier-on-LFM2.5) is the part that maps onto Intraface. Everything
else — agents, distributed control plane, Core hosting — fights the
charter.

### When to revisit LocalAI

- If Intraface wants **one** modality behind an OpenAI URL (e.g.
  consolidate STT/TTS/embeddings on drtr), LocalAI could be evaluated
  as a **thin gateway** on a single node — not as Core or Executor.
- If a future Unit is genuinely "score N fixed options," LocalAI's
  classifier mode is worth a read, but implementable with the existing
  engine.

---

## SGLang

**Source:** [sgl-project/sglang](https://github.com/sgl-project/sglang)
(LMSYS, Apache-2.0)

### What was considered

SGLang's RadixAttention caches KV state in a radix tree, reusing shared
prefixes across requests. Benchmarks show up to 6× lower TTFT on
shared-prefix workloads (RAG, agent loops, repeated system prompts).

### Why it looked interesting

If Unit calls shared a large stable prefix, SGLang would skip re-prefill
on every call. The question was whether that applies to Intraface Units.

### Why it was rejected

**Unit prompt shape is bulk-unique, not shared-prefix.** For `extract`
(the only shipped Unit):

| Prompt part | Size | Shared across calls? |
|-------------|------|----------------------|
| Primer + instructions | ~150-300 tokens | Yes |
| Source slice | Usually the bulk (up to nearly full ctx) | **No** - different file/range each time |

The shared prefix SGLang would skip is a thin header. Prefill cost is
dominated by the unique source. Intraface is not in the 6× RAG regime;
it is in the "almost everything is new every call" regime.

**What actually hurts Units** is different and unaffected by SGLang:

1. Cold model load (~tens of seconds) — fixed by warm `llama-server`
   (ADR 0008), not by RadixAttention.
2. CPU prefill of unique bulk — every engine pays this.
3. VRAM exclusion from Core — Units stay CPU/`-ngl 0`; SGLang is a
   GPU serving stack in practice.

llama.cpp already covers what Units need: GGUF, GBNF, CPU, pinned in
`engines.toml`, and warm-server prompt cache for the small primer.

### SGLang verdict

SGLang's prefix-cache win does not match Unit shape. Stay on mainstream
`llama.cpp` for Units (ADR 0008).

### When to revisit SGLang

- If a future Unit shares a **large** stable document across many calls
  (e.g. a fixed corpus Unit), SGLang's RadixAttention becomes relevant.
- If Units move to GPU (breaking the CPU-only discipline), re-evaluate
  the serving stack holistically.

---

## Artifacts

- LocalAI README and docs (fetched 2026-08-01):
  `https://github.com/mudler/LocalAI`, `https://localai.io/docs/`
- SGLang paper: [SGLang: Efficient Execution of Structured Language
  Model Programs](https://par.nsf.gov/servlets/purl/10524135) (NSF-PAR)
- Charter five-tests scorecard and role-by-role analysis: this chat
  session (2026-08-01), not separately persisted

## Status

- **LocalAI:** rejected as Core/Unit/control-plane; revisit only as a
  single-modality thin gateway if consolidation is needed.
- **SGLang:** rejected for Units; revisit only if Unit shape shifts to
  shared-large-prefix or Units leave CPU.
- Both decisions are reflected in ADR 0008 (Unit runtime = mainstream
  `llama.cpp`) and the engines.toml pin.
