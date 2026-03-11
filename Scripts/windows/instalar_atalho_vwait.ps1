$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$shortcutPath = Join-Path $env:USERPROFILE 'Desktop\VWAIT.lnk'
$launcherPath = Join-Path $projectRoot 'Scripts\windows\iniciar_vwait.bat'
$iconPath = Join-Path $projectRoot 'app\assets\vwait_logo.ico'
$cmdPath = Join-Path $env:SystemRoot 'System32\cmd.exe'

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $cmdPath
$shortcut.Arguments = "/c `"$launcherPath`""
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = 'Abrir VWAIT'

if (Test-Path $iconPath) {
    $shortcut.IconLocation = "$iconPath,0"
}

$shortcut.Save()
Write-Output "Atalho atualizado: $shortcutPath"
