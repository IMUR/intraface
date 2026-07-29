"""FastAPI signaling server for the Intraface voice bot.

Exposes:
    POST /api/offer   WebRTC SDP exchange (SmallWebRTCRequestHandler)
    PATCH /api/offer  trickle ICE candidate relay
    GET  /            static/index.html (the WebRTC client + transcript UI)
    GET  /static/*    assets
"""

import argparse
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from bot import run_bot

load_dotenv(override=True)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

small_webrtc_handler = SmallWebRTCRequestHandler()


@app.post("/api/offer")
async def offer(request: SmallWebRTCRequest, background_tasks: BackgroundTasks):
    async def webrtc_connection_callback(connection):
        background_tasks.add_task(run_bot, connection)

    return await small_webrtc_handler.handle_web_request(
        request=request,
        webrtc_connection_callback=webrtc_connection_callback,
    )


@app.patch("/api/offer")
async def ice_candidate(request: SmallWebRTCPatchRequest):
    await small_webrtc_handler.handle_patch_request(request)
    return {"status": "success"}


@app.get("/")
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await small_webrtc_handler.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Intraface voice bot server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7878)
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    logger.remove(0)
    logger.add(sys.stderr, level="TRACE" if args.verbose else "DEBUG")

    uvicorn.run(app, host=args.host, port=args.port)
