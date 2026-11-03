#!/bin/bash
# Stop all mandate-guard demo servers (macOS/Linux)
pkill -f "uvicorn server:app" 2>/dev/null
pkill -f "merchant.py" 2>/dev/null
pkill -f "mcp_server.py" 2>/dev/null
echo "All demo servers stopped."
