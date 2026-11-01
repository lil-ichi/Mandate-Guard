"""Demo agent: proposes payments and obeys the guard.

No real money, no LLM API key needed — the point is the authorization
boundary, not the model.
"""
from mandate_guard import guard, store, verdicts

SCENARIO = [
    # (agent_id, amount, currency, vendor, purpose, idempotency_key)
    ("demo-agent", 120, "USD", "acme-cloud", "monthly API bill", "demo-1"),
    ("demo-agent", 900, "USD", "acme-cloud", "GPU cluster", "demo-2"),
    ("demo-agent", 50, "USD", "evil-vendor", "mystery service", "demo-3"),
    ("demo-agent", 49.99, "USD", "evil-vendor", "mystery service", "demo-4"),  # retry-gaming
    ("demo-agent", 120, "USD", "acme-cloud", "monthly API bill", "demo-1"),  # idempotent replay
]


def main() -> None:
    # Fresh run: clear spend + decisions so the demo is deterministic
    store.reset()

    for agent_id, amount, cur, vendor, purpose, key in SCENARIO:
        rec = guard.authorize(agent_id, amount, cur, vendor, purpose, idempotency_key=key)
        claims = verdicts.verify_verdict(rec["verdict"])
        assert claims["decision"] == rec["decision"], "signature mismatch!"
        tag = "REPLAY" if rec.get("replayed") else "NEW"
        print(f"[{tag}] ${amount:g} -> {vendor}: {rec['decision']} ({rec['reason']})")
        if rec["decision"] == "allowed":
            print("   agent: verdict verified, paying via my own provider...")
        elif rec["decision"] == "needs_human":
            print("   agent: pausing, asking a human for approval.")
        else:
            print("   agent: stopping. No retry.")


if __name__ == "__main__":
    main()
