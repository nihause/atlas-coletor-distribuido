# Confere conexão, chave e contrato com o servidor, sem pedir tarefa.
$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz
& (Join-Path $Raiz ".venv\Scripts\atlas-worker.exe") --env ".env" verificar
exit $LASTEXITCODE
