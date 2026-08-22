#!/usr/bin/env python3
"""LFM2.5-Encoder-350M HTTP server (transformers, CPU) — port 7719.

Exposes the bidirectional encoder backbone over HTTP:

  GET  /health            -> {"status": "ok"}
  POST /v1/embeddings     -> OAI-shaped; {"input": str|[str], "pooling": "mean"|"cls"}
  POST /hidden            -> per-token last hidden states {"hidden": [[[...]]]}
  POST /mlm               -> masked-token prediction:
                             {"text": "The capital of France is [MASK].", "top_k": 5}

Model is an MLM backbone (not embedding-trained); /v1/embeddings is provided
for convenience (mean pooling default) but retrieval quality is unverified
until fine-tuned — see https://huggingface.co/LiquidAI/LFM2.5-Encoder-350M
"""

import os
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModelForMaskedLM, AutoTokenizer

MODEL_PATH = os.environ.get(
    "ENCODER_MODEL_PATH",
    "/home/prtr/.intraface/models/unit/lfm2.5-encoder-350m/hf",
)
MAX_LEN = 8192

state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    tok = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    # NOTE: AutoModel alone maps checkpoint keys without the `lfm2.` prefix and
    # silently loads random weights (verified 2026-08-08). The MLM wrapper loads
    # correctly; use its inner encoder as the body.
    mlm = AutoModelForMaskedLM.from_pretrained(MODEL_PATH, trust_remote_code=True)
    body = mlm.lfm2
    body.eval()
    mlm.eval()
    state.update(tok=tok, body=body, mlm=mlm)
    yield


app = FastAPI(title="LFM2.5-Encoder-350M", lifespan=lifespan)


class EmbedRequest(BaseModel):
    input: str | list[str]
    pooling: str = "mean"  # mean | cls


class HiddenRequest(BaseModel):
    input: str | list[str]


class MlmRequest(BaseModel):
    text: str
    top_k: int = 5


def _encode(texts: list[str]) -> dict[str, torch.Tensor]:
    return state["tok"](
        texts,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=MAX_LEN,
    )


@torch.no_grad()
def _hidden(texts: list[str]) -> tuple[torch.Tensor, torch.Tensor]:
    enc = _encode(texts)
    out = state["body"](**enc)
    return out.last_hidden_state, enc["attention_mask"]


@app.get("/health")
def health():
    return {"status": "ok", "model": "LFM2.5-Encoder-350M"}


@app.post("/v1/embeddings")
def embeddings(req: EmbedRequest):
    texts = [req.input] if isinstance(req.input, str) else req.input
    if req.pooling not in ("mean", "cls"):
        raise HTTPException(400, "pooling must be 'mean' or 'cls'")
    hs, mask = _hidden(texts)
    if req.pooling == "cls":
        vec = hs[:, 0]
    else:
        m = mask.unsqueeze(-1).to(hs.dtype)
        vec = (hs * m).sum(1) / m.sum(1).clamp(min=1e-9)
    return {
        "object": "list",
        "model": "LFM2.5-Encoder-350M",
        "data": [
            {"object": "embedding", "index": i, "embedding": v.tolist()}
            for i, v in enumerate(vec)
        ],
    }


@app.post("/hidden")
def hidden(req: HiddenRequest):
    texts = [req.input] if isinstance(req.input, str) else req.input
    hs, mask = _hidden(texts)
    return {
        "model": "LFM2.5-Encoder-350M",
        "hidden": [
            hs[i, : int(mask[i].sum())].tolist() for i in range(len(texts))
        ],
    }


@app.post("/mlm")
@torch.no_grad()
def mlm(req: MlmRequest):
    tok = state["tok"]
    if tok.mask_token not in req.text:
        raise HTTPException(400, f"text must contain the mask token {tok.mask_token!r}")
    enc = tok(req.text, return_tensors="pt")
    logits = state["mlm"](**enc).logits
    pos = (enc["input_ids"][0] == tok.mask_token_id).nonzero()
    if len(pos) == 0:
        raise HTTPException(400, "mask token not found after tokenization")
    top = logits[0, pos[0].item()].topk(req.top_k)
    return {
        "model": "LFM2.5-Encoder-350M",
        "mask_token": tok.mask_token,
        "predictions": [
            {"token": tok.decode([t]).strip(), "token_id": t.item(), "score": s.item()}
            for s, t in zip(top.values, top.indices)
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=7719)
