# Remove viewer shortcuts and stop the viewer process.
# The plugin package itself is removed by DSH's uninstall.
# Data is kept unless -PurgeData is passed.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File uninstall-viewer.ps1
#   powershell -ExecutionPolicy Bypass -File uninstall-viewer.ps1 -PurgeData
#   powershell -ExecutionPolicy Bypass -File uninstall-viewer.ps1 -DryRun

param(
  [switch]$PurgeData,
  [switch]$DryRun
)

$ws = New-Object -ComObject WScript.Shell
$dirs = @(
  [Environment]::GetFolderPath('Desktop'),
  [Environment]::GetFolderPath('Startup')
)

$removed = 0
foreach ($dir in $dirs) {
  if (-not (Test-Path $dir)) { continue }
  Get-ChildItem $dir -Filter '*.lnk' -ErrorAction SilentlyContinue | ForEach-Object {
    $sc = $ws.CreateShortcut($_.FullName)
    if ($sc.Arguments -match 'viewer-launcher\.vbs|open-viewer\.vbs') {
      if ($DryRun) {
        Write-Host "would remove $($_.FullName)"
      } else {
        Remove-Item $_.FullName -Force
        Write-Host "removed $($_.FullName)"
      }
      $removed++
    }
  }
}

# Stop a running viewer (listen on 8420, command line contains viewer.server).
$stops = 0
try {
  Get-NetTCPConnection -LocalPort 8420 -State Listen -ErrorAction Stop | ForEach-Object {
    $pid = $_.OwningProcess
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pid" -ErrorAction SilentlyContinue
    if ($proc -and $proc.CommandLine -match 'viewer\.server') {
      if ($DryRun) { Write-Host "would stop viewer pid $pid" }
      else { Stop-Process -Id $pid -Force; Write-Host "stopped viewer pid $pid" }
      $stops++
    }
  }
} catch {
  Write-Host "no viewer listening on 8420"
}

if ($PurgeData) {
  $db = Join-Path $env:USERPROFILE '.neuron-memory'
  if (Test-Path $db) {
    if ($DryRun) { Write-Host "would delete $db" }
    else { Remove-Item $db -Recurse -Force; Write-Host "deleted $db" }
  }
}

Write-Host "shortcuts: $removed, processes: $stops$(if ($PurgeData) { ', data purged' } else { ', data kept' })"
