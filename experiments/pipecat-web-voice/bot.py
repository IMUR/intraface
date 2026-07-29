"""Pipecat bot for the Intraface Core voice stack.

Wires three existing OpenAI-compatible services into a single pipecat pipeline:

    browser mic
    -> SmallWebRTCTransport.input
    -> Silero VAD (in user aggregator)
    -> Parakeet STT          (drtr:7733, reused)
    -> llama-server LLM      (prtr:7712, reused, thinking disabled)
    -> Chatterbox TTS        (drtr:7744, reused)
    -> SmallWebRTCTransport.output
    -> browser speaker

No custom adapter code. Every service is the stock pipecat OpenAI-compatible
adapter pointed at the existing endpoint via base_url. Reasoning is suppressed
at the Jinja template level via chat_template_kwargs (probed 2026-07-29:
without this flag, the Qwen3.6 Uncensored Aggressive resident emits only
reasoning_content and stops before producing user-facing text).
"""

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

PARAKEET_URL = os.getenv("PARAKEET_URL", "http://100.64.0.3:7733/v1")
CHATTERBOX_URL = os.getenv("CHATTERBOX_URL", "http://100.64.0.3:7744/v1")
# Bot runs on prtr alongside llama-server (loopback, per DECISIONS 0006).
# Parakeet/Chatterbox run on drtr (100.64.0.3) and are reached via tailnet —
# probe 2026-07-29: prtr→drtr RTT ~3ms, full STT ~110ms, full TTS ~1.5s.
LLAMA_URL = os.getenv("LLAMA_URL", "http://127.0.0.1:7712/v1")
LLAMA_MODEL = os.getenv("LLAMA_MODEL", "qwen3.6-uncensored-q6-k-p")

SYSTEM_INSTRUCTION = (
    "You are a conversational voice assistant. Your output is converted to "
    "speech, so use plain spoken language with no Markdown, no lists, no "
    "headings, and no citations. Keep responses short — typically one or two "
    "sentences. Answer directly."
)

DUMMY_API_KEY = "dummy"


class TranscriptForwarder(FrameProcessor):
    """Forwards transcripts to the browser via the WebRTC data channel.

    Two instances are needed because the user aggregator consumes
    TranscriptionFrame before it can reach a downstream processor. The
    ``role="user"`` instance sits between STT and the user aggregator and
    forwards final user transcripts; the ``role="assistant"`` instance sits
    after the LLM and accumulates TextFrames between LLMFullResponseStart
    and End, then forwards the complete assistant turn.
    """

    def __init__(self, webrtc_connection, *, role: str):
        super().__init__()
        self._webrtc_connection = webrtc_connection
        self._role = role
        self._assistant_text: list[str] = []

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if self._role == "user":
            if isinstance(frame, TranscriptionFrame):
                text = frame.text.strip()
                if text:
                    await self._send("user", text)
        else:
            if isinstance(frame, LLMFullResponseStartFrame):
                self._assistant_text = []
            elif isinstance(frame, TextFrame):
                self._assistant_text.append(frame.text)
            elif isinstance(frame, LLMFullResponseEndFrame):
                text = "".join(self._assistant_text).strip()
                self._assistant_text = []
                if text:
                    await self._send("assistant", text)

        await self.push_frame(frame, direction)

    async def _send(self, role: str, text: str) -> None:
        # Per pipecat docs: "use send_app_message on your SmallWebRTCConnection
        # instance." The transport auto-queues if the data channel isn't open
        # yet, and flushes when it opens. No frame wrapping needed.
        self._webrtc_connection.send_app_message({"role": role, "text": text})


async def run_bot(webrtc_connection) -> None:
    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_out_10ms_chunks=2,
        ),
    )
    stt = OpenAISTTService(
        api_key=DUMMY_API_KEY,
        base_url=PARAKEET_URL,
        settings=OpenAISTTService.Settings(model="parakeet-tdt-0.6b-v2"),
    )

    llm = OpenAILLMService(
        api_key=DUMMY_API_KEY,
        base_url=LLAMA_URL,
        model=LLAMA_MODEL,
        settings=OpenAILLMService.Settings(
            # Pipecat's Settings.extra is merged into the kwargs passed to
            # openai.AsyncCompletions.create(). The OpenAI SDK rejects
            # `chat_template_kwargs` as a top-level kwarg — it must be nested
            # inside `extra_body`. So we put extra_body inside pipecat's extra.
            # Verified 2026-07-29: without this nesting, "AsyncCompletions.create()
            # got an unexpected keyword argument 'chat_template_kwargs'".
            extra={
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": False}
                }
            },
            max_completion_tokens=120,
            temperature=0.3,
        ),
    )

    tts = OpenAITTSService(
        api_key=DUMMY_API_KEY,
        base_url=CHATTERBOX_URL,
        settings=OpenAITTSService.Settings(
            model="chatterbox-turbo",
            voice="alloy",
        ),
    )

    context = LLMContext()
    context.add_message({"role": "system", "content": SYSTEM_INSTRUCTION})

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        realtime_service_mode=False,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    # Two forwarders because the user aggregator consumes TranscriptionFrame
    # (line 786 of llm_response_universal.py): one before the aggregator to
    # catch user transcripts, one after the LLM to catch assistant text.
    # Each forwarder holds the webrtc_connection directly per pipecat docs:
    # "use send_app_message on your SmallWebRTCConnection instance."
    user_transcript = TranscriptForwarder(webrtc_connection, role="user")
    assistant_transcript = TranscriptForwarder(webrtc_connection, role="assistant")

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_transcript,
            user_aggregator,
            llm,
            assistant_transcript,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(t, client):
        logger.info("Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()
