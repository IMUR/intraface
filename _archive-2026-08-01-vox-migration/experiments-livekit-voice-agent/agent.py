"""Hands-free local voice agent using LiveKit console mode."""

from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli
from livekit.plugins import silero

from providers import ChatterboxTTS, ParakeetSTT, PiLLM


server = AgentServer()


@server.rtc_session()
async def entrypoint(context: JobContext) -> None:
    session = AgentSession(
        vad=silero.VAD.load(
            min_speech_duration=0.10,
            min_silence_duration=0.70,
            prefix_padding_duration=0.30,
            activation_threshold=0.50,
            force_cpu=True,
        ),
        stt=ParakeetSTT(),
        llm=PiLLM(),
        tts=ChatterboxTTS(),
        turn_handling={
            "turn_detection": "vad",
            "endpointing": {
                "mode": "fixed",
                "min_delay": 0.70,
                "max_delay": 2.50,
            },
            "interruption": {
                "enabled": False,
                "discard_audio_if_uninterruptible": True,
            },
            "preemptive_generation": {
                "enabled": False,
            },
        },
    )
    await session.start(
        agent=Agent(
            instructions=(
                "You are the voice interface to the local Pi agent. "
                "Keep spoken responses short and direct."
            )
        ),
        room=context.room,
    )


if __name__ == "__main__":
    cli.run_app(server)
