#!/bin/bash
# mandate-guard one-shot starter (macOS/Linux)
# Starts guard :8123, merchant :8124, MCP server :8130, opens the demo page.
cd "$(dirname "$0")"

echo "[1/4] checking dependencies..."
python3 -c "import fastapi, uvicorn, jwt, mcp" 2>/dev/null || pip install -r requirements.txt

echo "[2/4] checking keys..."
[ -f keys/es256-private.pem ] || python3 setup_keys.py

echo "[3/4] starting servers..."
python3 -m uvicorn server:app --port 8123 &
python3 merchant.py &
python3 mcp_server.py --transport http --port 8130 &

echo "[4/4] opening demo..."
sleep 4
(xdg-open http://127.0.0.1:8123/ 2>/dev/null || open http://127.0.0.1:8123/ 2>/dev/null) &

echo ""
echo "Demo running at http://127.0.0.1:8123/  (run ./stop.sh to stop)"
wait
