# Qwen3.6-35B-A3B — Evaluation Framework

**Status:** historical stock-Q8 evaluation. The measured 262K profile
remains a valid peer candidate but is not resident. Qwen3.6 Uncensored
Aggressive Q6_K_P is resident as of 2026-07-15. This evaluation completed
launch, memory, reasoning-format, and spot-quality checks; the planned
full comparison suite was not completed.

This document records the evaluation framework **before** running it, so
the criteria are explicit and can't drift to fit the result.

## Phase 1 findings (2026-07-07)

Verified-good launch flags (post-tuning):

```bash
cd ~/prj/ik_llama.cpp && ./build/bin/llama-server \
  -m ~/.intraface/models/core/qwen3.6-35b-a3b/Qwen3.6-35B-A3B-Q8_0.gguf \
  --host 127.0.0.1 --port 7712 \
  -c 262144 -np 1 -ngl 99 --n-cpu-moe 4 \
  --jinja
```

Comparison vs GLM at its known-good config:

| Metric | GLM @ 96K | Qwen3.6 @ 262K |
|---|---|---|
| Context length | 96K | 262K (2.7× larger) |
| KV cache | 5,076 MiB | 5,120 MiB |
| VRAM GPU 0 | 21,936 MiB | 19,575 MiB |
| VRAM GPU 1 | 22,058 MiB | 18,559 MiB |
| Total VRAM | 43,994 MiB (~95%) | 38,134 MiB (~79%) |
| VRAM free | ~4 GB | ~10 GB |

**Qwen3.6 at 2.7× the context uses less VRAM than GLM.** The
architectural KV advantage (Gated DeltaNet + GQA-2-KV-heads) is
verified at runtime, not just spec'd in the model card.

### Quality spot-checks (single prompt, non-scientific)

| Task | Mode | Result | Latency |
|---|---|---|---|
| "47 × 23" | non-thinking | ✓ correct (1081) | 0.4s |
| "Say hi in 5 words" | non-thinking | ✓ correct | 0.3s |
| Python decorator with TTL | non-thinking | ✓ correct, idiomatic | 3.9s for 343 tokens (~88 tok/s) |
| Python decorator with TTL | thinking | ran out of token budget (1500) before producing answer; reasoning alone filled the budget | 16.5s |

**Lesson:** thinking mode needs `max_tokens: 8000+` (32K+ recommended by
card) to be useful. Non-thinking mode is snappy and produces correct
results for routine coding tasks. Default-to-non-thinking is likely the
right Pi configuration; reserve thinking mode for explicitly hard tasks.

## What "passes evaluation" means

Qwen3.6 passes if it is **at least as good as GLM-4.7-Flash** across all
of the following dimensions, with no regression severe enough to revert.

| Dimension | Must be | Stretch goal |
|---|---|---|
| Functional correctness on representative prompts | ≥ GLM | Strictly better |
| Latency at low context (<8K) | ≤ 1.5× GLM | ≤ GLM |
| Latency at high context (>32K) | ≤ 2× GLM | ≤ GLM |
| Tool-calling reliability via Pi | Works on first attempt | Indistinguishable from GLM |
| VRAM headroom | ≥ GLM (already confirmed: 72% vs 95%) | Substantial headroom for context growth |
| Pi integration (streaming, conversation) | Works without errors | Smooth UX |
| Stability over 1h+ continuous use | No crashes, no degraded latency | Indistinguishable from GLM |

**Fail condition:** Any single regression that breaks Pi usability or
makes Qwen3.6 strictly worse than GLM for the actual workflow.

## Phase 1: Optimal launch flags (historical plan)

At evaluation start, the model ran with flags copied from GLM minus
GLM-specific ones. The final measured launch is recorded above.

### Variables to test

| Flag | Initial value | Range tested/planned | Hypothesis |
|---|---|---|---|
| `-c` (context) | 98304 | 131072, 196608, 262144 | Native 262144; 9GB free VRAM may allow |
| `--n-cpu-moe` | 4 | 0, 2, 4, 8 | Qwen3.6 has 256 experts vs GLM's 96; optimal may differ |
| `--cache-ram` | 8192 (auto) | 4096, 8192, 16384, 32768 | More cache = more prompt reuse |
| `-fa` (flash attn) | unset | unset vs enabled | Usually a free win on Ampere |
| `--spec-type mtp:...` | unset | unset vs `mtp:n_max=1,p_min=0.0` | ikawrakow: "much slower than no MTP on CUDA" — likely skip |

### Test procedure (per variation)

1. Stop Qwen3.6, restart with new flag values.
2. Time: model load, first-token-latency on 1K prompt, completion of 100 tokens.
3. Check VRAM headroom after load (`nvidia-smi`).
4. Note any warnings/errors in log.

### Decision criterion

Pick the configuration that maximizes VRAM headroom while keeping
time-to-first-token under ~2× GLM baseline. Document as the
verified-good config.

## Phase 2 findings (2026-07-07, post-diagnosis)

**Issue identified and resolved:** Qwen3.6 was launched with default
`--reasoning-format none`, which leaves `<think>` tags inline in
`message.content`. This caused Pi to display thinking content inline
in the chat UI. Root cause identified via server log showing literal
`<think>` tags in output + comparison with historical GLM session
JSON showing `{"type": "thinking", "thinkingSignature": "reasoning_content"}`
structures (Pi knows how to handle separated thinking).

**Fix applied:** Restarted Core with `--reasoning-format deepseek`.
Verified via direct API test:
- `message.content` now contains only the answer
- `message.reasoning_content` is a separate field containing the thinking
- Pi's existing handling (built for GLM's reasoning_content) should apply unchanged

**Verified-good launch config for Qwen3.6:**

```bash
cd ~/prj/ik_llama.cpp && ./build/bin/llama-server \
  -m ~/.intraface/models/core/qwen3.6-35b-a3b/Qwen3.6-35B-A3B-Q8_0.gguf \
  --host 127.0.0.1 --port 7712 \
  -c 262144 -np 1 -ngl 99 --n-cpu-moe 4 \
  --jinja \
  --reasoning-format deepseek
```

### Open sampling questions

Qwen3.6's card recommends specific sampling profiles for thinking vs
non-thinking modes. Still need to test:
- Whether Pi needs different defaults per Qwen profile
- Whether to default-enable thinking or default-disable
- MTP speculative decoding — available but untested, may help or hurt

## Phase 3: Quality comparison vs GLM

### Test prompts (same prompt to both models, same flags except model-specific)

1. **Coding — small task:** Implement and explain a Python decorator that
   caches results with a TTL.
2. **Coding — larger task:** Read `units/extract/extract.ts` (281 lines)
   and explain what it does in 3 sentences.
3. **Extraction — real task:** Use the `extract` Unit on
   `.archive/Orchestrator_Model_Investigation_Report.md`. Compare outputs.
4. **Reasoning — multi-step:** Word problem with 3-4 inference steps.
5. **Tool-call:** Single-tool request ("What is the time?") via Pi.

### Comparison criteria

For each prompt:
- **Correctness** (does it actually answer the question correctly?)
- **Verbosity** (token count vs GLM)
- **Latency** (time to first token + time to completion)
- **Style** (subjective: clarity, structure)

## Phase 4: Pi integration

### Things to verify

- [ ] Basic chat works (one round-trip)
- [ ] Multi-turn conversation works (context preserved)
- [ ] Streaming works (responses appear incrementally)
- [ ] Tool calls work (if Pi has any registered besides `extract`)
- [ ] Thinking-mode content displays correctly (not as `<think>` tags
      visible to user)
- [ ] Long context doesn't break (paste 50K tokens)
- [ ] Stop/restart works cleanly

## Phase 5: Stability

Run Qwen3.6 for an extended period (1h+) with normal Pi usage. Watch
for:
- Memory leaks
- Latency degradation
- Crashes
- Log errors

## Documentation outcome

The stock-Q8 model remains on disk as a peer candidate. Current
uncensored profiles and resident measurements are maintained in
`docs/core-model-baselines/qwen3.6-35b-a3b-uncensored-aggressive.md`.

## Time estimate

- Phase 1 (flags): ~30 min — multiple restarts with measurements
- Phase 2 (sampling): ~30 min — multiple prompts per profile
- Phase 3 (quality): ~45 min — 5 prompts × 2 models
- Phase 4 (Pi integration): ~30 min — manual Pi usage
- Phase 5 (stability): ~1h+ unattended

**Total: ~2.5-3 hours of active evaluation.**
