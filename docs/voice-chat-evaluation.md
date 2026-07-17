# Modular voice chat — LiveKit Agents evaluation

**Status:** Phase 1 automatic half-duplex human test passed across
trtr → drtr → prtr on 2026-07-13. Latency tuning is next.

## Goal

Natural hands-free voice chat without Fun-Audio-Chat:

```text
local microphone
→ local Silero VAD / automatic endpointing
→ Parakeet STT on drtr
→ persistent Pi/Qwen session on prtr
→ Chatterbox Turbo on drtr
→ local speaker
```

## Components

| Component | Endpoint / implementation | Verified |
|---|---|---|
| VAD | `livekit-plugins-silero==1.6.5`, local CPU | Model assets downloaded |
| STT | `POST http://drtr:7733/v1/audio/transcriptions` | Exact test transcript |
| Agent | Persistent noninteractive Pi session via prtr A2A facade | Correct response; low-thinking profile active |
| TTS | `POST http://drtr:7744/v1/audio/speech` | Valid 24 kHz mono audio |
| Conversation runtime | `livekit-agents==1.6.5` console mode | Audio graph initialized |

Source:
`experiments/livekit-voice-agent/`

## Phase 1 behavior

- Always-listening local microphone
- Silero speech-start detection
- Automatic endpoint after approximately 700ms silence
- Batch Parakeet transcription after endpoint
- One serialized Pi request through a persistent session
- Pi response constrained to two short plain-text sentences
- Batch Chatterbox synthesis and automatic playback
- Automatic return to listening
- Interruptions disabled while agent speech plays

No keypress is required for normal turns. Quit/pause controls remain
available in LiveKit console mode.

## Verification completed

Independent adapter smoke test:

```text
stt: I have a hard time falling asleep. Is there any type of music that can help me fall asleep faster?
pi: 17 multiplied by 4 is 68.
tts: sample_rate=24000, channels=1, duration=2.88s
```

Console mode successfully initialized:

- LiveKit worker
- Silero plugin
- Local microphone and speaker transport
- Transcript synchronization

The tool-driven smoke launch lacked a real TTY, so LiveKit's keyboard
shortcut thread reported `Inappropriate ioctl for device`. This is
expected under the automation shell and should not occur in a real
terminal.

System dependency installed with user approval:

```text
prtr smoke host: libportaudio2
trtr runtime host: Homebrew portaudio
```

## Human test

Run in terminal 2:

```bash
cd /home/prtr/prj/intraface/experiments/livekit-voice-agent
uv run agent.py console
```

Speak a short query, then remain silent. Confirm:

1. Speech is detected without a keypress.
2. Endpoint occurs naturally after the pause.
3. Transcript is correct.
4. Pi responds once.
5. Chatterbox audio plays automatically.
6. Listening resumes after playback.

### Human test result (2026-07-13)

Passed from trtr using:

- Input device 0: MacBook Air Microphone
- Output device 1: MacBook Air Speakers
- SSH local-forward to the prtr A2A Pi facade

Observed turns:

1. `"Hello."` → `"Hello. How can I help you today?"`
2. `"Um, just uh wanna test out uh in the voice chat."` →
   `"Voice chat is working perfectly. Let me know if you need help with anything else."`

Verified:

- Silero detected speech without keypresses.
- Endpoints were committed automatically.
- Parakeet retained natural fillers (`"Um"`, `"uh"`).
- A2A reached the persistent Pi session on prtr.
- Chatterbox played responses on trtr.
- Listening resumed for the second turn.
- No duplicate or echo-triggered self-turn occurred.
- Ctrl+C produced a clean user-initiated shutdown.

Measured from end of detected speech to assistant item:

- Turn 1: approximately 7.6s
- Turn 2: approximately 13.9s

The variance is likely dominated by Pi's default high thinking level and
new-process-per-turn A2A facade. Routine voice turns should use a lower
thinking level; card resolution/client creation can also be cached later.

### Latency change applied

The prtr A2A facade now invokes Pi with explicit `--thinking low` instead
of inheriting the global high setting. A direct post-change A2A request
completed in approximately 1.9s. Human end-to-end voice latency has not
yet been remeasured after this change.

## Pass criteria

- No manual turn submission
- Correct transcript
- Correct Pi response
- Intelligible spoken response
- Automatic next-turn readiness
- No duplicate turns or echo-triggered self-conversation
- End-of-speech to first audio under 10 seconds

Functional criteria passed. Latency is a conditional pass: turn 1 met the
target and turn 2 exceeded it before the low-thinking change.

## Phase 2

Only after Phase 1 stability:

- Enable interruptions
- Keep microphone active during playback
- Add WebRTC or PipeWire acoustic echo cancellation
- Stop playback immediately on barge-in
- Cancel or ignore stale Pi/TTS work by turn ID
- Evaluate streaming STT and TTS independently

Self-hosting the LiveKit media server is deferred. Console mode does not
require it.
