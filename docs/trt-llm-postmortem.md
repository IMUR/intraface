# TensorRT-LLM Evaluation — Post-Mortem

**Date:** 2025-07-20
**Host:** prtr (dual RTX 3090, 48 GB VRAM, CUDA 13.3, driver 610.43.02)
**Evaluated:** TensorRT-LLM 1.2.1, PyTorch backend
**Target model:** `nvidia/Qwen3.6-27B-NVFP4` (HuggingFace)

## Verdict: Not viable on this hardware/software stack (yet)

TensorRT-LLM 1.2.1 cannot run the Qwen3.6-27B model due to a circular dependency
between the framework and the `transformers` library.

## What happened

1. **Installation** — clean install in isolated `~/.trt-llm` venv, no pollution of Vice's environment. CUDA 13.1 packages installed. TensorRT-LLM 1.2.1 + PyTorch backend worked on TinyLlama (0.11s inference, empty output).

2. **Model incompatibility** — `nvidia/Qwen3.6-27B-NVFP4` is a vLLM-quantized NVFP4 model. Its `config.json` declares `model_type: qwen3_5`, which requires `transformers >= 5.12`.

3. **TensorRT-LLM pins `transformers==4.57.3`** — the framework hard-depends on this version. 4.57.3 does not recognize `qwen3_5` model type.

4. **Upgrade transformers → 5.14.1** — fixes `qwen3_5` recognition but breaks TensorRT-LLM internals: `AutoModelForVision2Seq` removed, `get_parameter_device`/`get_parameter_dtype` removed, `get_rope` renamed. 12+ breakage points across the framework's multimodal and model-loading code.

5. **Attempted compatibility shims** — patched the top-level `transformers` module to re-export missing symbols. Two patches resolved, but deeper internal API changes (12 total breakage sites) made it unfeasible.

6. **Pin transformers back to 4.57.3** — restores TensorRT-LLM compatibility but `qwen3_5` model type is unrecognized. Circular dependency.

## Root cause

TensorRT-LLM 1.2.1 was released before Qwen3.6 existed. The Qwen3.5/3.6 architecture was added to `transformers` in the 5.x series. TensorRT-LLM 1.2.1 pins `transformers==4.57.3`. No version of transformers satisfies both constraints simultaneously.

## When to revisit

- **TensorRT-LLM 1.3+** — check release notes for `qwen3_5`/Qwen3.6 support and updated transformers pin
- **Pre-built TensorRT engine** — if NVIDIA publishes a `.engine`/ checkpoint for Qwen3.6-27B, the TensorRT backend bypasses the PyTorch backend and `transformers` entirely. The vLLM-quantized NVFP4 weights are NOT a TensorRT-LLM engine checkpoint.
- **vLLM as alternative** — `nvidia/Qwen3.6-27B-NVFP4` was designed for vLLM, which supports NVFP4 natively. Would be a separate evaluation.

## Artifacts

- Venv: `~/.trt-llm/` (Python 3.12, TensorRT-LLM 1.2.1, transformers currently pinned at 4.57.3)
- CUDA packages: `cuda-libraries-13-1`, `cuda-compiler-13-1`, `cuda-libraries-dev-13-1`, `libopenmpi-dev`
- Test script: `/tmp/test_trt_llm.py`
- Activation: `source ~/.trt-llm/bin/activate && LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH`

## Status

- **TensorRT-LLM: on ice** — venv retained, do not delete
- **llama-server: restored** — PID logged, listening on `127.0.0.1:7712`
