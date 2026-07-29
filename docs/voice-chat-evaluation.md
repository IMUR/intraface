# Voice chat evaluation

**Status:** Live. Browser-based conversational voice chat with the resident
Core is deployed at `https://vox.rtr.dev/`. Full-duplex with barge-in, streaming
TTS, and live transcript. End-of-speech to first audio typically 2-3 s.

This document supersedes the prior LiveKit + Pi + A2A evaluation. The
historical Phase 1 results are preserved at the end for provenance; the
LiveKit path is no longer deployed and the A2A facade is no longer running.

## Current architecture (pipecat, live 2026-07-29)

```text
Browser (any tailnet device)
  │ HTTPS  vox.rtr.dev
  ▼
crtr:443  Caddy  reverse_proxy → 100.64.0.2:7878
  │
  ▼
prtr:7878  FastAPI signaling + pipecat bot per WebRTC session
  │   (experiments/pipecat-web-voice/, bot PID in ~/.intraface/state/)
  │
  ├──► 127.0.0.1:7712   llama-server (prtr, loopback per DECISIONS 0006)
  │                       Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive Q6_K_P
  │                       262 144 context, --jinja --reasoning-format deepseek
  │                       Reasoning disabled per request via
  │                       chat_template_kwargs.enable_thinking=false
  │
  ├──► 100.64.0.3:7733  Parakeet STT (drtr, nvidia/parakeet-tdt-0.6b-v2, fp16)
  │
  └──► 100.64.0.3:7744  Chatterbox TTS (drtr, chatterbox==0.1.7, streaming)
```

The bot runs on prtr alongside llama-server. Parakeet and Chatterbox run on
drtr over the tailnet. prtr→drtr round-trip is ~3 ms; full STT call ~110 ms;
full TTS call ~1.5 s.

## Components

| Component | Endpoint / implementation | Verified |
|---|---|---|
| Browser transport | pipecat `SmallWebRTCTransport` over HTTPS via crtr Caddy | Live, signaling works |
| VAD | pipecat `SileroVADAnalyzer` (CPU, defaults: confidence 0.7, start/stop 0.2 s) | Live |
| Turn analyzer | pipecat `LocalSmartTurnV3` (`smart-turn-v3.2-cpu.onnx`) | Live; produces clean `EndOfTurnState.COMPLETE` on multi-word turns |
| STT | pipecat `OpenAISTTService(base_url=http://100.64.0.3:7733/v1)` → Parakeet | Live; TTFB ~280 ms |
| LLM | pipecat `OpenAILLMService(base_url=http://127.0.0.1:7712/v1)` → llama-server | Live; TTFB ~250-350 ms with thinking off |
| TTS | pipecat `OpenAITTSService(base_url=http://100.64.0.3:7744/v1)` → Chatterbox streaming | Live; TTFB ~1.3-2.1 s on long responses |
| Transcript forwarder | Custom `FrameProcessor` (2 instances — user + assistant) → WebRTC data channel | Live |
| Browser UI | `experiments/pipecat-web-voice/static/index.html` — vanilla JS, dark theme | Live; connect button + transcript panel |

Source: `experiments/pipecat-web-voice/` (bot.py, server.py, static/index.html)

## Two non-obvious requirements discovered during bring-up

These are not pipecat defaults and not in any example. Documenting here so
they aren't rediscovered.

1. **`chat_template_kwargs.enable_thinking: false` must be nested under `extra_body`**, not passed as a top-level kwarg. The Qwen3.6 Uncensored Aggressive Q6_K_P GGUF has thinking on by default in its Jinja template; without this flag, the model emits only `reasoning_content` and stops before producing any user-facing `content`. Pipecat's `OpenAILLMService.Settings(extra=...)` flattens the dict into top-level kwargs, which the OpenAI Python SDK rejects. The working shape:

   ```python
   settings=OpenAILLMService.Settings(
       extra={"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}},
       ...
   )
   ```

   Verified against the live llama-server: with the flag, `"What is 17 times 4?"` returns `"17 times 4 equals 68."` in ~750 ms.

2. **The browser must create the data channel before sending the WebRTC offer.** Pipecat's `SmallWebRTCTransport` listens via `@pc.on("datachannel")` server-side. Without a `pc.createDataChannel("pipecat")` call before `setLocalDescription(createOffer())`, the data channel never opens, transcripts are silently dropped, and the server times out after 10 s. The official pipecat example HTML omits this because it doesn't ship a transcript UI.

## Behavior (Phase 1, deployed)

- Always-listening browser microphone via `getUserMedia({audio: true})`
- Silero VAD speech-start detection (`start_secs=0.2`)
- Smart Turn v3.2 ML model decides turn-end (overrides simple silence heuristic)
- Batch Parakeet transcription after Smart Turn reports `COMPLETE`
- Streaming LLM (token chunks emitted as they arrive)
- Streaming TTS (Chatterbox text-chunked into ~25-word segments, PCM chunks flushed per segment)
- Full-duplex: barge-in enabled by default (~10 ms cutoff latency)
- Live transcript panel in browser via WebRTC data channel
- No persistence across disconnects — each WebRTC session starts with fresh `LLMContext`

## Latency budget (measured 2026-07-29)

| Stage | Time | Notes |
|---|---|---|
| Silero VAD → Smart Turn `COMPLETE` | ~1.5-2 s | depends on utterance length and silence pattern |
| Parakeet STT (after endpoint) | ~80-300 ms | batch transcribe of one utterance |
| llama-server LLM (thinking off) | ~250-350 ms TTFB | streams tokens |
| Chatterbox TTS first audio | ~1.3-2.1 s | streaming endpoint, text-chunked |
| **End-of-speech to first audio (typical)** | **~2-3 s** | |

For comparison, the prior LiveKit + Pi + A2A path measured 7.6 s and 13.9 s
end-of-speech to assistant item (see Historical Phase 1 below).

## Barge-in (full-duplex interruption)

Verified working 2026-07-29 via deliberate user testing:

- User can speak while bot is mid-speech
- VAD detects speech-start within ~200 ms
- `broadcast_interruption` fires immediately
- TTS playback cuts off within ~10 ms
- New turn's STT/LLM/TTS proceeds normally
- Bot confirmed awareness of the interrupt: *"Yes, I did."* when asked *"Did the interrupt stop your story?"*

No self-triggering from bot's own audio output (browser AEC handles it).

## TTS streaming fix (deployed 2026-07-29)

The Chatterbox wrapper at `/opt/services/chatterbox-tts/app.py` (in-house,
~150 LOC Flask) was extended to stream PCM chunks instead of returning the
full WAV in one response body. Pipecat's `OpenAITTSService` already used
`.with_streaming_response.create()` and iterated bytes as they arrived;
only the wrapper needed to change.

**Effect:** Long responses (175-word story) went from 22.7 s TTFB to 1.3-2.1 s
TTFB. Total TTS time is unchanged (same model work); only first-audio latency
improved. The chunker splits text on sentence boundaries first, falls back
to comma/semicolon, then hard word-count (25 words max per chunk).

Original wrapper backed up at `app.py.bak.20260729-111501` on drtr.

## Known issues

1. **Per-chunk leading silence.** Chatterbox emits ~30-50 ms of silence at
   the start of each `model.generate()` call. When streaming chunks back-to-
   back, this produces small audible gaps between sentences. Not yet fixed;
   not reported as noticeable in informal testing.

2. **Smart Turn patience on short utterances.** On "Hello" (single word),
   the model returns `INCOMPLETE` and waits the full 3 s silence window
   before firing inference. Annoying for rapid back-and-forth; acceptable
   for normal speech. Tunable via `LLMUserAggregatorParams.user_turn_stop_timeout`.

3. **Bot process durability.** Currently `nohup` background process on prtr.
   Dies on reboot or shell exit. Promotion to systemd user service is a
   follow-up.

4. **No persistence across disconnects.** Each WebRTC session starts with
   fresh `LLMContext` (system prompt only). Closing the tab loses the
   conversation. XTDB on prtr:5511 is available if persistent history
   becomes a requirement.

5. **llama-server JSON schema defect** (cross-cutting). Documented in
   `engines.toml [defects.json_schema]`. Blocks auto-derived tool schemas
   that include `true`/`false` JSON Schema 2020-12 values. Fix in progress
   in a separate workstream. Does not affect the current conversational
   voice path (no tools registered).

## Cross-node deployment (per ADR 0007)

Canonical source on prtr. The bot runs directly from the prtr checkout
(permitted under ADR 0002 for prtr-local code). The Chatterbox and Parakeet
services on drtr are node-specific runtime deployments under
`/opt/services/{chatterbox-tts,parakeet-stt}/`, each with its own `.venv`
and systemd unit. The crtr Caddyfile has one `vox.rtr.dev` block reverse-
proxying to prtr:7878.

No cross-node `rsync` is currently required for vox because the bot runs on
prtr from source. If the bot is ever moved to another node, the ADR 0007
rsync pattern applies (see `experiments/livekit-voice-agent/README.md` for
the original shape).

## Pass criteria (current)

- [x] Browser-accessible (any tailnet device, HTTPS via vox.rtr.dev)
- [x] No manual turn submission (VAD + Smart Turn)
- [x] Correct transcript (Parakeet)
- [x] Correct Core response (llama-server, thinking off)
- [x] Intelligible spoken response (Chatterbox streaming)
- [x] Automatic next-turn readiness
- [x] No duplicate turns or echo-triggered self-conversation
- [x] End-of-speech to first audio under 3 s (typically ~2-3 s)
- [x] Barge-in works (full-duplex, ~10 ms cutoff)
- [x] Live transcript in browser

All criteria pass.

## Open follow-ups (priority order)

1. **Agent capabilities** — tools, identity (`AGENTS.md`), self-awareness.
   **Layer 1 (read-only cluster ops) shipped 2026-07-29.** Layers 2–5
   (filesystem, web search, Pi delegation, modes) are designed but not yet
   implemented — see `experiments/pipecat-web-voice/AGENTS.md` for the design.
   See `docs/handoffs/2026-07-29-vox-agent-capabilities.md` for original scope.
2. **Frontend improvements** — Markdown, persistence, voice selection.
   See `docs/handoffs/2026-07-29-vox-frontend-ui.md`.
3. **Systemd unit for the bot process** — survive reboots.
4. **Per-chunk silence trimming** in the Chatterbox wrapper.
5. **Streaming STT** — Parakeet is batch today; a streaming-capable endpoint
   would shave the VAD-to-LLM gap.
6. **Latency tuning** — if 2-3 s TTFB becomes a bar, evaluate Option β
   (true token-streaming via `chatterstream-tts` or `chatterbox-streaming`
   libraries). Blocked by Python 3.13 incompatibility with `chatterstream-tts`
   (requires 3.10/3.11); `chatterbox-streaming` is compatible but
   introduces a maintained-fork dependency.

---

# Reference: shared context for handoff recipients

This section exists so that the handoff documents
(`docs/handoffs/2026-07-29-vox-*.md`) can be paired with this single
evaluation file as their only companion. Everything a fresh agent needs
beyond what's in their handoff should be here. If it's not here, treat the
absence as a finding and surface it.

## bot.py — current shape (verified 2026-07-29)

```text
experiments/pipecat-web-voice/bot.py — 205 LOC

  imports
  env vars:
    PARAKEET_URL     default http://100.64.0.3:7733/v1
    CHATTERBOX_URL   default http://100.64.0.3:7744/v1
    LLAMA_URL        default http://127.0.0.1:7712/v1
    LLAMA_MODEL      default qwen3.6-uncensored-q6-k-p

  SYSTEM_INSTRUCTION:
    "You are a conversational voice assistant. Your output is converted to
     speech, so use plain spoken language with no Markdown, no lists, no
     headings, and no citations. Keep responses short — typically one or
     two sentences. Answer directly."

  class TranscriptForwarder(FrameProcessor):
    role="user":     sits between STT and user_aggregator
                     emits on TranscriptionFrame
    role="assistant": sits between LLM and TTS
                      accumulates TextFrames between LLMFullResponseStart/End
    _send(): calls webrtc_connection.send_app_message({"role", "text"})
             (NOT transport.send_message — that was a bug we hit)

  async def run_bot(webrtc_connection):
    transport = SmallWebRTCTransport(audio_in=True, audio_out=True, audio_out_10ms_chunks=2)
    stt = OpenAISTTService(base_url=PARAKEET_URL, model="parakeet-tdt-0.6b-v2")
    llm = OpenAILLMService(base_url=LLAMA_URL, model=LLAMA_MODEL,
                           settings=Settings(extra={"extra_body": {
                               "chat_template_kwargs": {"enable_thinking": False}
                           }}, max_completion_tokens=120, temperature=0.3))
    tts = OpenAITTSService(base_url=CHATTERBOX_URL, model="chatterbox-turbo", voice="alloy")
    context = LLMContext() + system message
    user_agg, assistant_agg = LLMContextAggregatorPair(context, realtime=False,
                                                        user_params=(vad=SileroVADAnalyzer()))

    pipeline order:
      transport.input → stt → user_transcript → user_aggregator →
      llm → assistant_transcript → tts → transport.output → assistant_aggregator

    worker = PipelineWorker(pipeline, PipelineParams(enable_metrics=True))
    on_client_disconnected handler cancels worker
    runner = WorkerRunner(handle_sigint=False)
```

No tools registered today. `LLMContext` is constructed with default tools
(empty). When adding tools, pass them in the `LLMContext(tools=[...])`
constructor (see pipecat function calling docs).

> **Update 2026-07-29:** Layer 1 tools are now registered. `bot.py` constructs
> `LLMContext(tools=list(vox_tools.ALL_TOOLS))` and includes a
> `on_function_calls_started` filler hook. See `tools.py` for the four
> registered functions (`check_node`, `list_services`, `get_log_tail`,
> `get_port_state`) and `AGENTS.md` for vox's identity. The shape summary
> above reflects the pre-Layer-1 state for historical reference.

## server.py — current shape

```text
experiments/pipecat-web-voice/server.py — 77 LOC

FastAPI app on port 7878, host 0.0.0.0.
Mounts /static/* via StaticFiles.
Routes:
  POST /api/offer     SmallWebRTCRequest → SmallWebRTCRequestHandler
                      spawns run_bot(connection) as background task
  PATCH /api/offer    SmallWebRTCPatchRequest → trickle ICE
  GET  /              serves static/index.html
```

## static/index.html — current shape

```text
experiments/pipecat-web-voice/static/index.html — 281 LOC

Single self-contained file. No build step, no framework.
Dark theme via CSS custom properties. Two sections:
  #controls      status dot + status text + connect/disconnect button
  #transcript    scrollable div; turns appended as styled divs by JS
  <audio>        hidden, autoplay, fed by pc.ontrack

JS functions:
  connect()              getUserMedia → createPeerConnection
  createPeerConnection() new RTCPeerConnection, iceServers=[STUN only]
                         creates data channel "pipecat" BEFORE createOffer
                         addTransceiver audio (sendrecv) + video (sendrecv)
                         POSTs /api/offer, handles answer, queues ICE
  disconnect()           closes pc, resets UI
  addTurn(role, text)    appends turn div to #transcript
  sendIceCandidate()     PATCH /api/offer with {pc_id, candidates:[...]}

Data channel message shape (server→client):
  {"role": "user" | "assistant", "text": "<transcript text>"}
```

## Cluster topology (relevant facts)

The voice bot's tools and identity work reference these. **Authoritative
source: `rtr-profile.md`** — what's here is a minimal summary current as of
2026-07-29. If rtr-profile.md disagrees with reality, reality wins; surface
the drift.

### Nodes (4 total, all on tailnet 100.64.0.0/24)

| Node | Tailnet IP | LAN IP | Arch | OS | Role |
|---|---|---|---|---|---|
| prtr (projector) | 100.64.0.2 | 192.168.254.22 | x86_64 | Debian 13 | Compute, AI inference, bot host |
| drtr (director) | 100.64.0.3 | 192.168.254.33 | x86_64 | Debian 13 | GPU inference, voice STT/TTS |
| crtr (cooperator) | 100.64.0.4 | 192.168.254.11 | arm64 | Debian 13 | Edge ingress, Caddy, cluster ops |
| trtr (terminator) | 100.64.0.1 | 192.168.254.107 | arm64 | macOS 26.5 | Workstation, cluster entry-point |

### Cluster port block model

| Block | Range | Category |
|---|---|---|
| Daemon | `44`** | Engine services, gateways |
| WebUI | `55`** | Browser-facing UIs |
| Data | `66`** | Stores, caches |
| AI | `77`** | LLM, STT, TTS, embeddings |

### Voice-relevant ports (verified live 2026-07-29)

| Port | Bind | Service | Node |
|---|---|---|---|
| 7878 | 0.0.0.0 | pipecat bot (FastAPI + WebRTC signaling) | prtr |
| 7712 | 127.0.0.1 | llama-server (Qwen3.6 Q6_K_P) | prtr |
| 7733 | 0.0.0.0 | Parakeet STT | drtr |
| 7744 | 0.0.0.0 | Chatterbox TTS (streaming) | drtr |
| 5511 | 127.0.0.1 | XTDB v2.1.0 (pgwire, available for future history) | prtr |
| 443 | 192.168.254.10 | Caddy (vox.rtr.dev reverse proxy) | crtr |

### SSH aliases from prtr (passwordless, ControlMaster auto)

| Alias | Resolves to | User |
|---|---|---|
| `c` / `crtr` | 100.64.0.4 / 192.168.254.11 | crtr |
| `p` / `prtr` | 100.64.0.2 / 192.168.254.22 | prtr |
| `d` / `drtr` | 100.64.0.3 / 192.168.254.33 | drtr |
| `t` / `trtr` | 100.64.0.1 / 192.168.254.107 | trtr |

## SSH execution discipline

Cluster convention (from `rtr-profile.md`):

- **Bash is the default login shell on Linux nodes.** `ssh <node> '<cmd>'`
  works directly — no need for `bash -l -c` or `zsh -l -c`.
- **Don't use `zsh -l -c` for non-interactive ops** — unreliable on Linux
  nodes (zsh is for interactive use only).
- **ControlMaster auto multiplexes** — repeated SSH calls reuse one
  connection (~10 ms after first).
- **Stale ControlMaster sockets** can occur after node reboot. If SSH fails
  with "Connection closed", run `ssh -O exit <node>` then retry.
- **trtr is macOS** — may sleep. SSH can hang or fail. Tools targeting trtr
  should use a short timeout (3-5 s) and return clean "unreachable" rather
  than raise.
- **Spawn pattern:** `asyncio.create_subprocess_exec("ssh", "<alias>",
  "<cmd>")` — never `shell=True`, never `sh -c`.

## llama-server JSON schema defect (cross-cutting)

> **STATUS (2026-07-29): RESOLVED.** Verified live — see `engines.toml
> [defects.ik_llama_json_schema]` for the verification record. The text
> below is the historical description of the defect, retained for
> provenance. Layer 1 tools are deployed and working.

**Symptom (when registering tools via OpenAI function calling):**

```
Error: 500: {"code":500,"message":"Unable to generate parser for this
template. Automatic parser generation failed: JSON schema conversion
failed:\nUnrecognized schema: true","type":"server_error"}
```

**Root cause:** ik_llama.cpp's `common/json-schema-to-grammar.cpp` (at the
pinned commit `86d8e9a1`, 2026-07-06) doesn't handle JSON Schema 2020-12
boolean values (`true` means "accept any value," `false` means "reject all").
The OpenAI SDK's auto-derived tool schemas include `additionalProperties:
true` on object types, which triggers the defect.

**Authoritative documentation:** `engines.toml [defects.ik_llama_json_schema]`
(in the project root). Also documented in HANDOFF.md item #1.

**Fix status (2026-07-29):** RESOLVED. Probed the live server with three
schema shapes including `additionalProperties: true` — all returned HTTP
200. Full tool-call roundtrip verified end-to-end. Mechanism unclear:
binary mtime matches the pinned commit, so the defect self-resolved
without an obvious code change. Pipecat's `FunctionSchema.to_default_dict()`
also does not emit the trigger, so the standard tool path is safe
regardless.

**Does not affect** the current voice path — Layer 1 tools are deployed
and verified working.

## Engines and versions

| Engine | Version | Pinned commit | Role |
|---|---|---|---|
| `pipecat-ai` | 1.6.0 | n/a (PyPI) | Voice pipeline framework |
| `chatterbox` | 0.1.7 | n/a (PyPI) | TTS model (Chatterbox-Turbo) |
| `nemo` | 2.7.2 | n/a (PyPI) | Parakeet STT model host |
| `ik_llama.cpp` | 4681 | `86d8e9a13c4d6e6fead9c9489ade4b0d283afc53` | llama-server (Core) |
| `llama.cpp` | 9861 | `a2d90e887ac0f79accaa095f30a71a907f7f3536` | llama-cli (Units, not used by vox today) |

Source: `engines.toml` in project root. **If a future agent rebuilds the
engine, they must update `engines.toml` with the new commit.**

## Where things live

```text
~/prj/intraface/
├── experiments/
│   ├── pipecat-web-voice/    ← current voice bot (live)
│   │   ├── bot.py
│   │   ├── server.py
│   │   ├── static/index.html
│   │   ├── tests/test_pipeline_construction.py
│   │   ├── pyproject.toml
│   │   ├── uv.lock
│   │   └── README.md
│   ├── livekit-voice-agent/  ← superseded (reference only)
│   └── a2a-voice-bridge/     ← superseded (reference only, A2A facade not running)
├── docs/
│   ├── voice-chat-evaluation.md       ← this file
│   ├── handoffs/
│   │   ├── 2026-07-29-vox-frontend-ui.md
│   │   └── 2026-07-29-vox-agent-capabilities.md
│   ├── charter.md          ← conceptual model (5 tests, Executor/Core/Unit taxonomy)
│   ├── features.md         ← Unit backlog (pre-charter vocab; "specialist" = "Unit")
│   ├── core-model-baselines/
│   └── decisions/          ← ADRs 0001-0007
├── HANDOFF.md              ← project-wide handoff (may be stale; verify against live state)
├── rtr-profile.md          ← authoritative cluster reference
└── engines.toml            ← pinned engine commits + defects

/opt/services/  (on drtr)
├── parakeet-stt/
│   ├── app.py
│   └── .venv/              ← Python 3.13.5, nemo 2.7.2
└── chatterbox-tts/
    ├── app.py              ← v2 with streaming (original at app.py.bak.20260729-111501)
    └── .venv/              ← Python 3.13.5, chatterbox 0.1.7

~/.intraface/
├── models/
│   ├── core/
│   │   └── qwen3.6-35b-a3b-uncensored-aggressive/
│   │       └── Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q6_K_P.gguf
│   └── unit/               ← LFM2.5 weights (extract Unit, separate from vox)
└── state/
    ├── pipecat-web-voice.log
    ├── core-q6-k-p.log
    └── vox-monitor/        ← disabled systemd user service for log watching
```

## Architectural decisions in force (ADRs)

| ADR | Status | What it means for vox |
|---|---|---|
| 0001 | Accepted | Model custody at `~/.intraface/models/{core,unit}/` — vox uses core/, doesn't touch unit/ |
| 0002 | Superseded by 0007 | Originally "dev tree is runtime target" — still permits prtr-local code (like vox) running from the checkout |
| 0003 | Accepted | Units invoke llama.cpp as isolated subprocesses — not directly relevant to vox |
| 0006 | Accepted | Rejected Fun-Audio-Chat as Core candidate; chose modular LiveKit/Parakeet/Pi/Chatterbox direction — now evolved to pipecat |
| 0007 | Accepted | Canonical source on prtr; cross-node deployment explicit per node — vox runs from prtr source, no rsync needed today |

Don't violate these without writing a superseding ADR. Read the actual ADR
files in `docs/decisions/` if a decision seems to conflict with reality.

---

# Historical Phase 1 (LiveKit + Pi + A2A — superseded)

**Status:** Superseded 2026-07-29. Path is no longer deployed. Retained
for provenance and to document why it was replaced.

## Original goal

Natural hands-free voice chat without Fun-Audio-Chat:

```text
local microphone
→ local Silero VAD / automatic endpointing
→ Parakeet STT on drtr
→ persistent Pi/Qwen session on prtr
→ Chatterbox Turbo on drtr
→ local speaker
```

## What was deployed

| Component | Endpoint / implementation | Verified |
|---|---|---|
| VAD | `livekit-plugins-silero==1.6.5`, local CPU | Model assets downloaded |
| STT | `POST http://drtr:7733/v1/audio/transcriptions` | Exact test transcript |
| Agent | Persistent noninteractive Pi session via prtr A2A facade | Correct response; low-thinking profile active |
| TTS | `POST http://drtr:7744/v1/audio/speech` | Valid 24 kHz mono audio |
| Conversation runtime | `livekit-agents==1.6.5` console mode | Audio graph initialized |

Source: `experiments/livekit-voice-agent/` (retained as reference; not running)
A2A facade source: `experiments/a2a-voice-bridge/` (retained; facade not running)

## Human test result (2026-07-13)

Passed from trtr using:

- Input device 0: MacBook Air Microphone
- Output device 1: MacBook Air Speakers
- SSH local-forward to the prtr A2A Pi facade

Observed turns:

1. `"Hello."` → `"Hello. How can I help you today?"`
2. `"Um, just uh wanna test out uh in the voice chat."` →
   `"Voice chat is working perfectly. Let me know if you need help with anything else."`

Measured from end of detected speech to assistant item:

- Turn 1: approximately 7.6 s
- Turn 2: approximately 13.9 s

The variance was dominated by Pi's per-turn subprocess spawn and the A2A
round-trip. Routine turns used `--thinking low` after this test.

## Why it was superseded

Three reasons, in order of weight:

1. **The A2A facade at `127.0.0.1:9999` was no longer running** (verified
   2026-07-29). The current voice path was already broken at the A2A layer.
2. **LiveKit console mode required the client to run on trtr** (mic and
   speakers physically attached). The new pipecat path lets any browser
   on the tailnet be the client.
3. **The 4-hop voice path (browser → LiveKit → Pi subprocess → Core)
   added latency that the pipecat 2-hop path (browser → bot → Core)
   eliminates.** End-of-speech to first audio dropped from 7.6-13.9 s
   to typically 2-3 s.

The LiveKit code is retained under `experiments/livekit-voice-agent/` as
reference. The A2A facade code is retained under `experiments/a2a-voice-bridge/`.
Neither is deployed.

## Original Phase 2 plan (now obsolete)

The prior Phase 2 plan was:

- Enable interruptions
- Keep microphone active during playback
- Add WebRTC or PipeWire acoustic echo cancellation
- Stop playback immediately on barge-in
- Cancel or ignore stale Pi/TTS work by turn ID
- Evaluate streaming STT and TTS independently

All of these are solved by the pipecat deployment: barge-in is on by default,
AEC is handled by the browser, stale work cancellation is pipecat's
`InterruptionFrame` mechanism, and streaming TTS shipped 2026-07-29.
