> Versão oficial: [Atlas 0.2.2](https://github.com/nihause/atlas-coletor-distribuido/releases/tag/v0.2.2) · [Baixar instalador Ubuntu 24.04 amd64](https://github.com/nihause/atlas-coletor-distribuido/releases/download/v0.2.2/atlas-coletor_0.2.2_ubuntu24.04_amd64.deb). Repositório público, sem token GitHub. Quem usa 0.2.1 deve instalar o 0.2.2 uma vez para obter o novo atualizador assinado; mantenha seu .env e sua chave Radar.

> Atualização 0.2.2: consulte [atualizações e publicação](docs/ATUALIZACOES.md). Este guia substitui as instruções anteriores de atualização por simples checksum/abertura manual.

# atlas-coletor-distribuido

Coletor distribuído do ecossistema **Atlas/Radar**. Cada computador conectado roda um *worker* Python que pede tarefas ao servidor central (o Radar), executa as consultas autorizadas e devolve os resultados em lotes. **O worker nunca acessa o banco de dados**: só fala com uma API HTTPS autenticada.

```
 computador 1..N                         servidor central (Radar)
 ┌──────────────┐  HTTPS + chave       ┌──────────────────────────┐
 │ atlas-worker │ ───────────────────► │ /api/v1/coletores.php/*  │
 │  asyncio     │ ◄─ tarefa, comando ─ │  fila, reservas, limites │──► MySQL (só o servidor grava)
 └──────────────┘                      └──────────────────────────┘
   consulta DJEN / DataJud, filtra, entrega lotes; limite de requisições global
```

## O que o worker faz

| Tipo de tarefa | O que é | Quem decide |
|---|---|---|
| `djen_janela` | Um período de um favorito (parte, advogado ou comarca) no DJEN | O servidor monta a consulta e o filtro; o worker pagina, filtra homônimos e entrega |
| `datajud_lote` | Até 50 processos do escopo no DataJud (movimentações, assunto, grau) | O servidor reserva os processos; o worker consulta e entrega |

O servidor decide o que cada computador faz e redistribui conforme a disponibilidade: **não há função fixa por máquina**. Reservas têm prazo (renovado por heartbeat); se um computador some, a tarefa volta à fila do último checkpoint. Cada lote é idempotente (reenviar não duplica) e a tarefa só termina depois que o servidor confirma que persistiu tudo.

O limite de requisições às fontes (DJEN, DataJud) é **global**: o worker pergunta ao servidor quanto esperar antes de cada chamada, e o limite vale para todos os computadores somados. 429, `Retry-After` e falhas das fontes são relatados ao servidor, que aplica espera crescente e disjuntor. A descoberta geral de processos continua **desligada**.

## Aplicativo gráfico no Ubuntu 24.04

Abra o pacote **atlas-coletor_0.2.2_ubuntu24.04_amd64.deb** no instalador do Ubuntu. Depois, procure **ATLAS — Coletor Distribuído** no menu de aplicativos. Python e Qt acompanham o pacote.

Na aba **Configuração**, informe o endereço `https://justisoft.com.br/radar/api/v1`, o nome e a chave individual criada em **Radar → Administração → Coletores**. Clique em **Testar conexão** e depois **Conectar e iniciar**. A tela mostra tarefas, conexão, produtividade e logs sem precisar de terminal. A chave DataJud tem campo próprio, caso este computador execute tarefas DataJud.

Para reutilizar uma instalação, escolha **Abrir .env existente**. As opções extras e os dados locais são preservados. Inicialização automática na sessão Ubuntu e permanência na bandeja são opcionais. A aba **Atualizações** consulta os Releases públicos ao abrir e a cada seis horas, valida assinatura Ed25519 e SHA-256 e instala somente após autorização, aguardando as tarefas atuais. O Release oficial 0.2.2 já está disponível; branches de desenvolvimento continuam oferecendo artifacts de revisão.

Veja [Aplicativo Linux](docs/APLICATIVO-LINUX.md) para instalação, migração, atualização, diagnóstico, empacotamento e limites dos testes. Para desenvolver: `pip install -e ".[gui,dev,build-gui]"`; para abrir: `atlas-coletor`. O modo terminal abaixo continua disponível e usa o mesmo motor e contrato de API.

## Instalar em um computador

Pré-requisitos para o modo terminal: Python 3.11+, Git, e uma **chave de API exclusiva deste computador** (no Radar: Administração → Coletores → Adicionar coletor; a chave aparece uma única vez).

### Ubuntu / Linux
```bash
git clone URL_DO_REPOSITORIO
cd atlas-coletor-distribuido
scripts/instalar-linux.sh
```
O instalador cria o ambiente virtual, instala as dependências, pergunta a URL do Radar, o nome do computador e a chave (sem eco; vai para `.env`, permissão 600), confere a conexão e, se você aceitar, instala o serviço `systemd` (inicia com o sistema e reinicia após falhas). Nada existente é sobrescrito.

### Windows
```powershell
git clone URL_DO_REPOSITORIO
cd atlas-coletor-distribuido
powershell -ExecutionPolicy Bypass -File scripts\instalar-windows.ps1
```
Cria a tarefa agendada `AtlasWorker` (ao ligar o computador, se executado como Administrador; senão, ao entrar no Windows) com reinício automático. *Os scripts do Windows não puderam ser executados nos testes automatizados (feitos em Linux): valide no primeiro computador Windows.*

### Verificar a conexão
```bash
scripts/verificar-linux.sh          # ou: .venv/bin/atlas-worker --env .env verificar
```
Mostra: endereço, autenticação, contrato da API, comando atual do servidor e limites globais. Saída 0 = pronto; 4 = chave recusada; 5 = servidor inacessível.

### Executar sem serviço
```bash
scripts/iniciar-linux.sh            # Windows: scripts\iniciar-windows.ps1
```

## Configuração (`.env`)
Veja `.env.example`. O essencial:
```dotenv
RADAR_API_URL=https://servidor.exemplo.com/radar/api/v1
WORKER_NAME=coletor-01
WORKER_TOKEN=            # a chave deste computador; nunca vai para o Git
MAX_CONCURRENCY=2
HEARTBEAT_INTERVAL=30
LOG_LEVEL=INFO
```
`DATAJUD_API_KEY` (chave pública do DataJud) só é necessária para tarefas `datajud_lote`. HTTPS é obrigatório (certificado validado); `http://` só em endereço local e com `ALLOW_INSECURE_HTTP=1`, para testes.

## Atualizar (preserva a configuração)
```bash
scripts/atualizar-linux.sh          # Windows: scripts\atualizar-windows.ps1
```
Faz `git pull --ff-only`, reinstala as dependências e reinicia o serviço (a tarefa em curso é devolvida sem penalidade e retomada). `.env`, estado e logs ficam fora do Git e não são tocados. Se houver alteração local em arquivo versionado, recusa em vez de sobrescrever.

## Conectar os três computadores adicionais
1. No Radar (Administração → API), crie **uma chave por computador** (nome `coletor-02`, `coletor-03`, `coletor-04`), permissão **Ingestão**. Cada chave é revogável sozinha.
2. Em cada computador: `git clone`, `scripts/instalar-linux.sh` (ou o do Windows) com o nome e a chave daquele computador.
3. Em **Administração → Coletores** do Radar, o computador aparece online em até 30 s. Comece por **um** computador, acompanhe uma hora (tarefas concluídas, erros, produtividade) e só então conecte os demais.
4. Para pausar ou desativar um computador: botões na mesma tela. Pausado, ele devolve a tarefa atual sem penalidade e não pede outra.

## Desenvolvimento
```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q       # sem rede: o servidor e as fontes são simulados
```
Documentação: [`docs/CONTRATO-API.md`](docs/CONTRATO-API.md) (rotas e contrato v1), [`docs/OPERACAO.md`](docs/OPERACAO.md) (operação e diagnóstico), [`AGENTS.md`](AGENTS.md) (regras para quem altera o projeto).

## Segurança
- Credencial individual por computador, revogável no servidor; nunca em código, log ou Git (`.gitignore` bloqueia `.env`, chaves, logs, dumps e dados coletados).
- O token é `SecretStr` e filtrado dos logs.
- Sem acesso ao MySQL; só API autenticada sobre HTTPS com certificado validado.
- Sem contorno de CAPTCHA, bloqueio ou limite das fontes; só consultas oficiais e públicas, dentro do limite global.
- Registros sigilosos (nível de sigilo > 0) não saem do computador.

Progresso e atualização do PC1: [guia da versão 0.2.1](docs/PROGRESSO-COLETA.md).
