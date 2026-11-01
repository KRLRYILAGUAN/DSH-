$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$port = 8420

$up = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/graph" -UseBasicParsing -TimeoutSec 2
    $up = ($r.StatusCode -eq 200)
} catch { $up = $false }

if (-not $up) {
    Start-Process -FilePath $py -ArgumentList @("-m", "viewer.server", "--db", "data/neuron.db", "--port", "$port") -WorkingDirectory $root -WindowStyle Minimized
    Start-Sleep -Seconds 2
}

$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (Test-Path $edge) {
    Start-Process $edge "--app=http://127.0.0.1:$port/"
} else {
    Start-Process "http://127.0.0.1:$port/"
}
