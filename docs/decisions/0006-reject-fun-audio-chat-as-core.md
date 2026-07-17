# 0006. Reject Fun-Audio-Chat-8B as a Core candidate

Date: 2026-07-13
Status: accepted

Supersedes: [0005]

## Context

ADR 0005 accepted Fun-Audio-Chat-8B for evaluation as a peer Core
candidate. The evaluation progressed through:

- Basic audio understanding and generation
- Speech-to-speech output
- Co-residency with Qwen3.6 IQ4_XS, one model per GPU
- A synchronous A2A facade over a persistent Pi session
- A complete audio-file → FAC → A2A/Pi → CosyVoice → WAV loop

The implementation proved technically feasible:

- FAC + CosyVoice used 22.3 GB on GPU 0
- Qwen3.6 IQ4_XS used 21.1 GB on GPU 1 at 131K context
- Persistent warm turn latency measured 9.72 seconds
- A2A task completion and Pi session continuity worked

However, the evaluation also clarified what FAC contributes and what it
costs.

FAC is an audio-native conversational model, not merely ASR plus TTS.
Its unique potential value is prosody/emotion-aware reasoning and joint
speech-token generation. The tested Pi bridge bypassed FAC's own
reasoning and speech-token plan, reducing it to request extraction around
Pi plus conventional CosyVoice synthesis.

For the required voice-agent workflow, a modular stack provides clearer
component boundaries. The evaluated implementation now uses:

- Local Silero for VAD and automatic endpointing
- Parakeet on drtr for speech transcription
- Qwen3.6/Pi on prtr for reasoning and tools
- Chatterbox Turbo on drtr for speech generation
- LiveKit Agents on trtr for conversation and audio transport

Those component projects have stronger runtime maturity and allow each
stage to be replaced or optimized independently.

## Decision

**Fun-Audio-Chat-8B is rejected as a Core candidate for the current
Intraface architecture.**

Do not continue toward a production FAC/Pi A2A voice stack. Use the
modular Silero → Parakeet → Pi/Qwen → Chatterbox direction for voice
work.

The evaluation artifacts remain as evidence:

- `docs/core-model-baselines/fun-audio-chat-8b-evaluation.md`
- `experiments/a2a-voice-bridge/`

Model files and the vendor checkout are not deleted by this decision.
Deletion is a separate destructive cleanup decision.

## Consequences

**Positive:**

- Frees the architecture from FAC's 18.6 GB resident-model requirement.
- Allows Qwen3.6 quality profiles to use both GPUs.
- Preserves Pi as the authoritative reasoning/tool agent.
- Voice components can evolve independently.
- VAD, turn-taking, streaming STT, and streaming TTS can be selected on
  their own merits.

**Negative:**

- Loses FAC's possible audio-native advantages: prosody, emotion,
  hesitation, and joint semantic/speech planning.
- The modular pipeline has a text bottleneck.
- A future voice implementation still requires a session controller and
  explicit turn-taking policy.

## Evidence retained

The A2A experiment remains useful beyond FAC. It demonstrated:

- A small A2A facade can invoke Pi synchronously.
- A fixed Pi session preserves context across independent A2A tasks.
- Requests can be serialized to prevent overlapping turns.

This evidence may be reused if A2A is adopted between future agents, but
it does not by itself justify FAC.

## Trigger for reconsideration

Revisit FAC only if audio-native reasoning becomes a concrete requirement
that the modular pipeline demonstrably cannot meet, and if upstream FAC
serving maturity materially improves.

## References

- [0005] `docs/decisions/0005-fun-audio-chat-as-core-candidate.md`
- `docs/core-model-baselines/fun-audio-chat-8b-evaluation.md`
- `docs/core-model-baselines/qwen3.6-35b-a3b-uncensored-aggressive.md`
- `docs/voice-chat-evaluation.md`