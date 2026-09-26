import asyncio
import json
import os
import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_stream_response_text, new_text_message
from a2a.types.a2a_pb2 import Role, SendMessageRequest

BASE = os.environ.get("VEXA2A_TEST_URL", "http://127.0.0.1:8797")


async def main() -> None:
    async with httpx.AsyncClient(timeout=10.0) as http:
        health = (await http.get(BASE + "/health")).json()
        assert health["ok"] is True
        assert health["protocol"] == "1.0"
        expected = {"coordinator", "memory", "verification", "renderer", "phone", "coding"}
        assert set(health["agents"]) == expected

        for agent in expected:
            card = (await http.get(BASE + f"/{agent}/.well-known/agent-card.json")).json()
            assert card["name"]
            assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"

        client = await create_client(
            BASE + "/coordinator",
            ClientConfig(
                streaming=False,
                polling=False,
                httpx_client=http,
                accepted_output_modes=["text/plain", "application/json"],
            ),
        )
        rendered_parts = []
        request = SendMessageRequest(
            message=new_text_message("list agents", role=Role.ROLE_USER)
        )
        async for chunk in client.send_message(request):
            rendered_parts.append(get_stream_response_text(chunk))
        rendered = "\n".join(rendered_parts)
        assert "coordinator" in rendered
        assert "memory" in rendered
        await client.close()

        local = (
            await http.post(
                BASE + "/vex/send",
                json={"agent": "coordinator", "message": "list agents"},
            )
        ).json()
        assert local["ok"] is True
        assert "memory" in local["result"]["agents"]

    print("VEXA2A_SMOKE=PASS")
    print("AGENT_COUNT=6")


if __name__ == "__main__":
    asyncio.run(main())
