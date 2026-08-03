"""FastAPI signaling server for the Intraface voice bot.

Exposes:
    POST /api/offer    WebRTC SDP exchange (SmallWebRTCRequestHandler)
    PATCH /api/offer   trickle ICE candidate relay
    GET  /             React client (frontend/dist/) — primary UI
    GET  /vanilla      vanilla JS client — fallback if React handshake fails
    GET  /assets/*     React build assets (hashed)
    GET  /vanilla/*    vanilla client assets
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

# Static layout. The React build (frontend/dist/) is the live page; the
# vanilla client (frontend/vanilla/) is kept as a fallback at /vanilla in
# case the React client's RTVI handshake ever regresses. Both resolve via
# path relative to this file so the bot can run from its checkout without
# a build step or env config.
_HERE = Path(__file__).parent
REACT_DIST_DIR = _HERE.parent.parent / "frontend" / "dist"
VANILLA_DIR = _HERE.parent.parent / "frontend" / "vanilla"

# Legacy static dir retained for backward compatibility — the prior page
# (static/index.html) and any other assets. Harmless to keep mounted.
STATIC_DIR = _HERE / "static"

app = FastAPI()
small_webrtc_handler = SmallWebRTCRequestHandler()

# React build assets. Mounted at /assets/ (the path the built index.html
# references via <script src="/assets/...">). html=False so directory
# listings don't get served at /assets/.
if REACT_DIST_DIR.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=REACT_DIST_DIR / "assets", html=False),
        name="react-assets",
    )

# Vanilla fallback assets mounted at /vanilla/. The vanilla index.html
# references styles.css relatively, so this preserves its expected paths.
if VANILLA_DIR.is_dir():
    app.mount(
        "/vanilla",
        StaticFiles(directory=VANILLA_DIR, html=True),
        name="vanilla",
    )

# Legacy /static/* mount — preserved for any old caller. Today this serves
# the original static/index.html page (now superseded by the React app at /).
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
async def serve_react_index():
    """Primary UI — the React build."""
    return FileResponse(REACT_DIST_DIR / "index.html")


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
