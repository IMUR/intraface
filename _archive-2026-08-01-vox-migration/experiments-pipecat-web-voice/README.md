# pipecat-web-voice

Browser-based conversational voice chat with the resident Intraface Core,
built on pipecat's `SmallWebRTCTransport`.

```text
browser (mic + speaker + transcript UI)
  │ WebRTC (audio + data channel)
  ▼
drtr:7878  FastAPI signaling + pipecat bot process
  │
  ├──► drtr:7733   Parakeet STT      (existing, reused)
  ├──► prtr:7712   llama-server LLM  (existing, reused; thinking off)
  └──► drtr:7744   Chatterbox TTS    (existing, reused)
```

No custom adapter code: every service is the stock pipecat OpenAI-compatible
adapter pointed at an existing endpoint via `base_url`. Replaces the prior
LiveKit + Pi + A2A facade path (which was already broken: the A2A facade
at `127.0.0.1:9999` was not running as of 2026-07-29).

## Falsification checks (2026-07-29)

All four endpoint-shape assumptions were probed before code was written:

| Check | Probe | Result |
|---|---|---|
| Parakeet returns `{"text": "..."}` | POST known WAV | VERIFIED |
| llama-server streams content pipecat can use | POST `/v1/chat/completions` | NOT VERIFIED initially — resolved by `chat_template_kwargs.enable_thinking: false` |
| Chatterbox returns pipecat-compatible WAV | POST `/v1/audio/speech` | VERIFIED (24kHz mono 16-bit PCM) |
| drtr headroom for pipecat + Silero CPU VAD | `free`, `nvidia-smi` | VERIFIED (50Gi RAM free, load 0.10) |

The reasoning flag is the one non-obvious bit. The resident
Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive Q6_K_P model emits only
`reasoning_content` by default and stops naturally before producing any
user-facing `content`. The Jinja template accepts
`chat_template_kwargs.enable_thinking: false` to suppress this, verified
against the live server: `17 times 4 equals 68.` in 750ms with the flag.

## Layout

```text
experiments/pipecat-web-voice/
├── bot.py              pipecat Pipeline + TranscriptForwarder
├── server.py           FastAPI: /api/offer + static serve
├── static/
│   └── index.html      WebRTC client + live transcript panel
├── pyproject.toml      pipecat-ai[openai,silero,webrtc]
└── README.md           this file
```

## Deploy on drtr (per ADR 0007 pattern)

The bot lives on drtr so Parakeet and Chatterbox are reached at `localhost`
(minimum STT/TTS latency). Only the llama-server call crosses the tailnet.

```bash
# 1. Copy source from prtr to drtr (canonical → runtime)
mkdir -p ~/prj/intraface-client
rsync -az --exclude .venv --exclude __pycache__ \
  prtr:/home/prtr/prj/intraface/experiments/pipecat-web-voice/ \
  ~/prj/intraface-client/pipecat-web-voice/

cd ~/prj/intraface-client/pipecat-web-voice

# 2. Recreate env from lockfile (uv, not pip — see HANDOFF.md)
uv sync

# 3. Run
uv run python server.py --host 0.0.0.0 --port 7878
```

### Pre-flight checks (run once before starting the server)

```bash
# All three backend services must be live
curl -s http://localhost:7733/health    # Parakeet on drtr
curl -s http://localhost:7744/health    # Chatterbox on drtr
ssh prtr 'curl -s http://127.0.0.1:7712/v1/models'   # llama-server on prtr
```

## TLS via crtr Caddy (required for browser mic access)

Browsers refuse `getUserMedia` on `http://` origins except `localhost`.
The cluster's existing Caddy on crtr serves `*.rtr.dev` with valid DNS-01
wildcard certs (see `rtr-profile.md`). One block:

```caddyfile
vox.rtr.dev {
    reverse_proxy drtr.tailnet:7878
}
```

After reload, open `https://vox.rtr.dev/` from any browser on the tailnet.

For off-tailnet access (laptop on hotel wifi), add a TURN server to the
`RTCPeerConnection` config in `static/index.html`. STUN alone is sufficient
for same-tailnet peers.

## Environment overrides

The defaults assume the bot runs on drtr with the resident model. Override
via environment or `.env`:

| Var | Default | Purpose |
|---|---|---|
| `PARAKEET_URL` | `http://localhost:7733/v1` | Parakeet STT base |
| `CHATTERBOX_URL` | `http://localhost:7744/v1` | Chatterbox TTS base |
| `LLAMA_URL` | `http://100.64.0.2:7712/v1` | llama-server base (prtr tailnet IP) |
| `LLAMA_MODEL` | `qwen3.6-uncensored-q6-k-p` | model name |

## What this replaces

| Prior | Now |
|---|---|
| `experiments/livekit-voice-agent/` (3 custom adapters, ~320 LOC) | `experiments/pipecat-web-voice/bot.py` (~190 LOC, 0 custom adapters) |
| `experiments/a2a-voice-bridge/` (A2A facade, Pi subprocess) | deleted — pipecat talks to llama-server directly |
| LiveKit console transport (trtr-only, PortAudio) | SmallWebRTCTransport (any browser) |
| Half-duplex (interruption disabled for Phase 1) | Full-duplex by default (Silero VAD in user aggregator) |
| Pi `--thinking low` wrapper | `chat_template_kwargs.enable_thinking: false` in LLM settings |

## Known risks not yet verified at runtime

- **End-to-end turn latency.** Probe-based estimate is ~7s. Not measured
  through the full pipeline yet.
- **Concurrent sessions.** One bot process per WebRTC connection. For
  multi-user, a process supervisor is needed.
- **Parakeet/Chatterbox `/v1/models` 404.** Both services don't implement
  the OpenAI models list endpoint. Pipecat doesn't require it for STT/TTS.
  Non-issue.

## Phase 2 (deferred)

- Streaming STT (if a Parakeet streaming endpoint lands)
- Streaming TTS (split Chatterbox WAV into chunks for first-audio-faster)
- Voice selection UI
- Persistent transcript history (XTDB on prtr:5511 is available)
