@echo off
REM Stop all mandate-guard demo servers (Windows)
taskkill /F /FI "WINDOWTITLE eq mandate-guard" 2>nul
taskkill /F /FI "WINDOWTITLE eq merchant" 2>nul
taskkill /F /FI "WINDOWTITLE eq mcp-server" 2>nul
echo All demo servers stopped.
