"""Core authorization: the agent proposes, the mandate decides.

Never moves money. Returns a signed verdict the counterparty can verify.
State lives in SQLite (mandate_guard/store.py) with automatic
daily/monthly spend rollover.

Every decision also carries a `trace`: the ordered list of policy checks
that ran, each with a status (pass / deny / route / info) and a detail
string. The demo GUI renders this as the step-by-step timeline.
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


def _step(name: str, title: str, status: str, detail: str) -> dict:
    return {"name": name, "title": title, "status": status, "detail": detail}


def _evaluate(agent_id: str, amount: float, currency: str, vendor: str):
    """Pure policy evaluation, in check order. No writes.

    Returns (decision, reason, steps). `authorize()` applies the side
    effects (spend recording, decision logging, verdict signing).
    """
    steps: list[dict] = []

    mandate = store.get_mandate(agent_id)
    if not mandate:
        steps.append(_step("mandate", "Mandate lookup", "deny",
                           f"no mandate configured for agent '{agent_id}'"))
        return "denied", "no mandate for agent", steps
    steps.append(_step(
        "mandate", "Mandate lookup", "pass",
        f"daily_cap={mandate.daily_cap:g} monthly_cap={mandate.monthly_cap:g} "
        f"allowlist={mandate.vendor_allowlist or 'any'} "
        f"human_approval_above={mandate.human_approval_above:g} "
        f"{mandate.currency}"))

    # Retry-gaming: a denied fingerprint tried again with small tweaks.
    # Runs before the other policy checks so the repeat gets flagged
    # for what it is, instead of failing on a different rule.
    fp = _fingerprint(agent_id, vendor, amount)
    gaming = False
    for r in store.recent_decisions(limit=RETRY_WINDOW):
        if (r["agent_id"] == agent_id and r["decision"] == "denied"
                and _fingerprint(r["agent_id"], r["vendor"], r["amount"]) == fp):
            gaming = True
            break
    if gaming:
        steps.append(_step(
            "retry_gaming", "Retry-gaming scan", "deny",
            "same denied intent re-tried with small changes "
            f"(fingerprint {fp}) — blocked, not re-evaluated"))
        return ("denied",
                "retry-gaming: same denied intent with small changes", steps)
    steps.append(_step(
        "retry_gaming", "Retry-gaming scan", "pass",
        f"no repeat of a denied intent in the last {RETRY_WINDOW} decisions"))

    if currency != mandate.currency:
        steps.append(_step(
            "currency", "Currency check", "deny",
            f"request is {currency}, mandate covers {mandate.currency}"))
        return ("denied",
                f"currency {currency} not covered (mandate: {mandate.currency})",
                steps)
    steps.append(_step("currency", "Currency check", "pass",
                       f"{currency} == mandate currency {mandate.currency}"))

    if mandate.vendor_allowlist and vendor not in mandate.vendor_allowlist:
        steps.append(_step(
            "vendor_allowlist", "Vendor allowlist", "deny",
            f"'{vendor}' not in {mandate.vendor_allowlist}"))
        return "denied", f"vendor '{vendor}' not in allowlist", steps
    steps.append(_step(
        "vendor_allowlist", "Vendor allowlist", "pass",
        f"'{vendor}' is allowed"
        if mandate.vendor_allowlist else "no allowlist configured — any vendor"))

    if mandate.spent_today + amount > mandate.daily_cap:
        steps.append(_step(
            "daily_cap", "Daily cap", "deny",
            f"spent_today={mandate.spent_today:g} + {amount:g} > "
            f"daily_cap={mandate.daily_cap:g}"))
        return "denied", f"daily cap {mandate.daily_cap} exceeded", steps
    steps.append(_step(
        "daily_cap", "Daily cap", "pass",
        f"spent_today={mandate.spent_today:g} + {amount:g} <= "
        f"daily_cap={mandate.daily_cap:g}"))

    if mandate.spent_month + amount > mandate.monthly_cap:
        steps.append(_step(
            "monthly_cap", "Monthly cap", "deny",
            f"spent_month={mandate.spent_month:g} + {amount:g} > "
            f"monthly_cap={mandate.monthly_cap:g}"))
        return "denied", f"monthly cap {mandate.monthly_cap} exceeded", steps
    steps.append(_step(
        "monthly_cap", "Monthly cap", "pass",
        f"spent_month={mandate.spent_month:g} + {amount:g} <= "
        f"monthly_cap={mandate.monthly_cap:g}"))

    if amount > mandate.human_approval_above:
        steps.append(_step(
            "human_approval", "Human-approval threshold", "route",
            f"{amount:g} > {mandate.human_approval_above:g} — "
            "a person must approve, the agent cannot proceed alone"))
        return ("needs_human",
                f"amount {amount} above human-approval threshold "
                f"{mandate.human_approval_above}", steps)
    steps.append(_step(
        "human_approval", "Human-approval threshold", "pass",
        f"{amount:g} <= {mandate.human_approval_above:g} — no human needed"))

    return "allowed", "within mandate", steps


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
            steps = [_step(
                "idempotency", "Idempotency check", "info",
                f"key '{idempotency_key}' seen before → "
                f"replaying decision '{prev['decision']}', nothing re-authorized")]
            return {**prev, "replayed": True, "trace": steps}

    decision, reason, steps = _evaluate(agent_id, amount, currency, vendor)
    if idempotency_key:
        steps.insert(0, _step(
            "idempotency", "Idempotency check", "info",
            f"key '{idempotency_key}' not seen before → evaluating"))

    if decision == "allowed":
        # Allowed: record spend against the mandate
        store.record_spend(agent_id, amount)
    rec = _decide(agent_id, amount, currency, vendor, decision, reason,
                  idempotency_key, purpose)
    rec["trace"] = steps
    return rec


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
