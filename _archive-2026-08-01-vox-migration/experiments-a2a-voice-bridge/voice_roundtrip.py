"""Blocking audio file -> FAC -> A2A/Pi -> CosyVoice -> WAV test."""

import argparse
import os
import subprocess
import time
import uuid
from pathlib import Path

import librosa
import torch
import torchaudio
from funaudiochat.register import register_funaudiochat
from transformers import AutoConfig, AutoModelForSeq2SeqLM, AutoProcessor
from utils.constant import AUDIO_TEMPLATE, DEFAULT_S2T_PROMPT
from utils.cosyvoice_detokenizer import get_audio_detokenizer


register_funaudiochat()

FAC_ROOT = Path("/home/prtr/prj/intraface/vendor/Fun-Audio-Chat")
FAC_MODEL = FAC_ROOT / "pretrained_models/Fun-Audio-Chat-8B"
BRIDGE_ROOT = Path("/home/prtr/prj/intraface/experiments/a2a-voice-bridge")
BRIDGE_CLIENT = BRIDGE_ROOT / "client.py"
VOICE_PROMPT_WAV = FAC_ROOT / "examples/ck7vv9ag.wav"
VOICE_PROMPT_TEXT = (
    "I have a hard time falling asleep. Is there any type of music that "
    "can help me fall asleep faster?"
)
TRANSCRIBE_INSTRUCTION = (
    "Transcribe the spoken user request faithfully. Output only the request "
    "as plain text. Do not answer it, explain it, or add commentary."
)
DEVICE = "cuda:0"


def load_fac() -> tuple[AutoProcessor, AutoModelForSeq2SeqLM]:
    config = AutoConfig.from_pretrained(FAC_MODEL)
    processor = AutoProcessor.from_pretrained(FAC_MODEL)
    model = AutoModelForSeq2SeqLM.from_pretrained(
        FAC_MODEL,
        config=config,
        torch_dtype=torch.bfloat16,
        device_map=DEVICE,
    )
    model.sp_gen_kwargs.update(
        {
            "text_greedy": True,
            "disable_speech": True,
        }
    )
    return processor, model


def transcribe(
    processor: AutoProcessor,
    model: AutoModelForSeq2SeqLM,
    audio_path: Path,
) -> str:
    audio = [librosa.load(audio_path, sr=16000)[0]]
    conversation = [
        {"role": "system", "content": DEFAULT_S2T_PROMPT},
        {
            "role": "user",
            "content": f"{AUDIO_TEMPLATE}\n{TRANSCRIBE_INSTRUCTION}",
        },
    ]
    text = processor.apply_chat_template(
        conversation,
        add_generation_prompt=True,
        tokenize=False,
    )
    inputs = processor(
        text=text,
        audio=audio,
        return_tensors="pt",
        return_token_type_ids=False,
    ).to(model.device)
    generated_ids, _ = model.generate(**inputs)
    generated_ids = generated_ids[:, inputs.input_ids.size(1) :]
    transcript = processor.decode(
        generated_ids[0],
        skip_special_tokens=True,
    ).strip()
    if not transcript:
        raise RuntimeError("FAC returned an empty transcript.")
    return transcript


def ask_pi(transcript: str) -> str:
    voice_prompt = (
        "This request came from a synchronous voice conversation. "
        "Answer in no more than two short sentences using plain spoken text. "
        "Do not use Markdown, lists, headings, or citations.\n\n"
        f"User request: {transcript}"
    )
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(BRIDGE_ROOT),
            "python",
            str(BRIDGE_CLIENT),
            "--text-only",
            voice_prompt,
        ],
        cwd=BRIDGE_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"A2A/Pi failed ({completed.returncode}): {completed.stderr.strip()}"
        )
    response = completed.stdout.strip()
    if not response:
        raise RuntimeError("A2A/Pi returned no text artifact.")
    return response


def synthesize(tts_model, response: str, output_path: Path) -> None:
    chunks = [
        item["tts_speech"]
        for item in tts_model.inference_instruct2(
            response,
            "You are a warm, concise voice assistant.<|endofprompt|>",
            str(VOICE_PROMPT_WAV),
            stream=False,
        )
    ]
    if not chunks:
        raise RuntimeError("CosyVoice returned no audio chunks.")
    speech = torch.cat(chunks, dim=1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(output_path, speech.cpu(), tts_model.sample_rate)


def run_turn(
    audio_path: Path,
    output_path: Path,
    processor: AutoProcessor,
    model: AutoModelForSeq2SeqLM,
    tts_model,
    transcript_override: str | None = None,
) -> None:
    started = time.monotonic()
    transcript = transcript_override or transcribe(
        processor,
        model,
        audio_path,
    )
    transcribed = time.monotonic()
    print(f"transcript: {transcript}", flush=True)

    response = ask_pi(transcript)
    pi_finished = time.monotonic()
    print(f"pi_response: {response}", flush=True)

    synthesize(tts_model, response, output_path)
    finished = time.monotonic()

    print(f"output_wav: {output_path.resolve()}")
    print(
        "turn_timing_seconds: "
        f"fac_understand={transcribed - started:.2f}, "
        f"a2a_pi={pi_finished - transcribed:.2f}, "
        f"tts={finished - pi_finished:.2f}, "
        f"total={finished - started:.2f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path, nargs="?")
    parser.add_argument(
        "--output",
        type=Path,
        default=BRIDGE_ROOT / "output/voice-response.wav",
    )
    parser.add_argument(
        "--transcript",
        help="Bypass FAC audio understanding with known text.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Keep models resident and prompt for repeated audio-file paths.",
    )
    arguments = parser.parse_args()

    if not arguments.interactive and arguments.audio is None:
        parser.error("audio is required unless --interactive is used")
    if arguments.audio is not None and not arguments.audio.exists():
        raise FileNotFoundError(arguments.audio)

    os.chdir(FAC_ROOT)
    started = time.monotonic()
    processor, model = load_fac()
    fac_loaded = time.monotonic()
    tts_model = get_audio_detokenizer()
    tts_loaded = time.monotonic()
    print(
        "model_load_timing_seconds: "
        f"fac_load={fac_loaded - started:.2f}, "
        f"tts_load={tts_loaded - fac_loaded:.2f}, "
        f"total={tts_loaded - started:.2f}"
    )

    if not arguments.interactive:
        run_turn(
            arguments.audio,
            arguments.output,
            processor,
            model,
            tts_model,
            arguments.transcript,
        )
        return

    print("Enter an audio-file path, or 'exit'.", flush=True)
    while True:
        raw_path = input("audio > ").strip()
        if raw_path.lower() in {"exit", "quit"}:
            return
        audio_path = Path(raw_path).expanduser().resolve()
        if not audio_path.exists():
            print(f"not found: {audio_path}", flush=True)
            continue
        output_path = (
            BRIDGE_ROOT
            / "output"
            / f"voice-response-{uuid.uuid4().hex[:8]}.wav"
        )
        try:
            run_turn(
                audio_path,
                output_path,
                processor,
                model,
                tts_model,
            )
        except Exception as error:
            print(f"turn failed: {error}", flush=True)


if __name__ == "__main__":
    main()
