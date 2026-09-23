param(
    [ValidateSet('install', 'remove')][string]$Action = 'install',
    [Parameter(Mandatory = $true)][string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'
$startup = [Environment]::GetFolderPath('Startup')
if (-not $startup) {
    throw 'The per-user Startup folder could not be found.'
}

$shortcutPath = Join-Path $startup 'Keyboard-Agent.lnk'
$legacyPath = Join-Path $startup 'Keyboard-Agent.bat'

if ($Action -eq 'remove') {
    foreach ($path in @($shortcutPath, $legacyPath)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path
            Write-Output "Removed: $path"
        }
    }
    exit 0
}

$pythonw = Join-Path $ProjectRoot '.venv\Scripts\pythonw.exe'
$agent = Join-Path $ProjectRoot 'win_agent.py'
if (-not (Test-Path -LiteralPath $pythonw)) {
    $installed = Get-Command pythonw.exe -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $installed) {
        throw 'pythonw.exe was not found. Run setup_windows.bat first.'
    }
    $pythonw = $installed.Source
}
if (-not (Test-Path -LiteralPath $agent)) {
    throw 'win_agent.py is missing from the project directory.'
}

# Only retire the Startup entry created by the previous installer.
if (Test-Path -LiteralPath $legacyPath) {
    $legacyText = Get-Content -LiteralPath $legacyPath -Raw
    if ($legacyText -notmatch 'created by setup_autostart\.bat') {
        throw 'An unexpected Keyboard-Agent.bat exists in Startup. Inspect it manually.'
    }
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = '"' + $agent + '"'
$shortcut.WorkingDirectory = $ProjectRoot
$shortcut.Description = 'Keyboard-Agent local pet'
$shortcut.Save()

if (-not (Test-Path -LiteralPath $shortcutPath)) {
    throw 'The Startup shortcut was not created.'
}
if (Test-Path -LiteralPath $legacyPath) {
    Remove-Item -LiteralPath $legacyPath
}
Write-Output "Installed windowless autostart: $shortcutPath"
