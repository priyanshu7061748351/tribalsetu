@echo off
title TribalSetu - Live Public Tunnel (Cloudflare)
cd /d "%~dp0"
echo ========================================================
echo   TribalSetu 2026 - Live Cloudflare Public Tunnel
echo ========================================================
echo.
if not exist "cloudflared.exe" (
    echo Downloading Cloudflare Tunnel engine...
    curl.exe -L -o "cloudflared.exe" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
)
echo Starting Cloudflare HTTPS Tunnel to localhost:8000...
echo Keep this window open while sharing your link!
echo.
.\cloudflared.exe tunnel --url http://127.0.0.1:8000
pause
