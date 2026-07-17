# Fun-Audio-Chat-8B — Evaluation Framework

**Status:** evaluation complete; **no-go as a Core candidate** per ADR
0006. Phase 1 passed, Phase 2 conditionally passed, and Phase 3 A2A +
synchronous audio-file-to-WAV tests passed at 9.72s warm latency.
Technical feasibility was demonstrated, but the modular
Silero → Parakeet → Pi/Qwen → Chatterbox direction is preferred. Phase
4 FAC stability testing is cancelled.

This document records the evaluation framework **before** running it, so
the criteria are explicit and can't drift to fit the result. Same format
as `docs/core-model-baselines/qwen3.6-35b-a3b-evaluation.md`. Results
have been appended in place as each phase completed.

## Intended role at evaluation start (superseded by ADR 0006)

**A third Core candidate alongside GLM-4.7-Flash and Qwen3.6-35B-A3B.**
Per ADR 0001, multiple Core candidates may coexist on disk with at most
one resident at a time. Fun-Audio-Chat-8B is a *different shape* of
Core (audio-native multimodal) — switching to it as the resident Core
enables a voice-interaction mode that GLM and Qwen3.6 cannot provide.

**Not** a replacement for Qwen3.6 in the text-reasoning role. Not a
new tier (sensorimotor/modal-bridge). A peer Core candidate that
expands the set of operational modes the Executor can be in.

See `docs/decisions/0005-fun-audio-chat-as-core-candidate.md` for the
architectural decision.

## What "passes evaluation" means

Fun-Audio-Chat-8B passes if it provides **voice-interaction capability
not available from text-only Core candidates** at acceptable quality and
latency on this hardware.

| Dimension | Must be | Stretch goal |
|---|---|---|
| Speech-to-text accuracy | Usable for chat | Comparable to Whisper-large |
| Speech-to-speech latency | <2s end-to-end | <1s |
| Voice quality (TTS output) | Intelligible, not robotic | Natural conversational |
| VRAM at inference | ≤24 GB (fits one 3090) | Room for larger batch |
| Concurrent with Qwen3.6 | N/A (mutual exclusion enforced) | — |
| Stability over 5+ minute conversation | No degradation | Indistinguishable from start |

**Fail condition:** Voice quality unusable for chat, latency >5s, or
basic inference doesn't run at all on this hardware.

### Caveat discovered during Phase 1 (2026-07-11)

The "Speech-to-text accuracy" row was based on a misread of what
`examples/infer_s2t.py` does. Despite the filename and the upstream
Chinese-language comment ("S2T 模式提示词 - 仅生成文本"), the script is
not ASR transcription — it is speech-input → text-response chat. The
"speech-to-text" label refers to **output modality** (text out, vs.
audio out), not the ASR sense. The model is a chat model with audio
I/O, not a transcription model.

The correct criterion for what `infer_s2t.py` actually tests is
**speech-input comprehension + text-response quality**, not verbatim
transcription accuracy. Phase 1 validated this — the model correctly
understood the spoken sleep-music query and produced a coherent
textual answer.

## Phase 1: Feasibility — does basic inference work?

### Pre-flight (verified 2026-07-11)

| Requirement | Status |
|---|---|
| Python 3.12 | ✓ `/home/prtr/.local/bin/python3.12` (mise-managed) |
| UV package manager | ✓ v0.11.28 (will replace conda flow) |
| CUDA | ✓ 12.4.131 installed, driver 550.163.01 |
| ffmpeg | ✓ v7.1.5 |
| Disk free | ✓ 510 GB |
| flash-attn | N/A for inference (training only) |

### Known concerns to validate

1. **PyTorch version** — card pins `torch==2.8.0` with `cu128` wheels; we have CUDA 12.4 driver. PyTorch is forward-compatible (newer driver runs older CUDA wheels) but worth verifying.
2. **`tensorrt-cu12==10.13.3.9`** in requirements.txt — large install (~1GB), possible CUDA compat issues.
3. **Custom VSTS onnxruntime index URL** in requirements.txt — may fail; we'll see.
4. **Pin conflicts** — `requirements.txt` pins aggressively (`pydantic==2.7.0`, `transformers==4.52.3`, etc.). UV venv isolates this from the rest of the system.

### Procedure

1. **Verify the resident Core's PID before stopping.** The pidfile at
   `~/.intraface/state/core-server.pid` drifted during 2026-07-11 prep —
   it pointed at a dead PID while the real llama-server ran under a
   different one. Identify the actual process via the listening port
   (`ss -tlnp 'sport = :7712'` or `lsof -i :7712`), not the pidfile.
   Once verified, stop the resident Core to free VRAM (~38 GB).
2. Clone `https://github.com/FunAudioLLM/Fun-Audio-Chat` with submodules
   to `~/prj/intraface/vendor/Fun-Audio-Chat/`.
3. Download model files via `hf` CLI:
   - `FunAudioLLM/Fun-Audio-Chat-8B` (~18 GB, 4 safetensors; measured 2026-07-11)
   - `FunAudioLLM/Fun-CosyVoice3-0.5B-2512` (**~9.1 GB — larger than the original ~5 GB estimate**, measured 2026-07-11)
4. Create UV venv with Python 3.12 (replaces card's `conda create`).
5. Install torch via UV (try `cu124` wheels first; fall back to `cu128` if needed).
   - **Measured (2026-07-11):** cu124 index resolved to `torch==2.6.0+cu124`, not the card-pinned `2.8.0`. CUDA verified working under torch 2.6.0 on driver 550.163.01 / CUDA 12.4. Forward-compat held.
6. Install requirements.txt via UV.
   - **Measured (2026-07-11):** required `--index-strategy unsafe-best-match` because the custom VSTS onnxruntime index exposed `protobuf` but not at the version `transformers` needed; UV's default safe-index strategy wouldn't fall back to PyPI. With the flag, install succeeded.
   - **Silent dependency fix applied:** pinned `ruamel.yaml==0.18.10` to resolve conflict with `hyperpyyaml==1.2.2` (which UV had resolved to `ruamel.yaml==0.19.1`, incompatible).
   - **onnxruntime CUDA EP broken at runtime:** needs `libcudnn.so.8` (cuDNN 8) but torch ships cuDNN 9. Falls back to CPU for input speech-tokenization. Functional; adds input-encoding latency. Generation dominates wall time anyway.
   - **TensorRT installed cleanly** (`tensorrt-cu12==10.13.3.9` + bindings + libs). Neither default inference path (`infer_s2t.py`, `infer_s2s.py` with default args) actually imports TensorRT; it's only needed if `load_trt=True` is explicitly set on the CosyVoice detokenizer. Safe to skip on future installs if install time matters more than TRT-optimized TTS.
7. Run `examples/infer_s2t.py` against `examples/ck7vv9ag.wav`.
   - **Required:** `PYTHONPATH=.` (script lives in `examples/` and imports the repo-root `funaudiochat` package).

### Checkpoint

- Does the model load?
- Does inference complete?
- What's the wall time?
- What's the actual VRAM peak?

**If checkpoint fails:** Stop. Don't proceed to Phase 2. Document what
failed and revisit.

### Phase 1 result (2026-07-11)

**Passed** — but on the dimension the script actually tests, not the
"speech-to-text accuracy" dimension the original criteria named.

| Item | Result |
|---|---|
| Model load | OK — 4 safetensor shards in ~3s |
| Inference completion | Exit 0 |
| Wall time | 54.7s total (load + generation of ~500-word response) |
| VRAM peak | 18,599 MiB (~18.2 GB) — within ≤24 GB target |
| Output | Coherent text-response to spoken query (not verbatim transcription) |
| CUDA errors / OOM / NaN | None |

Test audio: `examples/ck7vv9ag.wav` — 6.0s mono 16kHz. Content: *"I have
a hard time falling asleep. Is there any type of music that can help me
fall asleep faster?"* Model produced a ~500-word structured response
recommending sleep music. The response was coherent, contextually
appropriate, and correctly grounded in the spoken query — confirming
speech comprehension + text generation. It was **not** a transcription.

## Phase 2: Voice quality and latency

### Test procedure

Run `infer_s2s.py` (speech-to-speech) against multiple input audios:
- Short query (~3 seconds): "What is the time?"
- Medium query (~10 seconds): explain-request
- Long query (~30 seconds): paragraph reading

For each, measure:
- Total wall time
- Time to first audio output
- Output duration
- Quality (subjective: intelligibility, naturalness)

### Decision criterion

If end-to-end latency is <2s for short queries and voice quality is
acceptable, this is a real voice-interaction capability. If >5s, it's
not usable for chat and we document the limitation.

### Phase 2 result (2026-07-11)

**Conditional pass** — quality passes, latency fails the <2s stretch
and the >5s fail threshold for medium/long responses. The latency
failure is partly architectural (stock script is non-streaming —
generates all tokens, then synthesizes audio) and partly prompt
engineering (system prompt asked for 1-3 sentences; the model produced
paragraphs for medium and long queries).

| Query | Input | Generate | First-audio (post-gen) | Perceived latency | Output | Quality |
|---|---|---|---|---|---|---|
| short | 2.6s | 2.8s | 0.36s | ~3.1s | 2.0s | Clean, accurate: "The capital of France is Paris." |
| medium | 12.4s | 24.5s | 1.43s | ~25.9s | 26.8s | Intelligible, matches generated text closely |
| long | 31.0s | 84.0s | 1.61s | ~85.6s | 102.6s | Intelligible; Japanese proper-noun pronunciation slightly rough |

Model load (amortized, once): main 5.2s + CosyVoice 15.6s.

**Critical caveat on "time to first audio":** the stock `infer_s2s.py`
is non-streaming. The model autoregressively generates all tokens (text
+ speech) before any audio is synthesized. "First audio" in the table
above is measured from the start of token-to-wav conversion, *after*
generation completes. User-perceived latency from end of input speech
to first audio ≈ generation time + first-chunk time.

**VRAM:** peak 23,089 MiB on GPU0 (~1.5 GB headroom on the 24 GB 3090).
Both main model (18.6 GB) and CosyVoice co-located on `cuda:0`. GPU1
idle. **Tight margin** — Phase 4 stability testing would need to watch
for OOM if KV cache grows during extended conversation.

**Quality verification:** output WAVs transcribed externally and
compared against the model's generated text; transcriptions matched
nearly verbatim. Proper-noun mishearings (e.g. "Dotonbori" →
"Dardenbori") were transcription errors, not TTS artifacts.

### Against the success criteria

| Dimension | Target | Phase 2 result |
|---|---|---|
| S2S latency (short) | <2s stretch / <5s fail | ~3.1s — between stretch and fail |
| S2S latency (medium/long) | <2s | 26s / 86s — fails |
| Voice quality | Intelligible | Pass — clean, matches text |
| VRAM | ≤24 GB | 23.1 GB — passes, tight (~1.5 GB headroom) |
| Stability (5+ min) | — | Not tested (Phase 4) |

**Honest verdict:** the *stock script* fails the latency target. The
*model* might pass with a streaming implementation + tighter response
length constraints, but neither has been tested. The eval as written
tested the stock script, not the model's ceiling.

## Phase 3: Pi integration architecture

**In progress. Architecture-only A2A test passed 2026-07-12.**

### Correction to the prior reframe

The prior version of this document treated `parakeet-stt.service` and
`chatterbox-tts.service` on drtr as part of this stack. They are not.
They were mentioned only because an earlier evaluation kept reaching for
Whisper despite those cluster services already existing. This
Fun-Audio-Chat evaluation is local to prtr and remains distinct.

### Chosen evaluation architecture

Run two models concurrently, one per RTX 3090:

- **GPU 0:** Fun-Audio-Chat main model + CosyVoice TTS, co-located.
- **GPU 1:** Qwen3.6-35B-A3B IQ4_XS via ik_llama.cpp and Pi.

Use A2A as the protocol boundary between the voice-facing side and Pi.
The first implementation is intentionally synchronous and requires
explicit user actions for recording, submitting, and playing audio.
Streaming, interruption, and automatic delegation are deferred until
the blocking loop proves useful.

### Architecture-only test result

Experiment source:
`experiments/a2a-voice-bridge/`

Verified steady state:

| Component | Endpoint / GPU | Result |
|---|---|---|
| FAC + CosyVoice | `127.0.0.1:11235`, GPU 0 | 22,280 MiB VRAM |
| Qwen3.6 IQ4_XS | `127.0.0.1:7712`, GPU 1 | 21,049 MiB VRAM, 131,072 context |
| A2A Pi facade | `127.0.0.1:9999` | Agent Card + JSON-RPC 1.0 available |

The A2A facade invokes Pi synchronously with a fixed session ID. Requests
are serialized through one lock, so the persistent Pi session cannot
process overlapping turns.

Two tests passed:

1. `"What is 17 multiplied by 4?"` returned a completed A2A task with
   text artifact `"17 multiplied by 4 equals 68."`.
2. A separate A2A task asking for the prior result returned `"68"`,
   proving Pi session continuity across A2A task boundaries.

### Synchronous audio-file test result

Implemented a blocking CLI pipeline:

1. Accept an audio file path supplied by the user.
2. Use FAC audio understanding to produce the user request.
3. Send the request through the existing A2A Pi facade.
4. Convert Pi's returned text to WAV with CosyVoice.
5. Print the transcript, Pi response, output WAV path, and timing for
   every phase.

Test audio:
`vendor/Fun-Audio-Chat/examples/ck7vv9ag.wav`

| Phase | Result |
|---|---|
| FAC understanding | Exact spoken request recovered in 1.83s |
| A2A/Pi | Correct one-sentence response in 1.96s |
| CosyVoice | Valid 24 kHz mono WAV, 13.48s duration |
| Cold model loads | FAC 5.12s + CosyVoice 10.70s |
| TTS generation | 7.13s |
| Total cold loop | 26.74s |
| Measured resident warm loop | **9.72s** |

Output:
`experiments/a2a-voice-bridge/output/voice-response.wav`

**Result:** functional and latency pass in resident mode. The initial
unconstrained Pi answer took 49 seconds to synthesize; adding a
two-short-sentence plain-text voice contract reduced TTS to 7.13s. A
resident CLI process then removed 16.07s of repeated model loading and
measured 9.72s total warm turn latency:

- FAC understanding: 1.67s
- A2A/Pi: 1.87s
- CosyVoice: 6.17s

The resident CLI is available via `voice_roundtrip.py --interactive`.
Streaming and automatic turn detection remain deferred.

The existing web demo is not an intended interface. It remains only
verification/reference code.

## Phase 4: Stability (cancelled)

Not run. ADR 0006 closed FAC as a Core candidate after Phase 3. The
modular LiveKit voice implementation has its own stability evaluation in
`docs/voice-chat-evaluation.md`.

## Documentation outcome

**Final outcome (2026-07-13): technically feasible, architectural
no-go as a Core candidate.** FAC and CosyVoice fit together on GPU 0;
Qwen3.6 IQ4_XS fits on GPU 1 at 131,072 context; A2A task completion,
Pi session continuity, and the complete audio-file-to-WAV loop all work.

The evaluation nevertheless showed that the tested bridge bypasses
FAC's unique audio-native reasoning and reduces it to request extraction
around Pi plus CosyVoice synthesis. The implemented modular
Silero → Parakeet → Pi/Qwen → Chatterbox stack provides clearer
boundaries and frees both GPUs for higher-quality Core profiles.

Phase 4 FAC stability testing is cancelled. Keep this document and the
A2A experiment as evidence; see ADR 0006.

No verified-good FAC baseline will be created unless ADR 0006 is
superseded in the future.

## Original time estimate

- Phase 1 (feasibility): ~1-2 hours — dominated by download (24 GB)
  and dependency install (TensorRT is heavy)
- Phase 2 (voice quality): ~30 min — three test queries with measurement
- Phase 3 (Pi integration): **unknown** — depends on Phase 1-2 outcome
  and what integration path we choose
- Phase 4 (stability): ~30 min — extended conversation

**Total to pass/fail basic feasibility: ~2-3 hours.**

## Setup questions and resolutions

1. **Where does the source checkout live?** `~/prj/intraface/vendor/Fun-Audio-Chat/` per ADR 0002's dev/tree-is-runtime-target pattern. `vendor/` is in `.gitignore` (same rationale as `node_modules/`).
2. **Where do the model files live?** Per ADR 0001, Core models go under
   `~/.intraface/models/core/<name>/`. Fun-Audio-Chat has TWO models
   (main + TTS companion); both co-located under `~/.intraface/models/core/fun-audio-chat-8b/` since the TTS model isn't independently useful.
3. **Does UV handle the `--extra-index-url` for onnxruntime correctly?**
   The custom VSTS URL is unusual; may need a fallback.
   - **Resolved (2026-07-11):** No, not with UV's default safe-index strategy. Required `--index-strategy unsafe-best-match` to allow UV to fall back to PyPI for `protobuf` when the VSTS index didn't have the required version. See Phase 1 procedure notes.
