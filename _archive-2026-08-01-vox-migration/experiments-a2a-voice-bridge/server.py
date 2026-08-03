"""Minimal A2A server exposing Pi as a synchronous reasoning agent."""

import asyncio
import os
from pathlib import Path

import uvicorn
from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    TaskState,
)
from starlette.applications import Starlette


HOST = os.getenv("A2A_HOST", "127.0.0.1")
PORT = int(os.getenv("A2A_PORT", "9999"))
PI_CWD = Path(os.getenv("PI_CWD", "/home/prtr/prj/intraface"))
PI_PROVIDER = os.getenv("PI_PROVIDER", "llamacpp")
PI_MODEL = os.getenv(
    "PI_MODEL",
    "qwen3.6-35b-a3b-uncensored-q6-k-p",
)
PI_THINKING = os.getenv("PI_THINKING", "low")
PI_SESSION_ID = os.getenv("PI_SESSION_ID", "a2a-voice-bridge")
PI_SESSION_DIR = Path(
    os.getenv(
        "PI_SESSION_DIR",
        "/home/prtr/.intraface/state/a2a-pi-sessions",
    )
)
PI_TIMEOUT_SECONDS = float(os.getenv("PI_TIMEOUT_SECONDS", "120"))


class PiAgent:
    """Serialize requests through one persistent Pi session."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def invoke(self, prompt: str) -> str:
        PI_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        command = [
            "pi",
            "--mode",
            "text",
            "--print",
            "--provider",
            PI_PROVIDER,
            "--model",
            PI_MODEL,
            "--thinking",
            PI_THINKING,
            "--session-id",
            PI_SESSION_ID,
            "--session-dir",
            str(PI_SESSION_DIR),
            prompt,
        ]

        async with self._lock:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=PI_CWD,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=PI_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                raise RuntimeError(
                    f"Pi timed out after {PI_TIMEOUT_SECONDS:.0f}s"
                ) from None

        output = stdout.decode().strip()
        error = stderr.decode().strip()
        if process.returncode != 0:
            raise RuntimeError(
                f"Pi exited {process.returncode}: {error or output}"
            )
        if not output:
            raise RuntimeError(f"Pi returned no text. stderr: {error}")
        return output


class PiAgentExecutor(AgentExecutor):
    """Adapt the Pi subprocess to the A2A task lifecycle."""

    def __init__(self) -> None:
        self.agent = PiAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        task = context.current_task or new_task_from_user_message(context.message)
        if context.current_task is None:
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )
        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message("Pi is reasoning synchronously."),
        )

        prompt = get_message_text(context.message)
        if not prompt:
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message("No text input was provided."),
            )
            return

        try:
            result = await self.agent.invoke(prompt)
        except Exception as error:
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(str(error)),
            )
            return

        await updater.add_artifact(
            parts=[new_text_part(text=result, media_type="text/plain")],
        )
        await updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message("Pi completed the request."),
        )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        raise NotImplementedError("Cancellation is not supported yet.")


skill = AgentSkill(
    id="pi_reasoning",
    name="Pi Reasoning Agent",
    description=(
        "Runs a request synchronously through a persistent Pi agent session."
    ),
    input_modes=["text/plain"],
    output_modes=["text/plain"],
    tags=["pi", "reasoning", "a2a", "synchronous"],
    examples=["What is 17 multiplied by 4?"],
)
agent_card = AgentCard(
    name="Intraface Pi Agent",
    description="A synchronous A2A facade over the local Pi coding agent.",
    version="0.1.0",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(streaming=False),
    supported_interfaces=[
        AgentInterface(
            protocol_binding="JSONRPC",
            url=f"http://{HOST}:{PORT}",
            protocol_version="1.0",
        )
    ],
    skills=[skill],
)
request_handler = DefaultRequestHandler(
    agent_executor=PiAgentExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)
routes = [
    *create_agent_card_routes(agent_card),
    *create_jsonrpc_routes(request_handler, "/"),
]
app = Starlette(routes=routes)


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
