@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo TribalSetu Python environment was not found at .venv\Scripts\python.exe
  echo From this folder, run: py -m venv .venv
  echo Then run: .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

powershell.exe -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -TimeoutSec 2 -UseBasicParsing; if ($r.Content -match 'TribalSetu') { exit 0 } } catch {}; exit 1" >nul 2>&1
if not errorlevel 1 goto open_app

start "TribalSetu Local Server" "%ComSpec%" /k ""%PYTHON%" -m uvicorn server:app --host 127.0.0.1 --port 8000"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ready = $false; for ($i = 0; $i -lt 40 -and -not $ready; $i++) { try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -TimeoutSec 2 -UseBasicParsing; if ($r.StatusCode -eq 200 -and $r.Content -match 'TribalSetu') { $ready = $true } } catch {}; if (-not $ready) { Start-Sleep -Milliseconds 500 } }; if ($ready) { Start-Process 'http://127.0.0.1:8000/'; exit 0 }; exit 1"
if errorlevel 1 (
  echo The local server did not become ready. Check the TribalSetu server window for errors.
  pause
  exit /b 1
)
goto end

:open_app
start "" "http://127.0.0.1:8000/"

:end
endlocal
