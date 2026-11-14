# Executa o coletor e o reinicia depois de qualquer saída inesperada (espera 15 s entre tentativas). Código 0 = parada normal, não reinicia.
$ErrorActionPreference = "Continue"
$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz
$worker = Join-Path $Raiz ".venv\Scripts\atlas-worker.exe"
if (-not (Test-Path $worker)) { Write-Error "Rode primeiro scripts\instalar-windows.ps1"; exit 1 }
if (-not (Test-Path ".env")) { Write-Error "Falta o arquivo .env"; exit 1 }
while ($true) {
    & $worker --env ".env" run
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 15
}
