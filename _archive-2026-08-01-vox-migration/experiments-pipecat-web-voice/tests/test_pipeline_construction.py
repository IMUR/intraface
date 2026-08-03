"""Smoke test: construct the bot pipeline against mock services.

Verifies run_bot() builds without API-shape errors and that the
OpenAILLMService settings accept the chat_template_kwargs.extra field.
Does NOT open a real WebRTC connection or call the live backends —
that requires a browser and a human ear.

Run with:
    uv run python tests/test_pipeline_construction.py
"""

import asyncio
import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Allow importing bot.py from the parent dir
sys.path.insert(0, str(Path(__file__).parent.parent))

import bot  # noqa: E402


async def main():
    # 1. Verify OpenAILLMService.Settings accepts the extra field
    from pipecat.services.openai.llm import OpenAILLMService
    settings = OpenAILLMService.Settings(
        extra={"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}},
        max_completion_tokens=120,
        temperature=0.3,
    )
    assert settings.extra == {
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}
    }, f"extra not stored: {settings.extra}"
    print("PASS: OpenAILLMService.Settings.extra accepts extra_body.chat_template_kwargs")

    # 2. Verify the run_bot function signature
    sig = inspect.signature(bot.run_bot)
    params = list(sig.parameters.keys())
    assert params == ["webrtc_connection"], f"unexpected params: {params}"
    print(f"PASS: run_bot signature {sig}")

    # 3. Construct the bot pipeline with a mock connection.
    # SmallWebRTCTransport wires up event handlers on the connection during
    # __init__, so the mock needs to accept arbitrary attribute access and
    # return callables.

    def mock_event_handler(name):
        def decorator(func):
            return func
        return decorator

    mock_conn = MagicMock()
    mock_conn.pc_id = "test-pc"
    mock_conn.event_handler = mock_event_handler
    # MagicMock auto-provides send_app_message; no transport patching needed.

    # Prevent WorkerRunner.run from blocking.
    from pipecat.workers.runner import WorkerRunner
    original_runner_run = WorkerRunner.run
    original_runner_add = WorkerRunner.add_workers

    async def stub_run(self):
        pass

    async def stub_add(self, *workers):
        pass

    WorkerRunner.run = stub_run
    WorkerRunner.add_workers = stub_add

    try:
        await bot.run_bot(mock_conn)
        print("PASS: run_bot() constructed pipeline without errors")
    finally:
        WorkerRunner.run = original_runner_run
        WorkerRunner.add_workers = original_runner_add

    # 4. Verify env-var overrides take effect
    import os
    os.environ["LLAMA_MODEL"] = "test-model"
    import importlib
    importlib.reload(bot)
    assert bot.LLAMA_MODEL == "test-model", f"override failed: {bot.LLAMA_MODEL}"
    print(f"PASS: env override works (LLAMA_MODEL={bot.LLAMA_MODEL})")


if __name__ == "__main__":
    asyncio.run(main())
