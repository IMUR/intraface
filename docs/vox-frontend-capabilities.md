# vox frontend capability inventory

**Date:** 2026-07-30
**Purpose:** Everything the vox frontend *can* accommodate, written as input
for UI/UX design. This describes capabilities, signals, and constraints —
not the current build. If a design stays within these bounds, it is
implementable without backend changes (exceptions are marked ⟳
coordination-required).

**Sources:** RTVI standard (pipecat docs), voice-ui-kit docs, installed
pipecat-ai 1.6.0 / client-js 1.13 / voice-ui-kit 0.13, and the live bot
configuration (see `PROGRESS.md` — the bot now has cluster tools).

---

## 1. Session model

- One browser session = one WebRTC connection = one private bot instance
  with its own conversation memory. No other users visible, ever.
- **No persistence.** Disconnect, refresh, or network drop = conversation
  gone (client-side localStorage is possible purely as a display cache).
- No authentication, no identity, no accounts. Anyone on the tailnet.
- Reconnection is not provided by the platform; a dropped session is a new
  session. The UI should treat "lost" as a first-class terminal state with
  a path to start fresh, not as an error to retry silently.

## 2. Session lifecycle states (design must cover all)

`disconnected → connecting → connected → (bot ready) → ready`

Plus terminal/degraded states: `error` (mic denied, signaling failure,
server unreachable), `disconnected` mid-session (network drop, bot
process death — the bot is a nohup process and *can* die).

The bot's readiness arrives as an explicit `bot-ready` event after media
connects — there is a real, measurable "almost there" moment to design for.

## 3. The conversational state machine (per turn)

The richest thing a design can express. Every state below arrives as a
discrete real-time event:

| State | Signal | Typical duration |
|---|---|---|
| Idle / listening | (default) | indefinite |
| User speaking | `vad-user-started-speaking` / `user-started-speaking` | as long as they talk |
| User finished, understanding | `user-stopped-speaking` → transcript arrives | 1.5–2 s (see §9) |
| Bot thinking | `bot-llm-started`, tokens streaming via `bot-llm-text` | ~0.3 s to first token |
| Bot speaking | `bot-tts-started`, `bot-started-speaking` / `bot-stopped-speaking` | length of reply |
| Interrupted (barge-in) | user speaks any time; playback cuts in ~10 ms; pipeline resets | — |

**Interruption is always available and instant.** The user never needs a
button to cut the bot off — they just talk. A design may surface this
("speaking — interrupt anytime") but must not gate it.

Notable nuance: VAD events (`vad-user-*`) are the raw signal;
`user-started/stopped-speaking` are turn-finalized. Both are available —
e.g. a subtle "hearing you" pulse on VAD vs. a committed "turn" state.

## 4. Conversation content (what can be rendered)

| Content | Detail |
|---|---|
| User turns | Final transcription per turn. Partial hypotheses exist in the protocol; our STT is batch, so partials arrive late/not at all today ⟳ streaming STT is a backend follow-up |
| Assistant turns | Streaming token-by-token (`bot-llm-text`) AND sentence-aggregated |
| **Spoken vs. unspoken text** | Every assistant chunk carries `spoken` / `unspoken` portions — enables **karaoke mode**: words highlight as the bot actually says them. Also captions mode (sentence-at-a-time) and instant mode. This is voice-native; a chat UI doesn't have it |
| **Function/tool calls** | The bot has live cluster tools (node health, logs, ports), file reads, and web search. Calls appear in the timeline with name, status (started/in-progress/completed), arguments, result — collapsible renderers exist; custom renderers per tool are supported |
| System/injected messages | Arbitrary messages can be injected client-side into the timeline |
| Timestamps | Per message/part |

Assistant text is plain spoken prose by system prompt (no Markdown, short).
That is a prompt choice, not a platform constraint ⟳ longer/markdown
responses are a backend prompt change away.

## 5. Input modalities

| Modality | Detail |
|---|---|
| **Voice (always-on)** | Open mic with server-side VAD + turn detection. No push-to-talk exists; endpointing is not the UI's job |
| **Text input** | Fully supported *today* via RTVI `send-text`. Options per message: `run_immediately` (default true — typing acts like a polite barge-in) and `audio_response` (default true — bot speaks the reply; set false for silent text replies). Design decision: typed input can interrupt, queue, or request text-only replies |
| Mic mute | Client-side mute while staying connected |
| Device selection | Microphone picker, speaker/output picker (where the browser allows) |
| Video / screen share | Transport supports both; the bot ignores them today. Available as layout space if ever needed, excluded by default |

Browser AEC handles echo; the bot's own audio never self-triggers. Nothing
to design around there.

## 6. Output modalities & live data for visualization

| Output | Detail |
|---|---|
| Bot voice | Audio stream, ~20 ms chunks |
| **Bot audio analysis** | Real-time frequency/amplitude data of bot audio (FFT bands, bass/mid/treble, volume) — drives visualizers |
| **Mic audio analysis** | Same for the user's voice |
| Visualizer states | The kit's WebGL plasma visualizer has three designed states — disconnected, connected, thinking — and full color/ring/reactivity customization. Basic bar and circular-waveform visualizers also exist for both participants |
| Speaking indicators | Bot started/stopped events (distinct from audio levels — works even if visualizer is hidden) |
| **Metrics stream** | Per-stage performance events (TTFB, processing ms per pipeline stage) — a latency/debug surface is possible with zero backend work |

## 7. Controls the UI can offer

- Connect / disconnect
- Mic mute toggle, mic device select, speaker select, output volume
- Text composer (with the behavioral options in §5)
- Theme switching (light/dark/custom — theming is token-based CSS
  variables; light/dark ship by default, a "terminal" theme pack exists,
  custom themes are variable overrides)
- Conversation display modes (karaoke / captions / instant)
- Function-call expand/collapse, custom per-tool renderers
- Client-side transcript cache/clear (localStorage)

## 8. Extensibility hooks (for future features)

- `client-message` / `server-message` custom channel — arbitrary JSON both
  directions ⟳ server handler is a small bot.py addition
- `onServerMessage` / `onClient` client-side subscriptions
- Function-call reporting level is server-configurable (name only vs. full
  args/results) ⟳
- Per-aggregation custom text renderers (e.g. render `code` differently)
- Voice selection, TTS speed, VAD sensitivity ⟳ backend plumbing, tracked
  in `docs/vox-frontend-surface.md` §7

## 9. Timing & behavioral constraints (design must forgive these)

| Behavior | Value | Design implication |
|---|---|---|
| End-of-speech → first audio | typically **2–3 s** | Needs an explicit "understood, working" state; silence without feedback reads as failure |
| Short utterances ("Hello") | up to ~3 s extra (turn model patience) | Same state covers it |
| Interruption | ~10 ms cutoff, ~200 ms detection | Feels instant; visual state should flip just as fast |
| TTS chunk gaps | ~30–50 ms silence between sentences | Audio artifact, not a bug; don't design "done" off audio gaps |
| First connect | mic permission prompt + signaling + bot spawn + `bot-ready` | A staged connect sequence (3–4 distinct beats) |
| Bot process durability | nohup process, dies on reboot | Mid-session death is possible; handle as "session ended" with reconnect path |
| Off-tailnet access | STUN only, no TURN | May fail from strict NATs; out of scope for v1 design |

## 10. Hard boundaries (do not design against these)

- No history across sessions, no conversation list, no sharing/export
  server-side (client-side export is possible)
- No user accounts, presence, or multi-user anything
- No server-driven UI commands, no proactive bot-initiated contact
- No control of bot voice/personality from the UI today ⟳
- HTTPS-only in production (mic); `localhost` for dev

---

### One-paragraph summary for the designer

vox is a single-user, voice-first, session-scoped conversation with a bot
that can see a cluster of machines. The UI can know *exactly* what the bot
is doing at every moment (listening / understanding / thinking / speaking /
interrupted / dead), can render the transcript in sync with the speech
(karaoke), can show the bot's tool use as it happens, can accept typed
input that behaves like speech, and has live audio data for both voices to
drive any visualization. Its two honest constraints are a 2–3 second
thinking gap that needs a designed state, and total impermanence — every
session is the whole world.
