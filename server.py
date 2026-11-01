"""REST API for mandate-guard."""
from fastapi import FastAPI
from pydantic import BaseModel

from mandate_guard import guard, store, verdicts
from mandate_guard.store import Mandate

app = FastAPI(title="mandate-guard", version="0.1.0")


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


@app.post("/v1/mandates")
def upsert_mandate(body: MandateIn):
    store.upsert_mandate(Mandate(**body.model_dump()))
    return {"ok": True}
