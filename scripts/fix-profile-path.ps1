$ErrorActionPreference = 'Stop'
Start-Transcript -Path "$env:TEMP\neuron-profile-fix.log" -Append | Out-Null
try {
    Write-Host 'Waiting for DSH to close (exit the app completely)...'
    $waited = 0
    while (Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue) {
        Start-Sleep -Seconds 2
        $waited += 2
        if ($waited % 10 -eq 0) { Write-Host "still running... ${waited}s" }
    }
    Start-Sleep -Seconds 2
    $root = Split-Path -Parent $MyInvocation.MyCommand.Path
    $py = Join-Path (Split-Path -Parent $root) '.venv\Scripts\python.exe'
    if (-not (Test-Path $py)) { throw "python not found: $py" }
    Write-Host 'Repairing profile package.json...'
    & $py (Join-Path $root 'fix_profile_path.py')
    if ($LASTEXITCODE -ne 0) { throw "repair exited with $LASTEXITCODE" }
    Write-Host ''
    Write-Host 'Done. Start DSH again, then ask the agent to verify.'
} catch {
    Write-Host ''
    Write-Host ('FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ('Log: ' + "$env:TEMP\neuron-profile-fix.log")
} finally {
    Stop-Transcript | Out-Null
    Start-Sleep -Seconds 4
}
