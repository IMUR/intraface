# Vox → Vice migration debrief

**Date:** 2026-08-01
**Author context:** Vice sessions through 2026-07-31
**Audience:** Anyone working in intraface / on Vox, wanting to know what
happened with the successor and what it means for this repo.
**Status:** Vice is live and working at `vce.rtr.dev`; Vox remains
untouched and is still the only rollback-tested service. Vox retirement is
not authorized.

This is a debrief, not a handoff or an instruction. It records what carried
over from Vox into Vice, what diverged, and which threads are still open.
Treat Vice's own docs (`~/prj/vice/docs/`) as the source of truth for
Vice's current state; this document is the bridge back to intraface.

## What Vice is

Vice is the standalone successor to the Vox experiment at
`experiments/pipecat-web-voice/`. Native Pipecat scaffold (not a copy of
Vox), SmallWebRTC transport, same local model stack (Parakeet STT, Qwen LLM
via llama-server, Chatterbox TTS), Forgejo auth, persistent semantic memory
on SurrealDB, and a bounded capability surface (read tools + confirmed
mutations).

```text
source:      ~/prj/vice
web:         https://git.rtr.dev/rtr/vice
public URL:  https://vce.rtr.dev  (live; non-persistent runner)
predecessor: https://vox.rtr.dev  (live; do not disturb)
```

## What carried over from Vox

These were proven by Vox and migrated largely intact:

- **Local OpenAI-compatible adapters.** Parakeet (`:7733`), llama-server
  Qwen (`127.0.0.1:7712`), Chatterbox (`:7744`) all work through Pipecat's
  OpenAI STT/LLM/TTS adapters. Verified again in Vice.
- **Qwen configuration quirks.** The `developer` role rejection (Qwen's
  Jinja template needs `"role": "user"`) and the nested
  `extra_body.chat_template_kwargs.enable_thinking=false` requirement both
  carried over verbatim. These are in Vice's "do not rediscover" list.
- **SmallWebRTC + RTVI contract.** Vox proved the transport; Vice uses the
  native Pipecat runner's `/api/offer` and `/start` and gets RTVI from
  `PipelineWorker` directly — no manual `TranscriptForwarder` needed. The
  copied React frontend in `~/prj/vice/frontend/` is retained as a fallback
  but Pipecat Prebuilt is the current evaluation UI.
- **Capability shape.** Vox's read-only cluster/filesystem/web tools and
  the confirmation-gated mutation pattern informed Vice's 11-tool surface.
  Vice's `server/tools/` is the reference; do not bulk-copy Vox's `tools.py`.

## What diverged

- **No custom signaling server.** Vox runs a hand-rolled FastAPI bot
  process. Vice uses Pipecat's dev runner directly and adds auth via
  middleware on the runner's FastAPI app. This was the right call — the
  runner already provides `/api/offer`, `/start`, `/sessions/*`, RTVI, and
  the Prebuilt UI.
- **Forgejo auth before memory.** Vox had no auth and no stable subject.
  Vice's memory is keyed by the server-derived Forgejo `sub` claim; this
  was a hard gate before any memory work. The auth layer (Authorization
  Code + PKCE, signed session cookies, runner-session-to-subject binding)
  is Vice-specific and not ported from Vox.
- **SurrealDB instead of a vendor memory SDK.** Vox's memory handoff
  (`docs/handoffs/2026-07-29-vox-persistent-memory.md`) evaluated Mem0 and
  alternatives. Vice ruled out any hosted account requirement and built a
  purpose-specific boundary backed by the shared SurrealDB on drtr
  (`nsp_vice/dtb_vice`, isolated from Protext's `nsp_protext`).
- **Memory model.** Vice's `memory_fact` schema, mechanical admission
  policy, extraction (llama-extract via tunnel), embedding (BGE-M3 via
  tunnel), and HNSW vector recall are all new — none existed in Vox.

## What's still genuinely open (affects both repos)

These are tracked as decision forks in `~/prj/vice/docs/HANDOFF.md` and are
likely to surface back here:

- **Memory as primary context layer.** The user's stated direction is that
  voice conversation becomes the through-line and memory replaces
  file-based agent context (like this kind of doc) as the working
  substrate. If that lands, the intraface handoff/handoff-doc pattern
  itself comes into question. Not decided.
- **prtr-local SurrealDB for Vice.** The user frames Vice's schema
  evolution as architectural evidence for Protext. This may pull Vice's
  data off the shared drtr instance onto a dedicated prtr instance.
  Affects Protext planning, not Vox directly.
- **Transcripts as a separate product.** The user reopened raw-transcript
  retention for browsable history. Vox has no such artifact; if Vice
  builds one, the pattern may inform Protext's session-history needs.
- **Vox retirement.** Not authorized. Vice must pass explicit voice,
  frontend, auth, capability, memory, persistence, and rollback gates
  first. Vox stays as rollback.

## What did NOT carry over (and shouldn't)

- Vox's `TranscriptForwarder` — superseded by standard RTVI from
  `PipelineWorker`.
- Vox's hand-rolled FastAPI signaling — the native runner covers it.
- Vox's rsync/dtr-hosted deployment notion (referenced in some older docs)
  — Vice runs on prtr.
- Any Vox-specific auth or subject model — Vox had none; Vice built its
  own.

## What intraface should NOT do

- Do not modify, move, delete, or commit to `~/prj/vice/` from intraface.
  Vice is a separate repo with its own remote.
- Do not retire Vox or redirect `vox.rtr.dev` without explicit user
  approval. Vice work does not authorize touching the live predecessor.
- Do not treat Vice's docs as instructions for intraface work. They
  describe Vice; cross-reference against intraface's own state before
  acting here.

## Pointers

- Vice current state: `~/prj/vice/docs/vice.md`
- Vice memory design: `~/prj/vice/docs/memory.md`
- Vice capability surface: `~/prj/vice/docs/capabilities.md`
- Vice handoff / open forks: `~/prj/vice/docs/HANDOFF.md`
- This migration's TRT-LLM postmortem (relevant to both repos — it's about
  the prtr LLM stack): `docs/trt-llm-postmortem.md` (now in intraface).
