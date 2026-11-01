"""MCP server: any MCP client can call the payment check.

The tool returns the signed verdict — never moves money.

Run:  python mcp_server.py                      (stdio, for local clients)
      python mcp_server.py --transport http      (streamable HTTP :8130,
                                                 for Claude/Cursor/etc.)
"""
import argparse

from mcp.server.mcpserver import MCPServer

from mandate_guard import guard, verdicts

mcp = MCPServer("mandate-guard")


@mcp.tool()
def check_payment(
    agent_id: str,
    amount: float,
    currency: str,
    vendor: str,
    purpose: str = "",
    idempotency_key: str = "",
) -> dict:
    """Check a proposed agent payment against its mandate.

    Returns allowed/denied/needs_human plus the signed ES256 verdict JWT.
    This tool never moves money — the caller's own system pays.
    """
    rec = guard.authorize(
        agent_id=agent_id,
        amount=amount,
        currency=currency,
        vendor=vendor,
        purpose=purpose,
        idempotency_key=idempotency_key or None,
    )
    return {
        "decision": rec["decision"],
        "reason": rec["reason"],
        "verdict": rec["verdict"],
        "decision_id": rec["decision_id"],
    }


@mcp.tool()
def verify_verdict(verdict: str) -> dict:
    """Verify a signed verdict against the published keys."""
    try:
        return {"valid": True, "claims": verdicts.verify_verdict(verdict)}
    except Exception as e:  # noqa: BLE001 - surfaced to the MCP client
        return {"valid": False, "error": str(e)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    p.add_argument("--port", type=int, default=8130)
    args = p.parse_args()
    if args.transport == "http":
        mcp.run(transport="streamable-http", port=args.port)
    else:
        mcp.run()
