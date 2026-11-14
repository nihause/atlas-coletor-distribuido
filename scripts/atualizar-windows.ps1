# Atualiza o coletor pelo Git preservando .env, estado e logs (fora do Git). Recusa se houver alteração local em arquivo versionado.
$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz
if (git status --porcelain --untracked-files=no) { git status --short --untracked-files=no; throw "Há alterações locais em arquivos versionados; não vou sobrescrevê-las." }
$antes = git rev-parse --short HEAD
git fetch --quiet origin
git pull --ff-only --quiet
$venvPy = Join-Path $Raiz ".venv\Scripts\python.exe"
& $venvPy -m pip install --quiet -e .
Write-Host "Atualizado: $antes -> $(git rev-parse --short HEAD)"
if (Get-ScheduledTask -TaskName "AtlasWorker" -ErrorAction SilentlyContinue) { Stop-ScheduledTask -TaskName "AtlasWorker" -ErrorAction SilentlyContinue; Start-ScheduledTask -TaskName "AtlasWorker"; Write-Host "Tarefa reiniciada." }
& (Join-Path $Raiz ".venv\Scripts\atlas-worker.exe") --env ".env" verificar
