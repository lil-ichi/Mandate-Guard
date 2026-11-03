@echo off
REM mandate-guard one-shot starter (Windows)
REM Starts guard :8123, merchant :8124, MCP server :8130, opens the demo page.
cd /d "%~dp0"

echo [1/4] checking dependencies...
python -c "import fastapi, uvicorn, jwt, mcp" 2>nul
if errorlevel 1 (
    echo installing requirements...
    pip install -r requirements.txt
)

echo [2/4] checking keys...
if not exist keys\es256-private.pem (
    echo generating dev keypair...
    python setup_keys.py
)

echo [3/4] starting servers...
start "mandate-guard" python -m uvicorn server:app --port 8123
start "merchant" python merchant.py
start "mcp-server" python mcp_server.py --transport http --port 8130

echo [4/4] opening demo...
timeout /t 5 /nobreak >nul
start http://127.0.0.1:8123/

echo.
echo Demo running at http://127.0.0.1:8123/
echo Close the three server windows or run stop.bat to stop.
pause
