import asyncio
import json
import os
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest

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

        resolver = A2ACardResolver(httpx_client=http, base_url=BASE + "/coordinator")
        card = await resolver.get_agent_card()
        client = A2AClient(httpx_client=http, agent_card=card)
        params = MessageSendParams(
            **{
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "list agents"}],
                    "messageId": uuid4().hex,
                    "contextId": uuid4().hex,
                },
                "configuration": {"acceptedOutputModes": ["text/plain", "application/json"]},
            }
        )
        response = await client.send_message(
            SendMessageRequest(id=str(uuid4()), params=params)
        )
        result = response.root.result.model_dump(mode="json", exclude_none=True)
        rendered = json.dumps(result)
        assert "coordinator" in rendered
        assert "memory" in rendered

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
