# Create desktop and logon shortcuts for the plugin's bundled viewer.
# Pure ASCII: no machine-specific paths are embedded in this script.

$pkg = Split-Path -Parent $PSScriptRoot
$vbs = Join-Path $PSScriptRoot 'viewer-launcher.vbs'

if (-not (Test-Path $vbs)) {
  Write-Error "viewer-launcher.vbs not found"
  exit 1
}

$ws = New-Object -ComObject WScript.Shell

$desktop = [Environment]::GetFolderPath('Desktop')
$link = $ws.CreateShortcut((Join-Path $desktop 'Neuron Memory Viewer.lnk'))
$link.TargetPath = 'wscript.exe'
$link.Arguments = '"' + $vbs + '"'
$link.WorkingDirectory = $pkg
$link.Save()

$startup = [Environment]::GetFolderPath('Startup')
$auto = $ws.CreateShortcut((Join-Path $startup 'Neuron Memory Viewer.lnk'))
$auto.TargetPath = 'wscript.exe'
$auto.Arguments = '"' + $vbs + '" /nobrowser'
$auto.WorkingDirectory = $pkg
$auto.Save()

Write-Host "Created:"
Write-Host "  $desktop\Neuron Memory Viewer.lnk"
Write-Host "  $startup\Neuron Memory Viewer.lnk"
Write-Host "Set NEURON_DB to the database the skill uses (default: %USERPROFILE%\.neuron-memory\neuron.db)."
