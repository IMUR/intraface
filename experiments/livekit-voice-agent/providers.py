"""LiveKit provider adapters for the existing Intraface voice stack."""

import asyncio
import os
import uuid
from pathlib import Path

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from livekit import rtc
from livekit.agents import (
    APIConnectOptions,
    DEFAULT_API_CONNECT_OPTIONS,
    llm,
    stt,
    tts,
)
from livekit.agents.types import NOT_GIVEN, NotGivenOr


PARAKEET_URL = os.getenv(
    "PARAKEET_URL",
    "http://drtr:7733/v1/audio/transcriptions",
)
CHATTERBOX_URL = os.getenv(
    "CHATTERBOX_URL",
    "http://drtr:7744/v1/audio/speech",
)
PI_CWD = Path(os.getenv("PI_CWD", "/home/prtr/prj/intraface"))
PI_PROVIDER = os.getenv("PI_PROVIDER", "llamacpp")
PI_MODEL = os.getenv(
    "PI_MODEL",
    "qwen3.6-35b-a3b-uncensored-q6-k-p",
)
PI_SESSION_ID = os.getenv("PI_SESSION_ID", "livekit-voice-session")
PI_SESSION_DIR = Path(
    os.getenv(
        "PI_SESSION_DIR",
        "/home/prtr/.intraface/state/livekit-voice-sessions",
    )
)
PI_TIMEOUT_SECONDS = float(os.getenv("PI_TIMEOUT_SECONDS", "180"))
PI_A2A_URL = os.getenv("PI_A2A_URL")


class ParakeetSTT(stt.STT):
    """Batch STT adapter for the existing OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=False,
                interim_results=False,
            )
        )

    @property
    def model(self) -> str:
        return "parakeet-tdt-0.6b-v2"

    @property
    def provider(self) -> str:
        return "drtr"

    async def _recognize_impl(
        self,
        buffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        frame = rtc.combine_audio_frames(
            buffer if isinstance(buffer, list) else [buffer]
        )
        files = {
            "file": (
                "speech.wav",
                frame.to_wav_bytes(),
                "audio/wav",
            )
        }
        async with httpx.AsyncClient(timeout=conn_options.timeout) as client:
            response = await client.post(PARAKEET_URL, files=files)
            response.raise_for_status()
            transcript = response.json()["text"].strip()

        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            request_id=uuid.uuid4().hex,
            alternatives=[
                stt.SpeechData(
                    language="en",
                    text=transcript,
                    confidence=1.0,
                )
            ],
        )


class PiLLM(llm.LLM):
    """Synchronous persistent Pi session exposed as a LiveKit LLM."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = asyncio.Lock()

    @property
    def model(self) -> str:
        return PI_MODEL

    @property
    def provider(self) -> str:
        return "pi"

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[llm.ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict] = NOT_GIVEN,
    ) -> llm.LLMStream:
        return PiLLMStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            lock=self._lock,
        )


class PiLLMStream(llm.LLMStream):
    def __init__(
        self,
        provider: PiLLM,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        conn_options: APIConnectOptions,
        lock: asyncio.Lock,
    ) -> None:
        super().__init__(
            provider,
            chat_ctx=chat_ctx,
            tools=tools,
            conn_options=conn_options,
        )
        self._lock = lock
        self._process: asyncio.subprocess.Process | None = None

    async def _invoke_a2a(self, prompt: str) -> str:
        if PI_A2A_URL is None:
            raise RuntimeError("PI_A2A_URL is not configured.")

        async with httpx.AsyncClient(timeout=PI_TIMEOUT_SECONDS) as http_client:
            resolver = A2ACardResolver(
                httpx_client=http_client,
                base_url=PI_A2A_URL,
            )
            agent_card = await resolver.get_agent_card()
            client = await create_client(
                agent=agent_card,
                client_config=ClientConfig(
                    streaming=False,
                    httpx_client=http_client,
                ),
            )
            try:
                request = SendMessageRequest(
                    message=new_text_message(prompt, role=Role.ROLE_USER),
                )
                async for event in client.send_message(request):
                    if not isinstance(event, Message):
                        continue
                    payload = MessageToDict(event)
                    parts = [
                        part.get("text", "")
                        for artifact in payload.get("task", {}).get(
                            "artifacts", []
                        )
                        for part in artifact.get("parts", [])
                        if part.get("text")
                    ]
                    if parts:
                        return "\n".join(parts)
            finally:
                await client.close()

        raise RuntimeError("A2A/Pi returned no text artifact.")

    async def _invoke_local_pi(self, prompt: str) -> str:
        PI_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        command = [
            "pi",
            "--offline",
            "--approve",
            "--provider",
            PI_PROVIDER,
            "--model",
            PI_MODEL,
            "--session-id",
            PI_SESSION_ID,
            "--session-dir",
            str(PI_SESSION_DIR),
            "--print",
            prompt,
        ]
        self._process = await asyncio.create_subprocess_exec(
            *command,
            cwd=PI_CWD,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                self._process.communicate(),
                timeout=PI_TIMEOUT_SECONDS,
            )
        except (TimeoutError, asyncio.CancelledError):
            self._process.kill()
            await self._process.wait()
            raise

        output = stdout.decode().strip()
        error = stderr.decode().strip()
        if self._process.returncode != 0:
            raise RuntimeError(
                f"Pi exited {self._process.returncode}: {error or output}"
            )
        if not output:
            raise RuntimeError(f"Pi returned no text. stderr: {error}")
        return output

    async def _run(self) -> None:
        user_messages = [
            message.raw_text_content
            for message in self._chat_ctx.messages()
            if message.role == "user" and message.raw_text_content
        ]
        if not user_messages:
            raise RuntimeError("Pi received no user text.")

        voice_prompt = (
            "This request came from a realtime voice conversation. "
            "Answer in no more than two short sentences using plain spoken "
            "text. Do not use Markdown, lists, headings, or citations.\n\n"
            f"User request: {user_messages[-1]}"
        )
        async with self._lock:
            output = (
                await self._invoke_a2a(voice_prompt)
                if PI_A2A_URL
                else await self._invoke_local_pi(voice_prompt)
            )

        self._event_ch.send_nowait(
            llm.ChatChunk(
                id=uuid.uuid4().hex,
                delta=llm.ChoiceDelta(
                    role="assistant",
                    content=output,
                ),
            )
        )


class ChatterboxTTS(tts.TTS):
    """Batch WAV TTS adapter for the existing OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=24000,
            num_channels=1,
        )

    @property
    def model(self) -> str:
        return "chatterbox-turbo"

    @property
    def provider(self) -> str:
        return "drtr"

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> tts.ChunkedStream:
        return ChatterboxStream(
            tts=self,
            input_text=text,
            conn_options=conn_options,
        )


class ChatterboxStream(tts.ChunkedStream):
    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        request_id = uuid.uuid4().hex
        async with httpx.AsyncClient(timeout=self._conn_options.timeout) as client:
            response = await client.post(
                CHATTERBOX_URL,
                json={"input": self._input_text},
            )
            response.raise_for_status()

        output_emitter.initialize(
            request_id=request_id,
            sample_rate=24000,
            num_channels=1,
            mime_type="audio/wav",
        )
        output_emitter.push(response.content)
        output_emitter.flush()
