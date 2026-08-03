"""Independent adapter smoke tests without opening the microphone."""

import asyncio
from pathlib import Path

import av
from livekit import rtc
from livekit.agents import llm

from providers import ChatterboxTTS, ParakeetSTT, PiLLM


TEST_WAV = Path(
    "/home/prtr/prj/intraface/vendor/Fun-Audio-Chat/examples/ck7vv9ag.wav"
)


async def decode_wav(path: Path):
    frames = []
    resampler = av.AudioResampler(
        format="s16",
        layout="mono",
        rate=16000,
    )
    with av.open(str(path)) as container:
        for decoded in container.decode(audio=0):
            for resampled in resampler.resample(decoded):
                frames.append(
                    rtc.AudioFrame(
                        data=resampled.to_ndarray().tobytes(),
                        sample_rate=16000,
                        num_channels=1,
                        samples_per_channel=resampled.samples,
                    )
                )
    return frames


async def main() -> None:
    frames = await decode_wav(TEST_WAV)
    transcription = await ParakeetSTT().recognize(frames)
    text = transcription.alternatives[0].text
    print(f"stt: {text}")

    context = llm.ChatContext.empty()
    context.add_message(
        role="user",
        content="What is 17 multiplied by 4? Answer in one sentence.",
    )
    response_parts = []
    async for chunk in PiLLM().chat(chat_ctx=context):
        if chunk.delta and chunk.delta.content:
            response_parts.append(chunk.delta.content)
    response = "".join(response_parts)
    print(f"pi: {response}")

    audio = await ChatterboxTTS().synthesize(response).collect()
    print(
        "tts: "
        f"sample_rate={audio.sample_rate}, "
        f"channels={audio.num_channels}, "
        f"duration={audio.duration:.2f}s"
    )


if __name__ == "__main__":
    asyncio.run(main())
