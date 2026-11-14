<#
Instala o coletor neste computador Windows: ambiente virtual, dependências, configuração e tarefa agendada (inicia com o Windows e reinicia após falhas).
NÃO sobrescreve configuração existente (use -ForcarConfig). Executar no PowerShell, na pasta do projeto:
    powershell -ExecutionPolicy Bypass -File scripts\instalar-windows.ps1 [-Url URL] [-Nome NOME] [-TokenArquivo ARQ] [-SemTarefa] [-ForcarConfig]
A tarefa agendada em nome do sistema exige PowerShell como Administrador; sem isso, ela é criada para iniciar no logon do usuário atual.
AVISO: este script não pôde ser executado nos testes automatizados do projeto (ambiente Linux); valide-o no primeiro computador Windows.
#>
param([string]$Url = "", [string]$Nome = "", [string]$TokenArquivo = "", [switch]$SemTarefa, [switch]$ForcarConfig)
$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz

# 1) Python 3.11+
$py = $null
foreach ($c in @("py -3.12", "py -3.11", "py -3.13", "python")) {
    try {
        $partes = $c.Split(" ")
        $ok = & $partes[0] $partes[1..($partes.Length - 1)] -c "import sys; print(int(sys.version_info >= (3,11)))" 2>$null
        if ($ok -eq "1") { $py = $c; break }
    } catch { }
}
if (-not $py) { throw "Python 3.11 ou superior não encontrado. Instale em https://www.python.org/downloads/ (marque 'Add python.exe to PATH') e rode de novo." }
Write-Host "Python encontrado: $py"

# 2) Ambiente virtual e dependências
$partes = $py.Split(" ")
if (-not (Test-Path ".venv")) { & $partes[0] $partes[1..($partes.Length - 1)] -m venv .venv }
$venvPy = Join-Path $Raiz ".venv\Scripts\python.exe"
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -e .
$worker = Join-Path $Raiz ".venv\Scripts\atlas-worker.exe"
& $worker version

# 3) Configuração (.env): só cria se não existir
if ((Test-Path ".env") -and -not $ForcarConfig) {
    Write-Host "Configuração existente mantida (.env). Use -ForcarConfig para recriar."
} else {
    if (-not $Url) { $Url = Read-Host "Endereço da API do Radar (ex.: https://servidor.exemplo.com/radar/api/v1)" }
    if (-not $Nome) { $sug = "coletor-" + ($env:COMPUTERNAME.ToLower() -replace '[^a-z0-9]', '-'); $Nome = Read-Host "Nome deste computador [$sug]"; if (-not $Nome) { $Nome = $sug } }
    if ($TokenArquivo) { $token = (Get-Content -Raw $TokenArquivo).Trim() }
    else { $sec = Read-Host "Chave de API deste computador (não aparece na tela)" -AsSecureString; $token = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)) }
    if (-not $token) { throw "Chave vazia." }
    if (Test-Path ".env") { Copy-Item ".env" (".env.anterior." + (Get-Date -Format yyyyMMddHHmmss)) }
    $linhas = Get-Content ".env.example" | ForEach-Object {
        if ($_ -match '^RADAR_API_URL=') { "RADAR_API_URL=$Url" }
        elseif ($_ -match '^WORKER_NAME=') { "WORKER_NAME=$Nome" }
        elseif ($_ -match '^WORKER_TOKEN=') { "WORKER_TOKEN=$token" }
        else { $_ } }
    Set-Content -Path ".env" -Value $linhas -Encoding UTF8
    # só o usuário atual (e o sistema) lê o arquivo
    icacls ".env" /inheritance:r /grant:r "$($env:USERNAME):(R,W)" "SYSTEM:(R)" | Out-Null
    Write-Host "Configuração gravada em $Raiz\.env (acesso restrito ao seu usuário)."
}

# 4) Confere a conexão
Write-Host "Verificando a conexão com o servidor..."
& $worker --env ".env" verificar
if ($LASTEXITCODE -ne 0) { throw "A verificação falhou: corrija o .env e rode: .venv\Scripts\atlas-worker.exe --env .env verificar" }

# 5) Tarefa agendada
if (-not $SemTarefa) {
    $nomeTarefa = "AtlasWorker"
    if (Get-ScheduledTask -TaskName $nomeTarefa -ErrorAction SilentlyContinue) {
        Write-Host "A tarefa '$nomeTarefa' já existe; mantida."
    } else {
        $acao = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Raiz\scripts\iniciar-windows.ps1`"" -WorkingDirectory $Raiz
        $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if ($admin) { $gatilho = New-ScheduledTaskTrigger -AtStartup; $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest }
        else { $gatilho = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME; $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive }
        $cfg = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        Register-ScheduledTask -TaskName $nomeTarefa -Action $acao -Trigger $gatilho -Principal $principal -Settings $cfg | Out-Null
        Start-ScheduledTask -TaskName $nomeTarefa
        Write-Host "Tarefa agendada '$nomeTarefa' criada e iniciada ($(if ($admin) { 'ao ligar o computador' } else { 'ao entrar no Windows' }))."
    }
} else { Write-Host "Tarefa agendada não criada. Para rodar agora: powershell -File scripts\iniciar-windows.ps1" }
