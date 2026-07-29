# Handoff: add RTVI protocol support to the vox bot

> **STATUS: STALE / SUPERSEDED (2026-07-29).** Read this addendum first.
>
> Investigation during the frontend swap revealed two errors in the
> original handoff below:
>
> 1. **RTVI is already active by default.** pipecat-ai 1.6.0's
>    `PipelineWorker.__init__` has `enable_rtvi=True` as the default,
>    auto-creating `RTVIProcessor` and `RTVIObserver` when none are passed.
>    Bot logs from 09:49 today show `RTVIProcessor#0..#4` linked into every
>    pipeline session. No change to `bot.py` was needed for the handshake
>    plumbing — it was already happening.
> 2. **`RTVIConfig(config=[])` does not exist in 1.6.0.** The recommended
>    import path (`from pipecat.processors.frameworks.rtvi import RTVIConfig`)
>    fails. The real API is `PipelineWorker(rtvi_processor=...,
>    rtvi_observer_params=...)` — and again, both auto-create by default.
>
> The frontend was swapped to be the live page at `/` on 2026-07-29 with
> the vanilla client kept at `/vanilla/` as fallback. **However, if the
> React client still hangs on connect, the cause is NOT missing RTVI.**
> See `PROGRESS.md` → "OPEN: React client may still hang on connect" for
> the candidate causes worth investigating next.
>
> Original handoff retained below for provenance. Do not act on it without
> first re-verifying the premise against the live bot.

---

**Date:** 2026-07-30
**For:** Owner of `experiments/pipecat-web-voice/bot.py`
**From:** vox frontend workstream (`frontend/`)
**Scope:** One additive change to `bot.py` — insert pipecat's RTVI processor
into the pipeline so the browser client SDK can connect. No behavior change
for the existing voice path.

**Your companion files:** `docs/voice-chat-evaluation.md` (Reference section
has the current `bot.py` shape) and `docs/vox-frontend-surface.md` (the
frontend/backend contract this change extends).

---

## Why this is needed

The new frontend (`frontend/`, React) is built on the Pipecat Client SDK
(`@pipecat-ai/client-js`) and the Pipecat Voice UI Kit. That client speaks
the **RTVI protocol** over the WebRTC data channel:

1. After media connects, the client sends a `client-ready` message and
   blocks until the bot responds with `bot-ready`.
2. From then on the UI is driven by typed RTVI events
   (`user-transcription`, `bot-llm-text`, `bot-started-speaking`, …).

Today `bot.py` only pushes raw `{"role", "text"}` JSON via
`TranscriptForwarder._send()` and never reads client→server messages.
Result if the new client connects today: WebRTC media comes up, but the
client waits forever for `bot-ready` and the UI never activates.

pipecat-ai 1.6.0 already ships everything needed — this is the standard
pattern from every pipecat web example. No new dependencies, no changes to
STT/LLM/TTS config.

## Requested change (additive)

In `run_bot()`:

```python
from pipecat.processors.frameworks.rtvi import RTVIProcessor, RTVIObserver, RTVIConfig

# after transport is constructed:
rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

# pipeline order — rtvi goes directly after transport.input():
#   transport.input() → rtvi → stt → user_transcript → user_aggregator →
#   llm → assistant_transcript → tts → transport.output() → assistant_aggregator

# attach the observer to whatever runs the pipeline:
#   PipelineTask(..., observers=[RTVIObserver(rtvi)])
# (the eval doc shows a PipelineWorker/WorkerRunner shape — the observer
# attaches the same way; RTVIObserver wraps the rtvi processor instance)
```

That is the whole change. `RTVIProcessor` handles the `client-ready` →
`bot-ready` handshake itself once it's in the pipeline; the observer is
what turns pipeline frames into the typed event stream.

## What the frontend will consume

| RTVI event | Frontend use |
|---|---|
| `bot-ready` | session activation (gates the whole UI) |
| `user-started-speaking` / `user-stopped-speaking` | speaking indicator, barge-in feedback |
| `vad-user-started-speaking` / `vad-user-stopped-speaking` | raw VAD signal for the mic meter state |
| `user-transcription` (`final` flag) | user turns in transcript; partials when available |
| `bot-llm-text` | streaming assistant transcript (typewriter) |
| `bot-transcription` / `bot-output` | sentence-aggregated assistant turns (fallback) |
| `bot-started-speaking` / `bot-stopped-speaking` | "speaking" state on the voice visualizer |
| `error` | error surface |

Future (not required now): `send-text` gives the UI a text input path, and
`client-message`/`server-message` covers settings plumbing — both come free
with RTVIProcessor. Don't build anything extra for these.

## Backward compatibility

The current `static/index.html` expects the raw `{"role", "text"}` messages
from `TranscriptForwarder`. **Please leave both `TranscriptForwarder`
instances in place** — they are harmless alongside RTVIProcessor and keep
the deployed page at vox.rtr.dev working until the React app replaces it.
We'll flag when the old page is retired so the forwarders can be removed.

## Verification

1. Bot starts unchanged; existing `static/index.html` session still works
   end-to-end (voice + transcript).
2. RTVI handshake: with the React dev build
   (`cd frontend && npm run dev`, see `frontend/README.md`), the UI should
   reach its ready state within ~1 s of media connect, and
   speaking/transcript events should drive the visualizer and thread.
3. If you want a lighter check before the React app is up: any RTVI-capable
   client (e.g. pipecat's JS quickstart) should receive `bot-ready` after
   sending `client-ready`.

## Out of scope (flag, don't build)

- Voice selection, settings plumbing, persistence, threads — frontend
  workstream items tracked in `docs/vox-frontend-surface.md` §7.
- Removing `TranscriptForwarder` (happens when the old page retires).
