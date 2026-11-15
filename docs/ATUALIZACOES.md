# Atualização gráfica e publicação oficial — Atlas 0.2.2

## Uso no computador coletor

A janela ocupa 94% da altura útil e respeita o monitor, sem maximizar. O painel foi reorganizado em duas linhas de indicadores e conexão compacta. Em 1100×700 e 1180×970, a coleta simples cabe sem rolagem e todos os indicadores ficam visíveis. Em conteúdo excepcionalmente grande, fontes ampliadas ou várias tarefas longas, a rolagem de segurança continua disponível para não cortar informações.

A aba Atualizações consulta automaticamente ao abrir e a cada seis horas. Mostra versão instalada, última publicada, horário, novidades, download e instalação. Repositório público dispensa token; enquanto privado, o campo opcional aceita token próprio do GitHub apenas em memória. Nunca usar a chave Radar nesse campo. Não existe instalação automática sem consentimento.

Use Verificar atualizações → Baixar atualização → Atualizar agora. Atualizar agora também baixa, caso necessário. A autenticidade é verificada por Ed25519 com chave pública incorporada, manifesto oficial e SHA-256. Somente Ubuntu 24.04 e arquitetura publicada são aceitos; downgrade é recusado. Sem manifesto assinado, a atualização fica bloqueada, mesmo com checksum válido.

Se estiver coletando, o Atlas suspende novas reservas, mantém heartbeat/renovação e aguarda todas as tarefas atuais concluírem. Não usa o encerramento com prazo de 30 segundos para atualizar. Cancelar atualização libera novas reservas. O usuário pode cancelar enquanto aguarda a coleta. Desativação pelo Radar ou perda de reserva continuam respeitando o contrato 1, sem conclusões inventadas.

Após a coleta, o pkexec pede autorização gráfica do Ubuntu. O executável instalado de propriedade de root faz uma cópia privada do pacote e verifica novamente assinatura, versão, arquitetura, tamanho, SHA e metadados Debian. Só então chama apt-get para instalar o pacote oficial e resolver dependências, sem permitir remoções. Não lê .env nem salva senha. A confirmação da versão vem de dpkg-query. Em caso de erro, a interface informa e mantém os arquivos de configuração; não há promessa de rollback transacional do apt/dpkg.

O reinício aguarda a saída do processo anterior antes de abrir a nova janela, e mantém as travas de instância. Reutiliza o mesmo --env e reconecta se a coleta estava ativa. WORKER_NAME, WORKER_TOKEN, RADAR_API_URL, concorrência, heartbeat, nível de log, logs, checkpoints, preferências e autostart ficam fora do pacote. Uma instalação por usuário não altera as configurações de outro.

### Primeira atualização da versão 0.2.1

O atualizador 0.2.1 não possui verificação de assinatura nem instalação integrada. Para entrar no fluxo novo, pare a coleta, feche o Atlas e instale manualmente o .deb 0.2.2 oficial. Depois, as próximas versões poderão ser instaladas pela aba Atualizações. Não executar serviço/CLI antigo junto da GUI.

## Publicar versões futuras

1. Revisar código e documentação; atualizar pyproject.toml e atlas_worker.__version__ juntos.
2. Abrir PR e aguardar todos os testes, Gitleaks (histórico completo), pip check, pip-audit e empacotamento passarem. Integrar à main.
3. Confirmar que não existem tag/Release para a versão. A primeira publicação pública depende da confirmação do proprietário, assim como tornar o repositório público.
4. Criar e enviar tag vX.Y.Z apontando para o commit validado da main. Commits normais geram artifacts; só tags publicam Releases.
5. O workflow testa, verifica segredos/dependências, confere tag versus versão, gera .deb/checksum, assina manifest.json com ATLAS_RELEASE_SIGNING_KEY e produz manifest.sig. A verificação local do manifesto garante que a chave corresponde à pública incorporada.
6. O job de publicação, dependente do sucesso anterior, tem contents:write e anexa pacote, checksum, manifesto e assinatura. Não sobrescreve Release existente. As demais etapas têm somente contents:read. Actions são fixadas por SHA.
7. Conferir o Release, baixar e testar em uma máquina Ubuntu de homologação antes de recomendar atualização dos demais coletores.

A chave privada Ed25519 foi gerada com permissão 600 fora do repositório e armazenada no secret GitHub Actions ATLAS_RELEASE_SIGNING_KEY. Nunca colocar seu conteúdo em argumentos, logs, docs, artifacts ou commits. A cópia local fica na área privada de publicação do mantenedor; protegê-la e manter backup seguro. Apenas release_trust.py, com a chave pública, entra no aplicativo. Rotação exige distribuir primeiro uma versão com confiança atualizada; não trocar silenciosamente a chave e invalidar instalações antigas.

Para gerar manifesto local: executar scripts/assinar-release.py com diretório dos pacotes e chave recebida pelo ambiente ATLAS_RELEASE_SIGNING_KEY, sem imprimi-la. Artefatos sem assinatura não são instaláveis pelo novo atualizador.

## Integração com Radar

O heartbeat já enviava a versão instalada. Agora envia atualizacao opcional com estado e última versão consultada, sem comandos executáveis. O servidor aceita uma lista fechada de estados e versão numérica, guarda em coleta_rotina_config com chave derivada do ID autenticado e mostra no cartão administrativo. Clientes antigos continuam aceitos. Campo desconhecido vira Não informado; não há URL, comando de shell ou instalação remota autorizada pelo Radar.

## Limites da validação

Testes automatizados cobrem GitHub simulado, versão atual/nova, token separado, download interrompido, assinatura/checksum/tamanho inválidos, pacote incompatível, downgrade, instalação simulada com falha, .env preservado, reinício, travas de instância, espera e cancelamento durante coleta, painel sem rolagem e periodicidade automática. Assinatura local do pacote e abertura do binário extraído são conferidas separadamente no LOG-IA.

Não foi executada instalação elevada real, atualização entre dois Releases reais, reinício/reconexão real no PC1, bandeja/autostart GNOME nem teste Windows. Não declarar o fluxo completo homologado antes desses testes. A configuração do PC1 não foi lida nem alterada.

Referências técnicas: [Ed25519 / cryptography](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/) e [segurança do GitHub Actions](https://docs.github.com/en/actions/how-tos/secure-your-work).
