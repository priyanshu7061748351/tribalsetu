$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$buildId = 'screening-v1'
$candidatePorts = @(8000, 8001, 8002)

if (-not (Test-Path -LiteralPath $pythonPath)) {
  Write-Host 'TribalSetu Python environment not found.' -ForegroundColor Red
  Write-Host 'Run: py -m venv .venv'
  Write-Host 'Then: .venv\Scripts\python.exe -m pip install -r requirements.txt'
  exit 1
}

foreach ($port in $candidatePorts) {
  try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 1
    if ($health.service -eq 'tribalsetu-local' -and $health.build -eq $buildId) {
      Start-Process "http://127.0.0.1:$port/"
      Write-Host "TribalSetu is already running at http://127.0.0.1:$port/"
      exit 0
    }
  } catch {}
}

$selectedPort = $null
foreach ($port in $candidatePorts) {
  $listener = $null
  try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    $listener.Start()
    $listener.Stop()
    $selectedPort = $port
    break
  } catch {
    if ($listener) { $listener.Stop() }
  }
}

if (-not $selectedPort) {
  Write-Host 'Ports 8000–8002 are busy. Close an older local server, then run this launcher again.' -ForegroundColor Red
  exit 1
}

$serverArguments = @('-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', "$selectedPort")
$serverProcess = Start-Process -FilePath $pythonPath -ArgumentList $serverArguments -WorkingDirectory $projectRoot -PassThru -WindowStyle Normal
$appUrl = "http://127.0.0.1:$selectedPort/"
$ready = $false

for ($attempt = 0; $attempt -lt 60 -and -not $ready; $attempt++) {
  try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$selectedPort/api/health" -TimeoutSec 2
    $ready = $health.service -eq 'tribalsetu-local' -and $health.build -eq $buildId
  } catch {}
  if (-not $ready) {
    $runningProcess = Get-Process -Id $serverProcess.Id -ErrorAction SilentlyContinue
    if (-not $runningProcess) { break }
    Start-Sleep -Milliseconds 500
  }
}

if (-not $ready) {
  Write-Host 'The TribalSetu server did not become ready. Check its console window for startup errors.' -ForegroundColor Red
  exit 1
}

Start-Process $appUrl
Write-Host "TribalSetu is ready at $appUrl"
Write-Host 'Keep the server console window open while using the app.'
