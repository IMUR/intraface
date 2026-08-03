# LiveKit voice-agent experiment

Hands-free, automatic half-duplex voice chat using existing services:

```text
local microphone
→ local Silero VAD / automatic endpointing
→ Parakeet STT on drtr:7733
→ persistent Pi/Qwen session on prtr
→ Chatterbox Turbo on drtr:7744
→ local speaker
```

This phase intentionally disables interruption while the agent is
speaking. The microphone returns to listening automatically afterward.

## Run

The Q6_K_P Core must be available at `127.0.0.1:7712`, and both drtr
voice services must pass `/health`.

```bash
cd /home/prtr/prj/intraface/experiments/livekit-voice-agent
uv run agent.py console
```

Speak normally. Silero ends the turn after approximately 700ms of
silence. Pi responses are constrained to two short plain-text sentences
before synthesis.

## Run from trtr

The microphone and speakers are attached to trtr while Pi runs on prtr.
Use the A2A Pi facade through an SSH local-forward.

On trtr:

```bash
mkdir -p ~/prj/intraface-client

rsync -az \
  --exclude .venv \
  --exclude __pycache__ \
  prtr:/home/prtr/prj/intraface/experiments/livekit-voice-agent/ \
  ~/prj/intraface-client/livekit-voice-agent/

cd ~/prj/intraface-client/livekit-voice-agent
uv sync
sudo apt-get install -y libportaudio2

ssh -fNT \
  -o ExitOnForwardFailure=yes \
  -L 9999:127.0.0.1:9999 \
  prtr

PI_A2A_URL=http://127.0.0.1:9999 \
  uv run agent.py console --list-devices
```

Then start with the selected local device IDs:

```bash
PI_A2A_URL=http://127.0.0.1:9999 \
  uv run agent.py console \
    --input-device INPUT_ID \
    --output-device OUTPUT_ID
```

Environment overrides:

- `PARAKEET_URL`
- `CHATTERBOX_URL`
- `PI_CWD`
- `PI_PROVIDER`
- `PI_MODEL`
- `PI_SESSION_ID`
- `PI_SESSION_DIR`
- `PI_TIMEOUT_SECONDS`

## Phase 2

After half-duplex stability passes:

1. Enable interruptions.
2. Keep microphone input active during playback.
3. Add WebRTC or PipeWire acoustic echo cancellation.
4. Cancel playback and stale Pi/TTS work on barge-in.
5. Evaluate streaming STT and TTS separately.
