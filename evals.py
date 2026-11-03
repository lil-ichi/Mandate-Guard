"""Evals: the three cases from the listing, plus idempotency and signatures.

Run: python evals.py
Also importable: from evals import run_evals  (used by the demo GUI)
"""
from mandate_guard import guard, store, verdicts


def run_evals() -> list[dict]:
    """Run all evals on a clean slate. Returns [{name, passed, detail}]."""
    store.reset()  # clears spend + decisions; mandates (incl. demo-agent) survive
    results: list[dict] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append({"name": name, "passed": bool(cond), "detail": detail})

    r = guard.authorize("demo-agent", 120, "USD", "acme-cloud",
                        idempotency_key="e1")
    check("E1 allowed payment passes", r["decision"] == "allowed",
          f"decision={r['decision']} — a payment inside the mandate is allowed and signed")

    r = guard.authorize("demo-agent", 50, "USD", "evil-vendor",
                        idempotency_key="e2")
    check("E2 denied vendor -> agent must stop", r["decision"] == "denied",
          f"decision={r['decision']} — vendor outside the allowlist is denied")

    r = guard.authorize("demo-agent", 49.99, "USD", "evil-vendor",
                        idempotency_key="e3")
    check("E3 retry-gaming blocked",
          r["decision"] == "denied" and "retry-gaming" in r["reason"],
          "same denied intent with a tweaked amount ($50 -> $49.99) is blocked, not re-evaluated")

    r = guard.authorize("demo-agent", 900, "USD", "acme-cloud",
                        idempotency_key="e4")
    check("E4 above threshold -> needs_human", r["decision"] == "needs_human",
          f"decision={r['decision']} — $900 above the $500 threshold routes to a person, not denied")

    r1 = guard.authorize("demo-agent", 120, "USD", "acme-cloud",
                         idempotency_key="e5")
    r2 = guard.authorize("demo-agent", 120, "USD", "acme-cloud",
                         idempotency_key="e5")
    check("E5 idempotency: same key -> same decision, no double spend",
          bool(r2.get("replayed")) and r2["decision_id"] == r1["decision_id"],
          "second call replays decision_id " + r1["decision_id"][:8] + "… — spend recorded once")

    r = guard.authorize("demo-agent", 10, "USD", "acme-cloud",
                        idempotency_key="e6")
    try:
        claims = verdicts.verify_verdict(r["verdict"])
        sig_ok = (claims["decision"] == r["decision"]
                  and claims["iss"] == "mandate-guard")
        detail = "ES256 signature verifies against the published key (kid=dev-1)"
    except Exception as e:  # noqa: BLE001
        sig_ok = False
        detail = f"verify failed: {e}"
    check("E6 verdict signature verifies (ES256)", sig_ok, detail)

    return results


if __name__ == "__main__":
    results = run_evals()
    for res in results:
        print(("PASS " if res["passed"] else "FAIL ") + res["name"])
    passed = sum(1 for res in results if res["passed"])
    print(f"\n{passed}/{len(results)} evals passed")
    raise SystemExit(0 if passed == len(results) else 1)
