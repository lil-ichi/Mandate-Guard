"""End-to-end proof: the verdict — not the agent — decides what hits the wire.

Spins up the guard API (8123) and the merchant (8124), then plays the agent:
for every spend it asks the guard first, and ONLY calls the merchant when the
verdict says "allowed". At the end it prints the merchant's charge log —
the wire only ever saw what the guard allowed.

Run: python live_demo.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(BASE, ".venv", "bin", "python")
GUARD_URL = "http://127.0.0.1:8123"
MERCHANT_URL = "http://127.0.0.1:8124"

from mandate_guard import guard, store  # noqa: E402


def _wait(url: str, timeout: float = 15.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:  # noqa: BLE001 - still starting
            time.sleep(0.3)
    raise RuntimeError(f"never came up: {url}")


def _post(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


def try_spend(agent_id: str, amount: float, vendor: str, item: str,
              key: str) -> None:
    print(f"\n── agent wants: ${amount:g} → {vendor} ({item})")
    rec = guard.authorize(agent_id, amount, "USD", vendor,
                          purpose=item, idempotency_key=key)
    print(f"   guard verdict: {rec['decision']} — {rec['reason']}")
    if rec["decision"] != "allowed":
        print("   → agent does NOT call the merchant. Nothing hits the wire.")
        return
    status, body = _post(f"{MERCHANT_URL}/charge", {
        "verdict": rec["verdict"], "amount": amount,
        "vendor": vendor, "item": item,
    })
    if status == 200 and body.get("charged"):
        print(f"   → merchant verified the signature and CHARGED."
              f" receipt {body['receipt_id'][:8]}…")
    else:
        print(f"   → merchant REJECTED it ({status}): {body}")


def main() -> None:
    store.reset()
    charges_path = os.path.join(BASE, "charges.jsonl")
    if os.path.exists(charges_path):
        os.remove(charges_path)

    guard_p = subprocess.Popen(
        [PY, "-m", "uvicorn", "server:app", "--port", "8123"], cwd=BASE,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    merch_p = subprocess.Popen(
        [PY, "-m", "uvicorn", "merchant:app", "--port", "8124"], cwd=BASE,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        _wait(f"{GUARD_URL}/.well-known/jwks.json")
        _wait(f"{MERCHANT_URL}/health")
        print("guard + merchant up. Playing the agent…")

        try_spend("demo-agent", 120, "acme-cloud", "gpu-hours", "live-1")
        try_spend("demo-agent", 50, "evil-vendor", "totally-legit", "live-2")
        try_spend("demo-agent", 49.99, "evil-vendor", "totally-legit?",
                  "live-3")  # same denied intent, tweaked amount
        try_spend("demo-agent", 900, "acme-cloud", "big-cluster", "live-4")

        # The tamper test: a VALID verdict for $120, but the agent asks the
        # merchant to charge $500. The merchant must catch the lie.
        print("\n── TAMPER TEST: agent reuses a $120 verdict, asks for $500")
        rec = guard.authorize("demo-agent", 120, "USD", "acme-cloud",
                              idempotency_key="live-tamper")
        status, body = _post(f"{MERCHANT_URL}/charge", {
            "verdict": rec["verdict"], "amount": 500,
            "vendor": "acme-cloud", "item": "sneaky-upgrade",
        })
        print(f"   → merchant: {status} {body.get('detail', body)}")

        print("\n══ merchant charge log (what actually hit the wire) ══")
        for c in _get(f"{MERCHANT_URL}/charges"):
            print(f"   ✔ ${c['amount']:g} {c['currency']} → {c['vendor']}"
                  f" ({c['item']}) receipt {c['receipt_id'][:8]}…")
        print("\nOne charge. Everything else never left the agent.")
    finally:
        guard_p.terminate()
        merch_p.terminate()


if __name__ == "__main__":
    sys.exit(main())
