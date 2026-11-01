"""Evals: the three cases from the listing, plus idempotency and signatures."""
from mandate_guard import guard, store, verdicts


def reset() -> None:
    store.reset()  # clears spend + decisions; mandates (incl. demo-agent) survive


results: list = []


def check(name: str, cond: bool) -> None:
    results.append((name, cond))
    print(("PASS " if cond else "FAIL ") + name)


reset()

r = guard.authorize("demo-agent", 120, "USD", "acme-cloud", idempotency_key="e1")
check("E1 allowed payment passes", r["decision"] == "allowed")

r = guard.authorize("demo-agent", 50, "USD", "evil-vendor", idempotency_key="e2")
check("E2 denied vendor -> agent must stop", r["decision"] == "denied")

r = guard.authorize("demo-agent", 49.99, "USD", "evil-vendor", idempotency_key="e3")
check("E3 retry-gaming blocked",
      r["decision"] == "denied" and "retry-gaming" in r["reason"])

r = guard.authorize("demo-agent", 900, "USD", "acme-cloud", idempotency_key="e4")
check("E4 above threshold -> needs_human", r["decision"] == "needs_human")

r1 = guard.authorize("demo-agent", 120, "USD", "acme-cloud", idempotency_key="e5")
r2 = guard.authorize("demo-agent", 120, "USD", "acme-cloud", idempotency_key="e5")
check("E5 idempotency: same key -> same decision, no double spend",
      bool(r2.get("replayed")) and r2["decision_id"] == r1["decision_id"])

r = guard.authorize("demo-agent", 10, "USD", "acme-cloud", idempotency_key="e6")
try:
    claims = verdicts.verify_verdict(r["verdict"])
    sig_ok = claims["decision"] == r["decision"] and claims["iss"] == "mandate-guard"
except Exception:  # noqa: BLE001
    sig_ok = False
check("E6 verdict signature verifies (ES256)", sig_ok)

passed = sum(1 for _, c in results if c)
print(f"\n{passed}/{len(results)} evals passed")
raise SystemExit(0 if passed == len(results) else 1)
