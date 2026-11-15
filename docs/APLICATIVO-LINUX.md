> Versão atual: [0.2.3](https://github.com/nihause/atlas-coletor-distribuido/releases/tag/v0.2.3), com chave pública DataJud preenchida automaticamente.

## Distribuição oficial 0.2.2

Repositório público: https://github.com/nihause/atlas-coletor-distribuido.

A publicação oficial usa a tag `v0.2.2` na `main`, com testes, auditoria, empacotamento e assinatura pelo GitHub Actions. O Release inclui `.deb`, SHA-256, `manifest.json` e `manifest.sig`. Consulte as [notas da versão](releases/v0.2.2.md) e o registro de publicação no LOG-IA para os detalhes da validação. A versão 0.2.2 foi publicada e validada em 15/11/2026, pelo Actions 43727933187.

> Atualização 0.2.2: consulte [atualizações e publicação](ATUALIZACOES.md). Este guia substitui as instruções anteriores de atualização por simples checksum/abertura manual.

# Aplicativo gráfico Atlas para Ubuntu

## Instalar sem terminal

1. Obtenha `atlas-coletor_0.2.3_ubuntu24.04_amd64.deb` e o respectivo `.sha256` na versão publicada no GitHub ou no pacote fornecido para revisão. O repositório e o Release são públicos; nenhum token GitHub é necessário.
2. No Ubuntu 24.04 de 64 bits, abra o `.deb` no instalador de pacotes do sistema (menu de contexto → abrir com instalador). O Ubuntu poderá solicitar autorização administrativa para instalar dependências. Se o sistema não tiver um aplicativo associado a `.deb`, será necessário instalar um gerenciador gráfico de pacotes.
3. No menu de aplicativos, abra **ATLAS — Coletor Distribuído**.
4. Em **Configuração**, informe a URL `https://justisoft.com.br/radar/api/v1`, o identificador cadastrado no Radar e a chave de API individual com permissão Ingestão. O cliente acrescenta `/coletores.php/<rota>`; não acrescente essa rota na URL base.
5. Clique em **Testar conexão**. O teste registra/confere o coletor na API, assim como o comando `verificar`; não reserva tarefas de coleta. Mensagens e detalhes técnicos indicam o resultado sem mostrar a chave.
6. Clique em **Conectar e iniciar**. O painel acompanha o motor real; o Radar decide tarefas, concorrência efetiva e ritmo global das fontes.

Python e Qt acompanham o `.deb`; não é necessário instalar Python manualmente. O pacote inclui também o comando de terminal `atlas-worker`. A interface não usa navegador nem Electron.

### Configuração e migração

O padrão da interface é `~/.config/atlas-worker/.env` (respeita `XDG_CONFIG_HOME`). A gravação é atômica e usa permissão 600; o diretório recém-criado usa 700. Não compartilhe o arquivo. O botão **Mostrar** revela a chave somente na tela.

Para usar uma instalação anterior, escolha **Abrir .env existente**. Abrir não modifica o arquivo; salvar atualiza os campos visíveis e mantém os valores das demais opções, inclusive `TASK_TYPES`, `DATAJUD_API_KEY`, `STATE_DIR`, timeouts e opções futuras. Comentários e ordenação podem ser normalizados. Arquivos com link simbólico são recusados para gravação. A interface aceita também `atlas-coletor --env /caminho/.env`; se abrir a partir de uma pasta com `.env`, ela usa esse arquivo.

A chave DataJud é um campo opcional separado. Ela é necessária para tarefas `datajud_lote`, como no motor anterior. Sem ela, o teste avisa; a chave do Radar não substitui a chave DataJud.

**Gerar nova configuração** limpa o formulário após confirmação. Não troca a chave no Radar nem altera o arquivo até salvar. Tokens só são gerados/revogados no painel do Radar. Configuração inválida não substitui a anterior.

O pacote instala somente em `/opt/atlas-coletor` e `/usr/share`/`/usr/bin`. Não há scripts de instalação que apaguem configurações. Atualizar ou remover o pacote preserva os arquivos do usuário. Antes de instalar uma atualização, encerre o motor e o aplicativo antigo; a atualização iniciada pela interface para o motor antes de abrir o instalador.

### Painel e controle

Os indicadores são desta execução: tarefas recebidas (inclui retomadas), concluídas após confirmação do Radar, tarefas com erro, tarefas ativas e tempo de atividade. O histórico central continua no Radar. Não é criado SQLite.

**Desconectar** para de reservar trabalho e usa o encerramento existente, com checkpoints e devolução/expiração de reservas. O encerramento aguarda chamadas em andamento; não mata a thread. **Reiniciar** aguarda o encerramento antes de iniciar novamente. O modo terminal e a interface usam travas por identidade (servidor + nome) e diretório de estado. Uma detecção adicional identifica processos antigos de terminal/serviço legíveis pelo usuário, sem pará-los. Não é possível detectar com certeza processos de outro usuário que ocultem a linha de comando ou usem configuração não legível; não execute instalações paralelas com usuários diferentes.

A configuração fica bloqueada durante a execução. Para editar, desconecte primeiro. O contrato continua sendo 1, e o motor recusa iniciar contra outro contrato.

### Inicialização e bandeja

**Conectar automaticamente ao entrar no Ubuntu** é opcional e cria `~/.config/autostart/atlas-coletor.desktop`. Isso inicia na sessão gráfica do usuário, não antes do login. Desmarcar remove somente esse atalho. Nenhum serviço systemd antigo é modificado ou desativado. Pare o serviço anterior antes de passar a operar pela interface.

Se a bandeja estiver disponível, habilite **Continuar trabalhando ao fechar a janela** para ocultar a janela e manter a coleta. O menu da bandeja permite abrir, parar e encerrar. Sem bandeja, a opção fica desabilitada e fechar aguarda o encerramento seguro. A bandeja depende do ambiente gráfico/extensão AppIndicator; não é simulada quando indisponível.

### Logs e diagnóstico

A aba **Logs** mostra os últimos eventos, filtros Informação/Aviso/Erro e identificador da tarefa quando presente. Mantém até mil entradas na tela e carrega até 256 KiB recentes do arquivo ao abrir. **Limpar visualização** limpa a tela, sem apagar o histórico em disco.

Os novos registros de `worker.log` são JSON estruturado, com rotação de 10 MiB e cinco cópias, em `STATE_DIR/logs`. Arquivos antigos em texto permanecem no disco, mas linhas fora do formato JSON não são mostradas na aba. Segredos conhecidos, cabeçalhos Bearer e padrões de chaves são removidos, inclusive de exceções. Não habilite ferramentas externas que registrem todo o tráfego HTTP com credenciais.

**Exportar diagnóstico** permite escolher um arquivo JSON privado, contendo versão, estados, indicadores e eventos sanitizados. Não inclui o `.env` nem os campos de credenciais.

### Teste de conexão

GUI e CLI usam `verification.check_connection`. HTTP 401 indica chave recusada; HTTP 403 com código `sem_permissao` indica ausência de permissão de ingestão. Outros 403 recebem mensagem de acesso recusado, sem inventar a causa. HTTP 404, redirecionamento e resposta HTML/JSON fora do contrato indicam URL/resposta inesperada. Timeout, DNS e certificado são distinguidos somente pelas exceções técnicas correspondentes. Falha de conexão genérica não é rotulada como DNS. Redirecionamentos do Radar não são seguidos; TLS continua validado.

## Atualizações autorizadas pelo usuário

A aba **Atualizações** consulta automaticamente os Releases públicos ao abrir e a cada seis horas. Mostra versão instalada/disponível, horário, novidades, progresso e estado de instalação. Não precisa de token GitHub. A chave Radar nunca é enviada ao GitHub.

O cliente compara versões estáveis, valida Ubuntu 24.04/arquitetura e exige manifesto Ed25519 válido com a chave pública incorporada. O pacote deve corresponder ao projeto oficial, versão, nome, tamanho e SHA-256 assinados. Pacotes alterados, sem assinatura, incompatíveis e downgrade são bloqueados.

Atualizar agora pede confirmação, baixa o pacote, suspende novas reservas e espera as tarefas atuais terminarem. É possível cancelar a espera. Depois, pkexec pede a autorização administrativa e o instalador verifica novamente o pacote antes de usar apt-get. O processo anterior sai antes do reinício; configuração, logs e estado são preservados. Detalhes em [ATUALIZACOES.md](ATUALIZACOES.md).

Para quem usa 0.2.1, a primeira instalação do 0.2.2 pelo .deb é recomendada para obter esse fluxo completo. O atualizador antigo pode abrir o pacote no instalador do Ubuntu, mas não faz a validação independente de assinatura nem a instalação integrada nova.

## Desenvolver e gerar o pacote

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[gui,dev,build-gui]'
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/atlas-coletor
.venv/bin/python scripts/gerar-deb.py --output /tmp/atlas-packages
```

O empacotamento requer Ubuntu 24.04 e `dpkg-deb`; inclui o Python, o motor e os módulos Qt utilizados via PyInstaller. Todos os temporários ficam fora do repositório. Gera `.deb` e `.deb.sha256`. Há também `scripts/instalar-grafico-linux.sh` com diálogos Zenity para instalar pelo código e criar atalho por usuário, mantendo `.env` e serviços existentes. O `.deb` é a opção preferencial para quem não usa terminal.

Referências oficiais do empacotamento: [Qt for Python e PyInstaller](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html) e [instalação Qt for Python](https://doc.qt.io/qtforpython-6/gettingstarted.html). O PySide6 é dependência opcional; `pip install .` e os instaladores antigos continuam voltados ao terminal.

O workflow `.github/workflows/aplicativo.yml` testa em Ubuntu 24.04 e disponibiliza o pacote como artifact para cada branch/PR. Tags `v*` aprovadas pelo mantenedor geram um Release com pacote, checksum, manifesto e assinatura. O push da branch não publica Release. Não enviar `.env`, estados, logs, diagnósticos ou pacotes locais ao Git.

## Limites de validação

Testes automatizados usam Qt real em `offscreen`, motor real e APIs simuladas. Não consultam nem reservam tarefas de produção. Instalação administrativa pelo gerenciador do Ubuntu, bandeja numa sessão GNOME real, inicialização após login, atualização entre duas versões publicadas e scripts Windows precisam de validação no computador de destino.

## Arquivos da implementação

- `src/atlas_worker/gui/app.py`, `runtime.py`, `desktop.py`, `style.py`, `atlas.svg` e `__init__.py`: interface Qt, trabalho assíncrono, controle do motor, bandeja, autostart e identidade visual.
- `src/atlas_worker/config_store.py`: leitura e gravação privada das configurações.
- `src/atlas_worker/verification.py`: resultado estruturado compartilhado pelo teste CLI/GUI.
- `src/atlas_worker/instance.py`: travas e detecção de processo legado.
- `src/atlas_worker/updates.py`: Releases, compatibilidade, download e SHA-256.
- `src/atlas_worker/client.py`, `config.py`, `main.py`, `metrics.py`, `worker.py`, `logging_config.py` e `__init__.py`: diagnóstico de protocolo/rede, validação de URL, CLI preservada, telemetria, erros fatais para a interface, logs estruturados e versão 0.2.0; contrato mantido em 1.
- `pyproject.toml`: dependências opcionais, comando `atlas-coletor` e recurso do ícone.
- `packaging/launcher.py`, `scripts/gerar-deb.py`, `scripts/instalar-grafico-linux.sh`: aplicativo empacotado, `.deb` e alternativa de instalação pelo código.
- `.github/workflows/aplicativo.yml`: testes, artifact e publicação mediante tag.
- `tests/test_desktop_core.py`, `tests/test_gui.py`: configuração, rede, segurança, Qt e integração com o motor real usando APIs simuladas.
- `README.md`, `docs/OPERACAO.md`, `docs/APLICATIVO-LINUX.md` e `docs/LOG-IA.md`: instruções e rastreabilidade.

### Resultado da validação desta entrega

Em 15/11/2026: **76 testes aprovados**; `.deb` amd64 gerado no Ubuntu 24.04 com 105.963.080 bytes e checksum conferido. O pacote foi extraído e o binário Qt abriu em modo offscreen, sem ambiente virtual; a CLI empacotada respondeu `atlas-worker 0.2.0 (contrato 1)`. Não houve instalação administrativa nem comunicação com APIs de produção. O `.deb` e seu checksum estão em `/home/justisoft/Downloads/atlas-coletor/` nesta máquina; os próximos builds serão artifacts do workflow no GitHub.
