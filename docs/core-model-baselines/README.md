# Core model baselines

Verified profiles and evaluation records for models under Intraface Core
custody.

Last live-state verification: **2026-07-15**

## Current resident

### Qwen3.6-35B-A3B Uncensored Aggressive Q6_K_P

- Profile:
  `docs/core-model-baselines/qwen3.6-35b-a3b-uncensored-aggressive.md`
- Service: `127.0.0.1:7712`
- Engine: ik_llama.cpp build 4681
- Context: 262,144
- Placement: dual GPU, all 41 layers resident
- VRAM at live check: 18,087 MiB + 17,525 MiB
- Pi ID: `qwen3.6-35b-a3b-uncensored-q6-k-p`

## Peer candidates

### Qwen3.6 Uncensored Aggressive IQ4_XS

- Same profile document as Q6_K_P
- Single-GPU candidate
- Verified at 131,072 context on GPU 1
- Intended for a co-resident workload on GPU 0

### Stock Qwen3.6-35B-A3B Q8_0

- Evaluation:
  `docs/core-model-baselines/qwen3.6-35b-a3b-evaluation.md`
- Dual-GPU 262K profile measured
- Not currently resident
- Full planned quality comparison was not completed

### GLM-4.7-Flash Q8_0

- Baseline: `docs/core-model-baselines/glm-4.7-flash.md`
- Verified 96K launch and swap procedure
- Not currently resident

## Rejected candidates

### Fun-Audio-Chat-8B

- Evaluation: `docs/core-model-baselines/fun-audio-chat-8b-evaluation.md`
- Technically feasible but rejected as a Core candidate by ADR 0006
- Model files and vendor checkout remain as evaluation evidence
- No verified-good baseline will be created unless ADR 0006 is
  superseded

## Conventions

- A **baseline** records a verified launch and measured runtime profile.
- An **evaluation** records criteria, experiments, and unresolved or
  rejected outcomes.
- Every resident profile must match Pi's configured model ID and context
  window.
- Live process facts override old PID files and historical evaluation
  text.
- Core candidates are peers on disk; only the explicitly identified
  resident serves port 7712.
