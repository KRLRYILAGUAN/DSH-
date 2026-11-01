param([switch]$NoBrowser)
# Start the neuron-memory viewer (if needed) and optionally open it.
# Pure ASCII on purpose: Chinese literals in .cmd/.ps1 get mangled by the
# console code page. Paths are derived from this script's location.

$root = Split-Path -Parent $PSScriptRoot
$db = Join-Path (Split-Path -Parent $root) '.neuron-memory\neuron.db'
$py = Join-Path $root '.venv\Scripts\pythonw.exe'
$url = 'http://127.0.0.1:8420/'

$up = $false
try {
  $r = Invoke-WebRequest -Uri ($url + 'api/health') -UseBasicParsing -TimeoutSec 2
  $up = ($r.StatusCode -eq 200)
} catch { $up = $false }

if (-not $up) {
  if (Test-Path $py) {
    Start-Process -FilePath $py -ArgumentList @('-m', 'viewer.server', '--db', $db, '--port', '8420') -WorkingDirectory $root -WindowStyle Hidden
  } else {
    Start-Process -FilePath 'python' -ArgumentList @('-m', 'viewer.server', '--db', $db, '--port', '8420') -WorkingDirectory $root -WindowStyle Hidden
  }
  Start-Sleep -Seconds 2
}

if (-not $NoBrowser) {
  Start-Process $url
}
