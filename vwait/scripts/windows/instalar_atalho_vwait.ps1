$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$shortcutPath = Join-Path $env:USERPROFILE 'Desktop\VWAIT.lnk'
$launcherPath = Join-Path $projectRoot 'scripts\windows\abrir_vwait_hidden.vbs'
$iconPath = Join-Path $projectRoot 'src\vwait\core\assets\vwait_logo.ico'
$wscriptPath = Join-Path $env:SystemRoot 'System32\wscript.exe'

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $wscriptPath
$shortcut.Arguments = "`"$launcherPath`""
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = 'Abrir VWAIT'

if (Test-Path $iconPath) {
    $shortcut.IconLocation = "$iconPath,0"
}

$shortcut.Save()
Write-Output "Atalho atualizado: $shortcutPath"
