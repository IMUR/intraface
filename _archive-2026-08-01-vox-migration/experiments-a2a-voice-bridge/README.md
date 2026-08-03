# A2A voice bridge experiment

Minimal, synchronous protocol test for the proposed FAC ↔ Pi link.

## What this phase proves

It proves that an A2A client can send a text task to a persistent Pi
session and receive the completed result. It does **not** yet prove audio
input, TTS output, streaming, interruption, or automatic delegation.

## Prerequisite

The Pi model configured by `PI_PROVIDER` / `PI_MODEL` must already be
available. Defaults:

- provider: `llamacpp`
- model: `qwen3.6-35b-a3b`
- A2A endpoint: `http://127.0.0.1:9999`

## Run

Terminal 1:

```bash
uv run server.py
```

Terminal 2:

```bash
uv run client.py "What is 17 multiplied by 4? Answer in one sentence."
```

The client prints the A2A task events as JSON. A passing test includes a
completed task with Pi's answer in a text artifact.

## Configuration

Environment variables:

- `A2A_HOST`, `A2A_PORT`
- `PI_CWD`
- `PI_PROVIDER`, `PI_MODEL`
- `PI_THINKING` (default: `low` for routine voice turns)
- `PI_SESSION_ID`, `PI_SESSION_DIR`
- `PI_TIMEOUT_SECONDS`

Requests are serialized through one `asyncio.Lock`, so the persistent Pi
session cannot process overlapping turns.

## Next phase

The text protocol test and one blocking audio-file round trip have
passed. To reproduce the full loop, keep `server.py` running and run:

```bash
cd /home/prtr/prj/intraface/experiments/a2a-voice-bridge
CUDA_VISIBLE_DEVICES=0 \
PYTHONPATH=/home/prtr/prj/intraface/vendor/Fun-Audio-Chat \
/home/prtr/prj/intraface/vendor/Fun-Audio-Chat/.venv/bin/python \
  voice_roundtrip.py \
  /path/to/input.wav
```

The command prints the recovered request, Pi response, output WAV path,
and phase timings. The first iteration intentionally requires explicit
user actions to record, submit, and play audio.

For repeated turns without model reloads:

```bash
CUDA_VISIBLE_DEVICES=0 \
PYTHONPATH=/home/prtr/prj/intraface/vendor/Fun-Audio-Chat \
/home/prtr/prj/intraface/vendor/Fun-Audio-Chat/.venv/bin/python \
  voice_roundtrip.py --interactive
```

The process loads FAC and CosyVoice once, then prompts for audio-file
paths. Each turn writes a uniquely named WAV under `output/`.

Streaming and automatic turn-taking are deferred.
