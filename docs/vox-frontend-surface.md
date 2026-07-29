# vox frontend surface profile

**Date:** 2026-07-29
**Purpose:** The complete contract between the vox backend and any browser
frontend, written so that a redesign of the UI can start from scratch
without reading the current `index.html`. If your design satisfies every
"MUST" here and accounts for every behavior in "Runtime characteristics,"
it will work against the live backend.

**Source of truth:** Derived from `docs/voice-chat-evaluation.md` and
`docs/handoffs/2026-07-29-vox-frontend-ui.md`, then **re-verified against
live source on 2026-07-30** (server.py 111 LOC, bot.py 328 LOC, tools.py
891 LOC). Where the docs and reality drift, reality wins — surface the
drift.

**Coordination note:** `bot.py` and `server.py` are owned by another
workstream. Everything under "Backend-coupled extension points" requires
coordination before a frontend can rely on it.

---

## 1. Deployment and serving model

| Fact | Value |
|---|---|
| Public URL | `https://vox.rtr.dev/` |
| Edge | crtr:443 Caddy, DNS-01 wildcard certs, `reverse_proxy → 100.64.0.2:7878` |
| Origin | prtr:7878, FastAPI (`server.py`, 77 LOC), host `0.0.0.0` |
| Frontend source | `frontend/` (repo root) — React + Vite app, builds to `frontend/dist/`. Legacy zero-dep client at `frontend/vanilla/` |
| Build step | Vite (`npm run build`) for the React app; none for the vanilla client |
| Serving | `GET /` serves the React `dist/index.html`; `/assets/*` hashed build assets; `/vanilla/*` vanilla fallback; `/static/*` legacy mount retained |
| Dev loop | React: `npm run dev` in `frontend/` (Vite proxies `/api` → prtr:7878). Vanilla: edit-and-refresh, no restart |
| Local dev | `cd experiments/pipecat-web-voice && uv sync && uv run python server.py --host 0.0.0.0 --port 7878` |
| Backend log | `~/.intraface/state/pipecat-web-voice.log` on prtr |

**Constraints this imposes on a redesign:**

- HTTPS is mandatory for mic access (`getUserMedia` is blocked on `http://`
  origins except `localhost`). Do not change the HTTPS path.
- The frontend talks to exactly one origin (the FastAPI signaling server).
  It never touches the model services (STT/LLM/TTS) directly.

---

## 2. Signaling API (the only HTTP surface)

### `POST /api/offer`

Request:
```json
{ "sdp": "<browser-generated SDP offer>", "type": "offer" }
```
Response:
```json
{ "sdp": "<server SDP answer>", "type": "answer", "pc_id": "<opaque connection ID>" }
```
Each POST spawns a bot instance (`run_bot`) as a background task. One
WebRTC connection = one bot = one fresh conversation.

### `PATCH /api/offer`

Trickle ICE. Request:
```json
{
  "pc_id": "<from POST response>",
  "candidates": [{
    "candidate": "<ICE candidate string>",
    "sdp_mid": "<sdpMid>",
    "sdp_mline_index": 0
  }]
}
```
Response: `{"status": "success"}`

### `GET /` and `GET /static/*`

Serves the frontend. No other routes exist.

---

## 3. WebRTC transport requirements (MUST)

These are hard requirements of pipecat's `SmallWebRTCTransport`. A
redesign that violates any of them fails silently or times out.

1. **MUST create the data channel before sending the offer.**
   `pc.createDataChannel("pipecat")` must be called before
   `setLocalDescription(await pc.createOffer())`. Pipecat listens
   server-side via `@pc.on("datachannel")`. Without this the channel never
   opens, transcripts silently drop, and the server times out after 10 s.
   The channel name MUST be `"pipecat"`.

2. **MUST add both audio and video transceivers** (`sendrecv` each), even
   though video is unused. SmallWebRTCTransport requires both.

3. **MUST queue outgoing ICE candidates until `pc_id` is known.**
   Candidates gathered before the POST response returns cannot be PATCHed.
   Current implementation pattern: `pc.pendingIceCandidates[]` flushed when
   `pc_id` arrives.

4. **MUST configure STUN only** (`iceServers: [STUN]`). No TURN exists.
   Same-tailnet clients work; off-tailnet clients behind strict NAT may
   fail. Adding TURN is a config change, not a code requirement.

5. **MUST play remote audio from `pc.ontrack`** into an `<audio autoplay>`
   element (or equivalent Web Audio graph).

6. **MUST handle the full connection-state machine**, including
   re-enabling UI on `connectionState === "connected"` (a bug hit during
   bring-up: the connect control stayed disabled after success).

---

## 4. Data channel contract

Two protocols share the data channel today:

**Primary: RTVI** (`label: "rtvi-ai"` envelopes, bidirectional). Active by
default via `PipelineWorker(enable_rtvi=True)` — no bot.py change was ever
needed. The client SDK sends `client-ready` and can send `send-text`;
the server emits the full typed event stream: `bot-ready`,
`user-started/stopped-speaking`, `vad-user-started/stopped-speaking`,
`user-transcription`, `bot-llm-text` (streaming tokens), `bot-output`
(sentence-aggregated, with `spoken`/`unspoken` split for karaoke sync),
`bot-started/stopped-speaking`, `bot-transcription`, `metrics`, `error`,
plus function-call events (`llm-function-call-*`).

**Legacy: raw turn messages** (server → client only):
```json
{ "role": "user" | "assistant", "text": "<transcript text>" }
```
Sent by the `TranscriptForwarder` class in `bot.py` (two instances:
user-side between STT and user aggregator; assistant-side between LLM and
TTS), kept for the vanilla client at `/vanilla/`. One message per completed
turn, not incremental. New work should consume RTVI, not this.

---

## 5. Audio behavior the UI must account for

- **Always-listening mic.** `getUserMedia({audio: true})` at connect;
  no push-to-talk. VAD (Silero, 0.2 s start) + Smart Turn v3.2 decide
  turn boundaries server-side. The frontend has no role in endpointing.
- **Echo cancellation is the browser's job.** Standard `getUserMedia` AEC
  handles the bot's own audio; no self-triggering occurs. A redesign using
  a custom Web Audio graph must not bypass AEC.
- **Barge-in is always on.** User speaks mid-playback → server detects
  speech-start in ~200 ms, playback cuts within ~10 ms, new turn proceeds.
  The frontend does nothing to support this — but the UI should expect
  assistant turns to be cut short, and transcripts may describe a response
  the user didn't hear to completion.
- **Bot audio arrives as 20 ms chunks** (`audio_out_10ms_chunks=2`).
  Relevant only if replacing `<audio>` with a Web Audio pipeline.
- **Audible artifacts to expect (backend known issues, not UI bugs):**
  - ~30–50 ms silence gaps between TTS chunks (per-sentence)
  - Single-word utterances (e.g. "Hello") may sit ~3 s in Smart Turn
    before responding (returns `INCOMPLETE`, waits the silence window)

---

## 6. Runtime characteristics (latency and state)

### Latency budget (measured 2026-07-29)

| Stage | Time |
|---|---|
| VAD → Smart Turn `COMPLETE` | ~1.5–2 s (utterance-dependent) |
| Parakeet STT | ~80–300 ms |
| LLM TTFB (thinking off) | ~250–350 ms, then streams |
| Chatterbox TTS first audio | ~1.3–2.1 s |
| **End-of-speech → first audio (typical)** | **~2–3 s** |

**Design consequence:** after the user stops speaking there is a 2–3 s
window with no audible feedback, and the user transcript arrives early in
that window but the assistant transcript arrives at the end. A good UI
needs an explicit intermediate state (processing/thinking) — the current
minimal UI has none.

### Session/state model

- **No server-side persistence.** Each WebRTC connection starts with a
  fresh `LLMContext` (system prompt only). Disconnect = conversation gone.
- **One bot per connection.** No shared state across users or sessions.
- **No auth.** Anyone who can reach `vox.rtr.dev` on the tailnet can use it.
- **Assistant output style is constrained by system prompt:** plain spoken
  language, short responses, tool-first behavior on cluster queries. The
  bot has an identity ("Vox") and read-only cluster tools (node health,
  services, logs, ports, filesystem reads — see `PROGRESS.md`).
  `max_completion_tokens` is 300.
- **Bot durability:** the backend is a `nohup` process; it can die. UI
  should treat connection failure as a normal, recoverable state.

### What the frontend cannot control today

- Voice selection: the `voice` field is sent but Chatterbox ignores it
- No way to request history, threads, or identity — none exist server-side
- Settings (VAD sensitivity, TTS speed): no plumbing yet, though RTVI
  `client-message` is the natural channel when added

---

## 7. Backend-coupled extension points (coordination required)

**2026-07-30 update:** most of this table is already available. RTVI is
active by default in pipecat-ai 1.6.0 (`PipelineWorker(enable_rtvi=True)`
auto-creates the processor and observer), so the typed event stream —
streaming transcripts, speaking state, `send-text` — already flows on the
data channel. Verified in the installed source
(`pipecat/pipeline/worker.py`). The React client at `frontend/` consumes it
today. An earlier handoff (`2026-07-30-vox-rtvi-backend.md`) wrongly listed
this as a required backend change; it is stamped stale with the correction.

A redesign that wants any of these must coordinate with the `bot.py` /
`server.py` owner before relying on it:

| Want | Where the change lands |
|---|---|
| New data-channel message types (streaming tokens, partial STT, state events like `thinking`/`speaking`/`interrupted`) | `TranscriptForwarder` / new `FrameProcessor`s in `bot.py` |
| Client→server control messages (push-to-talk, settings, barge-in hint) | Data channel receive handler — does not exist today; new code in `bot.py` transport wiring |
| Settings plumbing (VAD sensitivity, TTS speed) | pipecat `LLMUpdateSettingsFrame` / `TTSUpdateSettingsFrame` |
| Voice selection | Chatterbox wrapper on drtr (`/opt/services/chatterbox-tts/app.py`) must honor `voice` |
| Persistent history / threads | New API routes in `server.py` + XTDB (available at prtr:5511, pgwire) |
| TURN server for off-tailnet | `RTCPeerConnection` config (frontend-side, but infra to provision) |

---

## 8. Landmines (bugs already hit once — do not rediscover)

1. Data channel must be created before the offer (§3.1).
2. Connect control must be re-enabled on `connected` state (§3.6).
3. ICE candidates must be queued until `pc_id` exists (§3.3).
4. Mic requires HTTPS; `http://localhost` is the sole exception (§1).
5. `TranscriptForwarder` must use `send_app_message`, not
   `transport.send_message` (backend-side, noted for anyone touching §7).
6. ~~llama-server JSON-schema defect~~ — **resolved** (stamped in
   `engines.toml`). The bot registers tools via `FunctionSchema`
   auto-derivation today. Historical note only.

---

## 9. Browser support bar

- Works today: modern Chrome, Firefox, Safari on the tailnet.
- Required APIs: `RTCPeerConnection`, `getUserMedia`, `createDataChannel`
  — universal, but mobile Safari has quirks.
- Mobile layout: current page is responsive but not one-handed-optimized.

---

## 10. Design freedom summary

**Freely changeable (pure frontend):** everything visual and interactive —
layout, theme, framework choice, transcript rendering, localStorage
history, audio metering, reconnection UX, export/copy, mobile UX.

**Fixed by the backend:** the signaling API shapes (§2), the WebRTC
requirements (§3), the data channel name `"pipecat"` (§4), the latency
profile (§6), always-on VAD + barge-in, no server persistence, no auth.

**Negotiable with coordination:** anything in §7.
