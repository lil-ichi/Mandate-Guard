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


@app.post("/v1/mandates")
def upsert_mandate(body: MandateIn):
    store.upsert_mandate(Mandate(**body.model_dump()))
    return {"ok": True}
