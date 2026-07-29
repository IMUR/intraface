# vox frontend

Browser client for vox.rtr.dev. Two implementations:

```
frontend/
├── vanilla/          ← zero-dependency reference build (ES modules, no build
│                       step). Canonical implementation of the backend contract.
│                       Serve: cd vanilla && python3 dev_proxy.py  → :8080
├── src/              ← React app (primary, in development)
│   ├── App.tsx           PipecatAppBase wiring (SmallWebRTCTransport → /api/offer)
│   └── vox/
│       ├── Session.tsx           layout: status / visualizer / thread / controls
│       └── ConversationThread.tsx bridge: usePipecatConversation →
│                                  assistant-ui external-store runtime
├── package.json      Vite + React 19 + TS + Tailwind 4
└── vite.config.ts    dev server :5173, proxies /api → prtr:7878
```

**Contract:** `../docs/vox-frontend-surface.md` is authoritative for the
backend surface. `vanilla/src/signaling.js` has every MUST annotated inline.

**Stack:** [Pipecat Voice UI Kit](https://voiceuikit.pipecat.ai/) (voice
session, visualizer, mic control) + [assistant-ui](https://www.assistant-ui.com/)
(thread rendering), both on the Pipecat Client SDK's RTVI event stream.

## Run

```bash
npm install
npm run dev        # http://localhost:5173 (localhost origin = mic permitted)
```

Must run on a machine that can reach `http://100.64.0.2:7878` (tailnet).
From off-prtr: `ssh -L 5173:127.0.0.1:5173 prtr`.

## Status

**Live (2026-07-29):** the React build (`dist/`) is served as the page at
`https://vox.rtr.dev/` by the bot's FastAPI server; the vanilla client is
kept at `/vanilla/` as fallback. RTVI was already active by default in
pipecat-ai 1.6.0 (`PipelineWorker(enable_rtvi=True)`) — no `bot.py` change
was required. Verified end-to-end by user test: full LLM+TTS round trip
through the React UI.
