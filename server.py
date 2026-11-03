"""REST API for mandate-guard.

Serves the interactive demo GUI at `/` (demo.html) alongside the API.
"""
import os
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from mandate_guard import guard, store, verdicts
from mandate_guard.store import Mandate

BASE = os.path.dirname(os.path.abspath(__file__))
CHARGES_PATH = os.path.join(BASE, "charges.jsonl")

app = FastAPI(title="mandate-guard", version="0.1.0")


@app.get("/", include_in_schema=False)
def demo_page():
    return FileResponse(os.path.join(BASE, "demo.html"))


class CheckIn(BaseModel):
    agent_id: str
    amount: float
    currency: str = "USD"
    vendor: str
    purpose: str = ""
    idempotency_key: str | None = None


class MandateIn(BaseModel):
    agent_id: str
    daily_cap: float
    monthly_cap: float
    currency: str = "USD"
    vendor_allowlist: list[str] = []
    human_approval_above: float = 500.0


@app.post("/v1/check")
def check(body: CheckIn):
    return guard.authorize(**body.model_dump())


@app.get("/.well-known/jwks.json")
def jwks():
    return verdicts.jwks()


@app.get("/v1/decisions")
def decisions(limit: int = 50):
    return store.recent_decisions(limit=limit)


@app.get("/v1/mandates/{agent_id}")
def get_mandate(agent_id: str):
    m = store.get_mandate(agent_id)
    if not m:
        raise HTTPException(status_code=404, detail="no mandate for agent")
    return asdict(m)


@app.post("/v1/demo/reset")
def demo_reset():
    """Clean slate for demos: clears spend + decisions, keeps mandates."""
    store.reset()
    if os.path.exists(CHARGES_PATH):
        os.remove(CHARGES_PATH)
    return {"ok": True}


@app.post("/v1/demo/evals")
def demo_evals():
    """Run the eval suite live (resets demo spend first, like CI)."""
    import evals as evals_mod
    results = evals_mod.run_evals()
    return {
        "results": results,
        "passed": sum(1 for r in results if r["passed"]),
        "total": len(results),
    }


class McpCheckIn(BaseModel):
    agent_id: str = "demo-agent"
    amount: float = 45.0
    currency: str = "USD"
    vendor: str = "acme-cloud"
    purpose: str = ""
    idempotency_key: str | None = None


MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8130/mcp")


def _mcp_call(tool: str, args: dict):
    """Real MCP client call over streamable HTTP (like Claude/Cursor)."""
    import asyncio
    import json

    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def _run():
        async with streamable_http_client(MCP_URL) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                if tool == "__list__":
                    tools = await s.list_tools()
                    return [t.name for t in tools.tools]
                res = await s.call_tool(tool, args)
                return json.loads(res.content[0].text)

    return asyncio.run(_run())


@app.get("/v1/demo/mcp-status")
def demo_mcp_status():
    """Read-only probe: is the MCP server up, which tools does it expose?"""
    try:
        tools = _mcp_call("__list__", {})
        return {"ok": True, "url": MCP_URL, "tools": tools}
    except Exception as e:  # noqa: BLE001 - surfaced as the hint
        raise HTTPException(
            status_code=502,
            detail="MCP server not reachable at " + MCP_URL
                   + " — start it with: python mcp_server.py --transport http --port 8130"
                   + f" ({e})",
        )


@app.post("/v1/demo/mcp-check")
def demo_mcp_check(body: McpCheckIn):
    """Call check_payment through the MCP protocol (not the REST API)."""
    try:
        out = _mcp_call("check_payment", {
            "agent_id": body.agent_id,
            "amount": body.amount,
            "currency": body.currency,
            "vendor": body.vendor,
            "purpose": body.purpose,
            "idempotency_key": body.idempotency_key or "",
        })
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail="MCP server not reachable at " + MCP_URL
                   + " — start it with: python mcp_server.py --transport http --port 8130"
                   + f" ({e})",
        )
    return {"via": "mcp/streamable-http", "tool": "check_payment", "result": out}


@app.post("/v1/mandates")
def upsert_mandate(body: MandateIn):
    store.upsert_mandate(Mandate(**body.model_dump()))
    return {"ok": True}
