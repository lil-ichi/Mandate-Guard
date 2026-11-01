"""ES256 signed verdicts.

Mirrors the design: the verdict is a JWT the counterparty can verify
against published keys. The guard never moves money.
"""
from __future__ import annotations

import base64
import os
import time
import uuid

import jwt
from cryptography.hazmat.primitives import serialization

BASE = os.path.dirname(os.path.dirname(__file__))
PRIV_PATH = os.path.join(BASE, "keys", "es256-private.pem")
PUB_PATH = os.path.join(BASE, "keys", "es256-public.pem")
KID = "dev-1"
ISSUER = "mandate-guard"


def _b64u(n: int, length: int) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()


def public_jwk() -> dict:
    with open(PUB_PATH, "rb") as f:
        pub = serialization.load_pem_public_key(f.read())
    nums = pub.public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "use": "sig",
        "alg": "ES256",
        "kid": KID,
        "x": _b64u(nums.x, 32),
        "y": _b64u(nums.y, 32),
    }


def jwks() -> dict:
    return {"keys": [public_jwk()]}


def sign_verdict(
    *,
    agent_id: str,
    amount: float,
    currency: str,
    vendor: str,
    decision: str,
    reason: str,
    idempotency_key: str | None = None,
    ttl: int = 300,
) -> str:
    now = int(time.time())
    payload = {
        "iss": ISSUER,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + ttl,
        "agent_id": agent_id,
        "amount": amount,
        "currency": currency,
        "vendor": vendor,
        "decision": decision,
        "reason": reason,
    }
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    with open(PRIV_PATH) as f:
        priv_pem = f.read()
    return jwt.encode(payload, priv_pem, algorithm="ES256", headers={"kid": KID})


def verify_verdict(token: str) -> dict:
    with open(PUB_PATH) as f:
        pub_pem = f.read()
    return jwt.decode(
        token,
        pub_pem,
        algorithms=["ES256"],
        issuer=ISSUER,
        options={"require": ["exp", "iss", "jti"]},
    )

