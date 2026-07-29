# vox frontend (dev build)

Redesign of the vox.rtr.dev browser client. Vanilla ES modules, zero
dependencies, no build step — structured so any toolchain (Vite, Svelte,
React, …) can ingest or replace it.

**Contract:** `../docs/vox-frontend-surface.md` is authoritative. Every
backend MUST is annotated inline in `src/signaling.js` with its §-reference.

## Layout

```
frontend/
├── index.html        structure: header / transcript / thinking / footer / hidden <audio>
├── styles.css        dark theme, mobile-first, CSS custom properties
├── src/
│   ├── main.js       UI wiring + connection state machine
│   ├── signaling.js  VoxConnection — WebRTC + /api/offer, all MUSTs (§2–§3)
│   ├── transcript.js turn-atomic store + localStorage persistence (§4)
│   └── meter.js      mic input level via AnalyserNode, AEC-safe (§5)
└── dev_proxy.py      zero-dep static server + /api proxy (see below)
```

## Run it

```bash
cd frontend
python3 dev_proxy.py            # serves :8080, proxies /api → prtr:7878
# open http://localhost:8080/
```

Requires reaching the bot at `http://100.64.0.2:7878` (tailnet). Override
with `--target` / `--port`. `localhost` is the one non-HTTPS origin where
`getUserMedia` works — for anything else, use HTTPS.

## Implemented (Track A — frontend-only, no backend coupling)

- [x] All WebRTC MUSTs: data channel before offer, audio+video m-lines,
      ICE queuing until `pc_id`, STUN-only, remote audio playback
- [x] Connection state machine; connect button re-enables on `connected`
      and becomes disconnect while live
- [x] Turn-atomic transcript (user/core bubbles)
- [x] "thinking…" indicator bridging the 2–3 s post-speech latency window
      (shown when the user turn lands, cleared on the assistant turn)
- [x] localStorage persistence across refresh + clear button
- [x] Mic input level meter
- [x] Mobile-first layout, safe-area insets

## Deliberately not done yet

- Markdown rendering (backend system prompt forbids Markdown today)
- Copy/export per turn
- Reconnection with ICE restart (current behavior: clean teardown on drop)
- Push-to-talk, voice selection, settings — all need backend coordination
  (surface doc §7)

## Testing against the live deployment

This directory is not wired into the FastAPI server (another workstream
owns `experiments/pipecat-web-voice/`). To test the exact production
serving path later, these files can be copied into
`experiments/pipecat-web-voice/static/` — coordinate first.
