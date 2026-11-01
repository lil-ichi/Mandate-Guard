"""Smoke test: MCP over streamable HTTP, like a real Claude/Cursor client."""
import asyncio
import subprocess
import time
import os

BASE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(BASE, ".venv", "bin", "python")

from mcp.client.streamable_http import streamable_http_client  # noqa: E402
from mcp import ClientSession  # noqa: E402


async def main() -> None:
    async with streamable_http_client("http://127.0.0.1:8130/mcp") as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("tools over HTTP:", [t.name for t in tools.tools])
            res = await s.call_tool("check_payment", {
                "agent_id": "demo-agent", "amount": 45, "currency": "USD",
                "vendor": "acme-cloud", "idempotency_key": "http-smoke-1",
            })
            import json
            out = json.loads(res.content[0].text)
            print("decision:", out["decision"], "| reason:", out["reason"])
            assert out["decision"] == "allowed"
            print("HTTP MCP smoke test OK")


p = subprocess.Popen(
    [PY, "mcp_server.py", "--transport", "http", "--port", "8130"],
    cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
try:
    time.sleep(4)
    asyncio.run(main())
finally:
    p.terminate()
