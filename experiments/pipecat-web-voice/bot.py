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

import json
import os
import uuid

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TTSSpeakFrame,
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

# Layers 1–3 tools (see AGENTS.md). Registered as direct
# functions: pipecat's DirectFunctionWrapper auto-derives a clean
# FunctionSchema from each callable's type annotations and docstring.
# Verified 2026-07-29 the derived schema does not emit
# `additionalProperties: true`, so it does not trip the historical
# llama-server JSON-schema defect (now also resolved on the live server —
# see engines.toml [defects.ik_llama_json_schema]).
import tools as vox_tools

load_dotenv(override=True)

PARAKEET_URL = os.getenv("PARAKEET_URL", "http://100.64.0.3:7733/v1")
CHATTERBOX_URL = os.getenv("CHATTERBOX_URL", "http://100.64.0.3:7744/v1")
# Bot runs on prtr alongside llama-server (loopback, per DECISIONS 0006).
# Parakeet/Chatterbox run on drtr (100.64.0.3) and are reached via tailnet —
# probe 2026-07-29: prtr→drtr RTT ~3ms, full STT ~110ms, full TTS ~1.5s.
LLAMA_URL = os.getenv("LLAMA_URL", "http://127.0.0.1:7712/v1")
LLAMA_MODEL = os.getenv("LLAMA_MODEL", "qwen3.6-uncensored-q6-k-p")

SYSTEM_INSTRUCTION = f"""\
You are Vox, the spoken, read-only interface to the rtr cluster. You run as a
Pipecat service on prtr using the resident language model {LLAMA_MODEL}.

Ground claims about current cluster state and project files in tool results.
Use web search for information that may have changed, such as current
documentation, versions, packages, and recent research. General conversation
and stable knowledge do not require a tool. Treat tool output as evidence:
summarize what it establishes, and if a tool fails or cannot answer, say so
without guessing.

Your authority is read-only. You cannot change cluster state or write files.
Refuse requests to start, stop, edit, write, or delete before calling any tool;
say the user must use a write-enabled interface outside Vox, then stop. Never
send a mutation request to delegate_to_pi; delegated Pi has no tools. Do not
ask for more details, inspect, describe, or speculate about the target of a
refused mutation. Never claim an action or capability you do not have. Judge
the requested outcome, not whether a preliminary step would be read-only: for
example, "edit bot.py" must be refused without finding or reading bot.py.

Speak naturally in plain language. Do not use Markdown, headings, lists, or
spoken URLs. Be concise by default—usually one or two sentences—but honor an
explicit request for more detail. Translate tool results into speech rather
than reciting raw logs or file contents. For web results, name the source, not
its URL.
"""

DUMMY_API_KEY = "dummy"
_MAX_FILLER_ARGUMENT_CHARS = 60


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


# Map tool names to short, specific spoken fillers. Returns a string the TTS
# speaks immediately when the LLM starts a tool call, so the user isn't in
# silence during the SSH round-trip. Specific beats generic.
_TOOL_FILLERS = {
    # Layer 1 — cluster ops
    "check_node":     "checking {node}",
    "list_services":  "listing services on {node}",
    "get_log_tail":   "pulling the {service} log on {node}",
    "get_port_state": "checking listeners on {node}",
    # Layer 2 — filesystem (read-only). Paths are deliberately not spoken.
    "read_file":       "reading the file",
    "list_directory":  "listing the directory",
    "find_files":      "searching for files matching {pattern}",
    "grep_files":      "searching file contents for {pattern}",
    # Layer 3 — web search. Filler names the query so the user knows what's
    # being looked up during the SearXNG round-trip (~100-500ms).
    "web_search":      "searching the web for {query}",
    # Layer 4 — Pi receives the task but has no tools or mutation surface.
    "delegate_to_pi":  "asking Pi to reason about that",
}


def _tool_filler(function_calls) -> str:
    """Build a spoken filler for the first tool call in a batch.

    Returns an empty string if no specific filler can be derived, in which
    case the bot stays silent during the call — the result summary will
    follow shortly.
    """
    if not function_calls:
        return ""
    call = function_calls[0]
    template = _TOOL_FILLERS.get(call.function_name, "")
    if not template:
        return ""
    # Arguments arrive as a JSON string in OpenAI's tool_call format.
    try:
        args = (
            json.loads(call.arguments)
            if isinstance(call.arguments, str)
            else (call.arguments or {})
        )
    except (json.JSONDecodeError, TypeError):
        args = {}
    if not isinstance(args, dict):
        args = {}
    spoken_args = {
        key: _short_spoken_value(value)
        for key, value in args.items()
    }
    if any(not value for value in spoken_args.values()):
        return ""
    try:
        return template.format(**spoken_args)
    except (KeyError, IndexError):
        return ""


def _short_spoken_value(value: object) -> str:
    """Make a tool argument safe and brief enough to speak as filler."""
    if not isinstance(value, (str, int, float)):
        return ""
    text = " ".join(str(value).split())
    if len(text) <= _MAX_FILLER_ARGUMENT_CHARS:
        return text
    return f"{text[:_MAX_FILLER_ARGUMENT_CHARS - 1].rstrip()}…"


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
        settings=OpenAILLMService.Settings(
            model=LLAMA_MODEL,
            system_instruction=SYSTEM_INSTRUCTION,
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
            # Tool-using turns need more room than pure chat. A check_node
            # turn is roughly: 1 sentence filler + tool_call + ~50-token
            # result + 1-sentence spoken summary. 300 tokens is comfortable
            # headroom without letting responses drift long for voice.
            max_completion_tokens=300,
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

    context = LLMContext(tools=list(vox_tools.TOOL_DEFINITIONS))

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

    # Tool-call narration: when the LLM emits one or more tool calls, push a
    # short filler so the user isn't in silence during the SSH round-trip.
    # Specific narration beats generic ("checking drtr's uptime" > "looking
    # that up") — derived from the function name and arguments below.
    @llm.event_handler("on_function_calls_started")
    async def on_function_calls_started(_service, function_calls):
        filler = _tool_filler(function_calls)
        if filler:
            await tts.queue_frame(TTSSpeakFrame(filler))

    @llm.event_handler("on_function_calls_cancelled")
    async def on_function_calls_cancelled(_service, function_calls):
        # Barge-in during tool execution. The worker handles cancelling the
        # outstanding SSH call; we just log so the bot's behavior is visible
        # in the transcript of what happened.
        for call in function_calls:
            logger.info(f"Tool call cancelled by barge-in: {call.function_name}")

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
        app_resources={"pi_session_id": f"vox-{uuid.uuid4().hex}"},
    )

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(t, client):
        logger.info("Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()
