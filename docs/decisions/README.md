# Architecture decisions

Last reviewed against live state: **2026-07-15**

| ADR | Status | Current meaning |
|---|---|---|
| [0001](0001-core-unit-model-custody.md) | Accepted | Core and Unit model custody under `~/.intraface/models/{core,unit}` |
| [0002](0002-dev-tree-is-runtime-target.md) | Superseded by 0007 | Historical one-machine dev-as-runtime decision |
| [0003](0003-subprocess-over-bindings.md) | Accepted | Units invoke llama.cpp as isolated subprocesses |
| [0004](0004-engine-builds-under-intraface.md) | Deprecated | Engine relocation attempt abandoned after RUNPATH failure |
| [0005](0005-fun-audio-chat-as-core-candidate.md) | Superseded by 0006 | Historical FAC candidacy decision |
| [0006](0006-reject-fun-audio-chat-as-core.md) | Accepted | FAC rejected; modular LiveKit/Parakeet/Pi/Chatterbox voice direction |
| [0007](0007-explicit-per-node-runtime-deployment.md) | Accepted | Canonical source on prtr; explicit copied/installed runtimes on other nodes |

## Current architecture facts

- Resident Core: Qwen3.6 Uncensored Aggressive Q6_K_P, dual GPU, 262K.
- Pi and Qwen run on prtr.
- LiveKit voice client runs on trtr with local microphone/speaker and
  Silero VAD.
- Parakeet STT and Chatterbox TTS run on drtr.
- The trtr voice client reaches Pi through an SSH-forwarded A2A facade
  on prtr.
- Fun-Audio-Chat remains only as rejected-candidate evidence.

Historical ADR context is preserved even when operational facts later
change. Outcome/correction sections record those changes without
rewriting the original decision rationale.
