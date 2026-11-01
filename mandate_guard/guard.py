"""Core authorization: the agent proposes, the mandate decides.

Never moves money. Returns a signed verdict the counterparty can verify.
State lives in SQLite (mandate_guard/store.py) with automatic
daily/monthly spend rollover.
"""
from __future__ import annotations

import time
import uuid

from . import store
from . import verdicts

RETRY_WINDOW = 10  # last N decisions scanned for retry-gaming


def _fingerprint(agent_id: str, vendor: str, amount: float):
    # Normalize: retry-gaming = same intent with tiny tweaks
    return (agent_id, vendor.strip().lower(), round(float(amount), 0))


def authorize(
    agent_id: str,
    amount: float,
    currency: str,
    vendor: str,
    purpose: str = "",
    idempotency_key: str | None = None,
) -> dict:
    # 1. Idempotency: same key -> same decision, never double-authorizes
    if idempotency_key:
        prev = store.find_by_idempotency(idempotency_key)
        if prev:
            return {**prev, "replayed": True}

    mandate = store.get_mandate(agent_id)
    if not mandate:
        return _decide(agent_id, amount, currency, vendor, "denied",
                       "no mandate for agent", idempotency_key, purpose)

    # Retry-gaming: a denied fingerprint tried again with small tweaks.
    # Runs before the other policy checks so the repeat gets flagged
    # for what it is, instead of failing on a different rule.
    fp = _fingerprint(agent_id, vendor, amount)
    for r in store.recent_decisions(limit=RETRY_WINDOW):
        if (r["agent_id"] == agent_id and r["decision"] == "denied"
                and _fingerprint(r["agent_id"], r["vendor"], r["amount"]) == fp):
            return _decide(agent_id, amount, currency, vendor, "denied",
                           "retry-gaming: same denied intent with small changes",
                           idempotency_key, purpose)

    if currency != mandate.currency:
        return _decide(agent_id, amount, currency, vendor, "denied",
                       f"currency {currency} not covered (mandate: {mandate.currency})",
                       idempotency_key, purpose)

    if mandate.vendor_allowlist and vendor not in mandate.vendor_allowlist:
        return _decide(agent_id, amount, currency, vendor, "denied",
                       f"vendor '{vendor}' not in allowlist",
                       idempotency_key, purpose)

    if mandate.spent_today + amount > mandate.daily_cap:
        return _decide(agent_id, amount, currency, vendor, "denied",
                       f"daily cap {mandate.daily_cap} exceeded",
                       idempotency_key, purpose)

    if mandate.spent_month + amount > mandate.monthly_cap:
        return _decide(agent_id, amount, currency, vendor, "denied",
                       f"monthly cap {mandate.monthly_cap} exceeded",
                       idempotency_key, purpose)

    if amount > mandate.human_approval_above:
        return _decide(agent_id, amount, currency, vendor, "needs_human",
                       f"amount {amount} above human-approval threshold "
                       f"{mandate.human_approval_above}",
                       idempotency_key, purpose)

    # Allowed: record spend against the mandate
    store.record_spend(agent_id, amount)
    return _decide(agent_id, amount, currency, vendor, "allowed",
                   "within mandate", idempotency_key, purpose)


def _decide(agent_id, amount, currency, vendor, decision, reason,
            idempotency_key, purpose=""):
    token = verdicts.sign_verdict(
        agent_id=agent_id, amount=amount, currency=currency, vendor=vendor,
        decision=decision, reason=reason, idempotency_key=idempotency_key,
    )
    record = {
        "decision_id": str(uuid.uuid4()),
        "ts": int(time.time()),
        "agent_id": agent_id,
        "amount": amount,
        "currency": currency,
        "vendor": vendor,
        "purpose": purpose,
        "decision": decision,
        "reason": reason,
        "idempotency_key": idempotency_key,
        "verdict": token,
    }
    store.append_decision(record)
    return record
