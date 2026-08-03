"""Send one synchronous text request to the Intraface Pi A2A server."""

import argparse
import asyncio
import json

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest
from google.protobuf.json_format import MessageToDict
from google.protobuf.json_format import MessageToJson
from google.protobuf.message import Message


def artifact_text(event: Message) -> str:
    payload = MessageToDict(event)
    parts = [
        part.get("text", "")
        for artifact in payload.get("task", {}).get("artifacts", [])
        for part in artifact.get("parts", [])
        if part.get("text")
    ]
    return "\n".join(parts)


async def send(prompt: str, base_url: str, text_only: bool) -> None:
    async with httpx.AsyncClient(timeout=180) as http_client:
        resolver = A2ACardResolver(
            httpx_client=http_client,
            base_url=base_url,
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
                if text_only and isinstance(event, Message):
                    text = artifact_text(event)
                    if text:
                        print(text)
                elif isinstance(event, Message):
                    print(MessageToJson(event, indent=2))
                elif hasattr(event, "model_dump_json"):
                    print(event.model_dump_json(indent=2))
                elif hasattr(event, "root") and hasattr(
                    event.root, "model_dump_json"
                ):
                    print(event.root.model_dump_json(indent=2))
                elif hasattr(event, "__dict__"):
                    print(json.dumps(event.__dict__, indent=2, default=str))
                else:
                    print(repr(event))
        finally:
            await client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:9999",
    )
    parser.add_argument(
        "--text-only",
        action="store_true",
        help="Print only completed text artifacts.",
    )
    arguments = parser.parse_args()
    asyncio.run(send(arguments.prompt, arguments.url, arguments.text_only))


if __name__ == "__main__":
    main()
