"""Demo merchant: the counterparty side.

Only charges when the guard's signed verdict checks out:
  1. Fetches the guard's public keys over HTTP via JWKS (the real
     discovery path — no shared secrets, no key files copied around).
  2. Verifies the ES256 signature.
  3. Checks the claims: decision == "allowed", amount and vendor match
     what the agent is actually asking to pay, verdict not expired.

Anything else -> rejected, nothing charged. This is the whole point:
even if the agent lies, the merchant catches it.

Run: python merchant.py  (port 8124)
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.request
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE = os.path.dirname(__file__)
CHARGES_PATH = os.path.join(BASE, "charges.jsonl")
GUARD_URL = os.environ.get("GUARD_URL", "http://127.0.0.1:8123")

app = FastAPI(title="demo-merchant", version="0.1.0")

# Local demo page (served from the guard on :8123) calls this merchant
# cross-origin in the browser — allow it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_jwks_cache: dict = {"at": 0.0, "keys": []}


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _jwk_to_pem(jwk: dict) -> bytes:
    nums = ec.EllipticCurvePublicNumbers(
        int.from_bytes(_b64d(jwk["x"]), "big"),
        int.from_bytes(_b64d(jwk["y"]), "big"),
        ec.SECP256R1(),
    )
    return nums.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _jwks() -> list[dict]:
    if time.time() - _jwks_cache["at"] < 60 and _jwks_cache["keys"]:
        return _jwks_cache["keys"]
    with urllib.request.urlopen(
        f"{GUARD_URL}/.well-known/jwks.json", timeout=5
    ) as r:
        keys = json.load(r)["keys"]
    _jwks_cache.update(at=time.time(), keys=keys)
    return keys


def verify_verdict(token: str) -> dict:
    header = jwt.get_unverified_header(token)
    for jwk in _jwks():
        if jwk.get("kid") == header.get("kid"):
            return jwt.decode(
                token,
                _jwk_to_pem(jwk),
                algorithms=["ES256"],
                issuer="mandate-guard",
            )
    raise jwt.InvalidTokenError("no matching key id")


class ChargeIn(BaseModel):
    verdict: str
    amount: float
    vendor: str
    item: str = ""


def _read_charges() -> list[dict]:
    if not os.path.exists(CHARGES_PATH):
        return []
    with open(CHARGES_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/charges")
def charges():
    return _read_charges()


@app.post("/charge")
def charge(body: ChargeIn):
    try:
        claims = verify_verdict(body.verdict)
    except Exception as e:  # noqa: BLE001 - surfaced as the rejection reason
        raise HTTPException(status_code=402, detail=f"bad verdict: {e}")

    if claims.get("decision") != "allowed":
        raise HTTPException(
            status_code=402,
            detail=f"verdict decision is '{claims.get('decision')}', not allowed",
        )
    if abs(float(claims.get("amount", -1)) - body.amount) > 1e-9:
        raise HTTPException(
            status_code=402,
            detail=f"amount mismatch: verdict says {claims.get('amount')},"
                   f" charge asks {body.amount}",
        )
    if claims.get("vendor") != body.vendor:
        raise HTTPException(
            status_code=402,
            detail=f"vendor mismatch: verdict says {claims.get('vendor')},"
                   f" charge asks {body.vendor}",
        )

    receipt = {
        "receipt_id": str(uuid.uuid4()),
        "ts": int(time.time()),
        "agent_id": claims.get("agent_id"),
        "amount": body.amount,
        "currency": claims.get("currency", "USD"),
        "vendor": body.vendor,
        "item": body.item,
        "verdict_jti": claims.get("jti"),
    }
    with open(CHARGES_PATH, "a") as f:
        f.write(json.dumps(receipt) + "\n")
    return {"charged": True, **receipt}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8124)
