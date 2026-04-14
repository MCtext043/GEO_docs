# Сборка лёгкого EXE в отдельном venv (без Langflow/torch из основного .venv)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Venv = Join-Path $Root ".venv-normdocs-build"
if (-not (Test-Path "$Venv\Scripts\python.exe")) {
    py -3.12 -m venv $Venv
}
& "$Venv\Scripts\pip.exe" install -U pip -q
& "$Venv\Scripts\pip.exe" install -r (Join-Path $Root "requirements-normdocs.txt") -q
& "$Venv\Scripts\pyinstaller.exe" --noconfirm --clean (Join-Path $Root "build_normdocs_exe.spec")
Write-Host "Готово: $Root\dist\NormDocsLangflow\NormDocsLangflow.exe"
