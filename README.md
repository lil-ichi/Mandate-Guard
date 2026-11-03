# mandate-guard

An authorization layer for AI-agent payments — a working miniature of the
idea Saifuro is built on.

The agent **proposes**, the **mandate** decides, and the guard returns a
**signed verdict** (ES256 JWT) the counterparty can verify. The guard never
moves money and never holds keys. The payment itself happens in your own
systems, through your own providers.

## What it does

- `POST /v1/check` — check a proposed payment against the agent's mandate
- `GET /.well-known/jwks.json` — published keys, so anyone can verify verdicts
- `GET /v1/decisions` — append-only audit log of every verdict
- `POST /v1/mandates` — upsert a mandate (caps, allowlist, human-approval threshold)
- MCP server (`mcp_server.py`) — `check_payment` tool any MCP client can call,
  over stdio or streamable HTTP (`--transport http --port 8130`)
- `agent_demo.py` — a demo agent that proposes payments and obeys the guard
- `live_demo.py` — **end-to-end proof**: spins up the guard + a demo merchant;
  the merchant fetches the guard's JWKS, verifies each verdict's signature and
  claims, and only then records the charge. Includes a tamper test where the
  agent lies about the amount and the merchant rejects it.
- `merchant.py` — the counterparty: charges only on a valid `allowed` verdict
- `evals.py` — the three eval cases: denied payment, human escalation, retry-gaming
- SQLite store (`mandate_guard/store.py`) — mandates, spend counters with
  automatic daily/monthly rollover, and the decision log survive restarts

## Decisions

- `allowed` — within mandate, verdict signed
- `denied` — vendor not allowlisted, cap exceeded, or retry-gaming detected
- `needs_human` — amount above the human-approval threshold; the agent must ask a person

Plus: idempotency keys (same key → same decision, never double-authorizes),
retry-gaming detection (same denied intent with tiny tweaks gets blocked),
and every decision written to an append-only JSONL log.

## Live demo GUI

The fastest way to see it — an interactive page with the mandate, a
"propose a payment" form, the step-by-step check trace for every verdict,
five scripted scenarios (including the tamper test), and the merchant's
charge log:

```bash
pip install -r requirements.txt
python -m uvicorn server:app --port 8123   # terminal 1: the guard + demo page
python merchant.py                          # terminal 2: the merchant (port 8124)
# open http://127.0.0.1:8123  →  click "▶ Run full story"
```

Every `/v1/check` response now also carries a `trace`: the ordered policy
checks (idempotency → mandate → retry-gaming → currency → allowlist →
daily/monthly caps → human threshold), each with pass/deny/route/info and a
detail string. The GUI renders it as a timeline.

## Quickstart

```bash
pip install -r requirements.txt
python setup_keys.py        # dev ES256 keypair (keys/ is gitignored)
python evals.py             # 6/6 evals should pass
python agent_demo.py        # watch the agent obey the guard
python live_demo.py         # end-to-end: guard + merchant, tamper test included
uvicorn server:app --port 8123          # REST API
python mcp_server.py                    # MCP server over stdio
python mcp_server.py --transport http   # MCP over streamable HTTP :8130
```

## Architecture

```
agent proposes payment
        |
        v
  POST /v1/check  (or MCP check_payment tool)
        |
        v
  mandate lookup -> policy checks -> signed verdict (ES256 JWT)
        |
        v
  append-only log + verdict returned
        |
        v
  YOUR system pays (or doesn't) via YOUR provider
```

## Mapping to Saifuro's concepts

| mandate-guard | Saifuro |
|---|---|
| mandate (caps, allowlist, approval threshold) | mandate |
| signed verdict (ES256 JWT) | signed verdict (ES256 JWT) |
| `/.well-known/jwks.json` | published keys |
| append-only `decisions.jsonl` | append-only decision log |
| guard never moves money | authorization, not a PSP |
| evals: denied / human / retry-gaming | evals in the job listing |
| MCP `check_payment` tool | MCP server in the job listing |

## Interview demo script (60 seconds)

1. "The agent proposes, the mandate decides." Run `live_demo.py`:
   `$120 to acme-cloud → allowed` → the merchant **verifies the signature
   via JWKS and charges**; `$50 to evil-vendor → denied`, `$49.99 retry →
   denied (retry-gaming)`, `$900 → needs_human` — none of them touch the wire.
2. The tamper test: the agent reuses a valid $120 verdict but asks for $500 —
   the merchant answers **402 amount mismatch**. "Even if the agent lies,
   the counterparty catches it."
3. Show the merchant charge log: exactly one charge. "The wire only saw
   what the guard allowed."
4. Show `evals.py`: 6/6 pass — "these are the three eval cases from your listing."
5. "The MCP tool returns the verdict, not money. Any MCP client can call it —
   stdio locally, streamable HTTP for remote clients like Claude or Cursor."

## Honest production gaps

- Dev keys (no rotation, no HSM); single process, SQLite (no real DB cluster)
- No escrow / on-chain settlement, no protocol adapters (x402 etc.),
  no metering/billing — the authorization core is what's modeled here
