"""Live proof: an MCP client discovering and calling our check_payment tool."""
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    params = StdioServerParameters(
        command="/home/hatch/workspace/mandate-guard/.venv/bin/python",
        args=["mcp_server.py"],
        cwd="/home/hatch/workspace/mandate-guard",
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("discovered tools:", [t.name for t in tools.tools])
            for t in tools.tools:
                if t.name == "check_payment":
                    print("check_payment description:", t.description)
            res = await session.call_tool(
                "check_payment",
                {
                    "agent_id": "demo-agent",
                    "amount": 120,
                    "currency": "USD",
                    "vendor": "acme-cloud",
                    "purpose": "demo call",
                    "idempotency_key": "mcp-live-1",
                },
            )
            print("call result:", res.content[0].text[:200], "...")


asyncio.run(main())
