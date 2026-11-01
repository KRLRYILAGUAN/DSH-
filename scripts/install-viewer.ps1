# Create desktop and logon shortcuts for the portable viewer launcher.
# Pure ASCII on purpose: no machine-specific paths are written anywhere
# except the shortcut files themselves, which are generated here.

$root = Split-Path -Parent $PSScriptRoot
$vbs = Join-Path $PSScriptRoot 'open-viewer.vbs'

if (-not (Test-Path $vbs)) {
  Write-Error "open-viewer.vbs not found next to this script"
  exit 1
}

$ws = New-Object -ComObject WScript.Shell

$desktop = [Environment]::GetFolderPath('Desktop')
$link = $ws.CreateShortcut((Join-Path $desktop 'Neuron Memory Viewer.lnk'))
$link.TargetPath = 'wscript.exe'
$link.Arguments = '"' + $vbs + '"'
$link.WorkingDirectory = $root
$link.Description = 'Neuron memory viewer'
$link.Save()

$startup = [Environment]::GetFolderPath('Startup')
$auto = $ws.CreateShortcut((Join-Path $startup 'Neuron Memory Viewer.lnk'))
$auto.TargetPath = 'wscript.exe'
$auto.Arguments = '"' + $vbs + '" /nobrowser'
$auto.WorkingDirectory = $root
$auto.Description = 'Start neuron memory viewer at logon'
$auto.Save()

Write-Host "Shortcuts created:"
Write-Host "  $desktop\Neuron Memory Viewer.lnk"
Write-Host "  $startup\Neuron Memory Viewer.lnk"
