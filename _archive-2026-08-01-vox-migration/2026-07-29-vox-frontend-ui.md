# Handoff: vox frontend UI development

**Date:** 2026-07-29
**For:** Frontend developer picking up the vox voice chat UI
**Scope:** The browser-side WebRTC client at `experiments/pipecat-web-voice/static/index.html`

**Your companion file:** `docs/voice-chat-evaluation.md`. That's the only
other file you should need. Its **"Reference: shared context"** section has
the current shape of `bot.py`, `server.py`, `static/index.html`, cluster
topology, SSH discipline, schema defect, ADRs, and file locations. Read its
Reference section before starting — anything you'd otherwise lack is there.

If something you need isn't in either this handoff or the evaluation doc's
Reference section, surface it as a gap before guessing.

---

## What exists right now

A single self-contained HTML file (~281 LOC) at `experiments/pipecat-web-voice/static/index.html`. No build step, no framework, no package.json. Vanilla JS + CSS in one file. Served by FastAPI at `GET /` on the bot server (prtr:7878, public-facing via `https://vox.rtr.dev/`).

**Working features:**
- Connect/disconnect button with mic permission prompt
- WebRTC peer connection (audio + video transceivers, even though video is unused — pipecat's SmallWebRTCTransport requires both)
- Trickle ICE candidate exchange via PATCH `/api/offer`
- Data channel created by client (pipecat listens for it server-side)
- Audio playback via `<audio autoplay>` element
- Live transcript panel (user/assistant turns appended as styled divs)
- Connection status indicator (gray/orange/green/red dot)
- Dark theme, mobile-responsive layout

**What's deliberately minimal:**
- No Markdown rendering — transcript is plain text
- No chat history persistence — page refresh loses the conversation
- No voice selection UI
- No file attachments
- No multiple conversation threads
- No copy/share/export

---

## Architecture context (so you don't have to reverse-engineer)

```
Browser (this file)
  │ WebRTC (audio + data channel)
  ▼
crtr:443  Caddy  reverse_proxy → 100.64.0.2:7878
  │
  ▼
prtr:7878  FastAPI + pipecat bot (experiments/pipecat-web-voice/server.py)
  │
  ├──► 127.0.0.1:7712   llama-server (Qwen3.6 Q6_K_P, thinking disabled)
  ├──► 100.64.0.3:7733  Parakeet STT (drtr)
  └──► 100.64.0.3:7744  Chatterbox TTS (drtr, streaming)
```

The frontend talks to exactly one backend: the FastAPI signaling server. It never touches the model services directly.

---

## API contract the frontend uses

### `POST /api/offer`

Request body:
```json
{
  "sdp": "<browser-generated SDP>",
  "type": "offer"
}
```

Response body:
```json
{
  "sdp": "<server-generated SDP answer>",
  "type": "answer",
  "pc_id": "<opaque connection ID>"
}
```

### `PATCH /api/offer`

Request body:
```json
{
  "pc_id": "<from POST response>",
  "candidates": [{
    "candidate": "<ICE candidate string>",
    "sdp_mid": "<sdpMid>",
    "sdp_mline_index": <sdpMLineIndex>
  }]
}
```

Response: `{"status": "success"}`

### Data channel messages (server → client)

The server pushes JSON messages over the data channel (named `"pipecat"`, created by the client). Current message shape:
```json
{"role": "user" | "assistant", "text": "<transcript text>"}
```

The frontend handles these in the `dc.onmessage` handler. **If you add new message types, coordinate the server-side change in `experiments/pipecat-web-voice/bot.py`** — the `TranscriptForwarder` class is what sends these.

---

## Known issues / friction points

1. **The data channel must be created by the client before the offer is sent.** Pipecat's SmallWebRTCTransport listens via `@pc.on("datachannel")` server-side. If you remove or reorder `pc.createDataChannel("pipecat")` relative to `setLocalDescription`/`createOffer`, transcript messages will silently drop. This was a bug we hit during bring-up — see `bot.py` comments in `TranscriptForwarder`.

2. **The connect button must be re-enabled on the `connected` state.** The natural pattern is to disable it during the `getUserMedia`/offer exchange, but if you don't explicitly re-enable on `pc.onconnectionstatechange === "connected"`, it stays disabled after a successful connect. Also a bug we hit.

3. **Browser mic access requires HTTPS.** `http://` origins are blocked except on `localhost`. The deployment uses `https://vox.rtr.dev/` via crtr's Caddy with DNS-01 wildcard certs (already configured — see "Cluster topology" → "Voice-relevant ports" in the evaluation doc's Reference section). Don't change the HTTPS path.

4. **ICE candidates must be queued until `pc_id` is set.** The current code uses `pc.canSendIceCandidates` and `pc.pendingIceCandidates` to handle this. Trickle ICE candidates that arrive before the POST `/api/offer` response can't be PATCHed because `pc_id` isn't known yet.

5. **STUN is configured but TURN is not.** Same-tailnet browser→bot works without TURN. Off-tailnet (laptop on hotel wifi) may fail depending on NAT strictness. If you need off-tailnet, add a TURN server to the `RTCPeerConnection` config.

---

## What "frontend UI dev" could mean — open scope

The current page is intentionally minimal. Likely improvements, in rough order of effort:

| Feature | Effort | Notes |
|---|---|---|
| Markdown rendering for assistant turns | low | use `marked` via CDN; assistant output already has no Markdown by system prompt, but useful if you allow longer responses |
| Chat history persistence (localStorage) | low | survive page refresh; per-session key |
| Copy / export transcript | low | button per turn or whole-conversation export |
| Voice selection UI | medium | requires backend coordination — Chatterbox currently ignores the `voice` field |
| Multiple conversation threads | medium | requires session management; bot currently uses one `LLMContext` per WebRTC connection |
| Settings panel (VAD sensitivity, STT language, TTS speed) | medium | requires pipecat `LLMUpdateSettingsFrame` / `TTSUpdateSettingsFrame` plumbing |
| Visual audio meter (input level) | low | `AudioContext` + `AnalyserNode` on the mic stream |
| Push-to-talk mode (alternative to VAD) | low | disable VAD, gate on spacebar / button hold |
| Reconnection on transient network failure | medium | detect `disconnected` state, attempt ICE restart |
| Mobile-native UX pass | medium | current layout works but isn't optimized for one-handed use |
| Persistent backend-side history (XTDB on prtr:5511) | high | requires schema, API, frontend threading |

---

## Local development setup

The frontend is served by the bot. To develop:

```bash
# On prtr (or any machine that can reach drtr:7733, drtr:7744, prtr:7712)
cd ~/prj/intraface/experiments/pipecat-web-voice
uv sync
uv run python server.py --host 0.0.0.0 --port 7878
```

Then open `http://localhost:7878/` (or `http://100.64.0.2:7878/` from another tailnet machine). `http://localhost` is the one non-HTTPS origin where browsers permit mic access.

**Edit-and-refresh loop:** HTML is read fresh from disk on every `GET /` request. Just save the file and refresh the browser — no restart needed.

**Backend log** is at `~/.intraface/state/pipecat-web-voice.log` on prtr. Watch with `tail -f`.

---

## Files you own

```
experiments/pipecat-web-voice/
├── static/
│   └── index.html          ← this is your file (shape: see Reference section in eval doc)
├── server.py               ← don't touch unless adding new API routes (shape: see Reference)
├── bot.py                  ← don't touch unless changing data-channel message shapes (shape: see Reference)
└── README.md               ← deployment docs
```

The data-channel message contract (`{"role", "text"}`) is the only coupling between frontend and bot. If you want new message types, coordinate with whoever owns `bot.py`'s `TranscriptForwarder` — its current shape is documented in the evaluation doc's Reference section.

---

## Open questions to resolve before significant frontend work

1. **Should the frontend ever need authentication?** Currently anyone on the tailnet who can reach `vox.rtr.dev` can use the bot. The cluster has no auth layer for `*.rtr.dev` services.

2. **Should the frontend support multiple simultaneous users?** Currently one bot process per WebRTC connection. Multiple users = multiple bot processes = multiple `LLMContext`s (no shared state). If you want shared conversation history, that's a backend change.

3. **What's the long-term bar for browser support?** Current page works in any modern Chrome/Firefox/Safari. WebRTC constraints (`RTCPeerConnection`, `getUserMedia`, `createDataChannel`) are universal but mobile Safari has quirks.
