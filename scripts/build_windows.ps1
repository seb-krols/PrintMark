# Run from the repository root in PowerShell. Requires Python 3.12, uv and Inno Setup 6.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}

Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $env:UV_PYTHON = '3.12'
    Invoke-Checked uv @('sync', '--frozen', '--extra', 'dev')
    Invoke-Checked uv @('run', 'ruff', 'check', '.')
    Invoke-Checked uv @('run', 'ruff', 'format', '--check', '.')
    Invoke-Checked uv @('run', 'pytest')
    Invoke-Checked uv @('run', 'pyinstaller', '--noconfirm', '--clean', '--onefile', '--name', 'basemark', '--collect-data', 'basemark', 'scripts/entrypoint.py')
    Invoke-Checked uv @('run', 'pyinstaller', '--noconfirm', '--clean', '--onefile', '--windowed', '--name', 'basemark-desktop', '--collect-data', 'basemark', 'scripts/desktop_entrypoint.py')
    Invoke-Checked uv @('run', 'python', 'scripts/package_release.py', 'windows-x64')
    $version = (& uv run python -c 'from basemark import __version__; print(__version__)').Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read package version' }
    $payload = Join-Path (Get-Location) 'build/windows-payload'
    if (Test-Path $payload) { Remove-Item $payload -Recurse -Force }
    Expand-Archive "dist/basemark-$version-windows-x64.zip" $payload
    $compiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6/ISCC.exe'
    if (!(Test-Path $compiler)) { throw 'Install Inno Setup 6 to build the Windows installer.' }
    Invoke-Checked $compiler @("/DAppVersion=$version", "scripts/windows_installer.iss")
    $setup = "dist/basemark-$version-windows-x64-setup.exe"
    $hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $(Split-Path $setup -Leaf)" | Set-Content "$setup.sha256" -Encoding ascii
    Write-Host "Built and verified portable ZIP and installer in dist/"
} finally {
    Pop-Location
}
