# Auditoria pré-publicação — 15/11/2026

Repositório correto: nihause/atlas-coletor-distribuido. GitHub confirmou visibilidade privada e permissão administrativa da conta conectada. PR #1: origem feat/aplicativo-grafico-linux, destino main. Nenhuma tag nem Release existente na conferência inicial. Branches locais/remotas e todo o histórico alcançável foram examinados; nenhum histórico foi reescrito.

Gitleaks 8.30.1: nenhum segredo no histórico (oito commits existentes ao iniciar a missão) nem na árvore de arquivos, incluindo os arquivos novos. Binário oficial conferido com checksum publicado. Relatórios detalhados ficam fora do projeto e com redação de segredos; nunca anexar um relatório sem revisar. A verificação volta a rodar no CI com fetch-depth 0.

Revisão manual: .env.example sem valores de credenciais; .gitignore exclui ambientes, dados, logs e chaves; configuração real fora do Git; fixtures de testes sintéticas. Workflows não recebem segredo em PR; assinatura somente em tag. Permissões de escrita só no job de publicação. URLs de fontes públicas e Radar são intencionais. Não encontrados dumps, chaves privadas versionadas, dados de clientes ou credenciais que exijam rotação.

Há documentação de arquitetura, nomes de tabelas e caminhos operacionais do JustiSOFT. São informações técnicas do código publicado, não credenciais ou acesso a servidores. O proprietário deve considerar essa exposição ao confirmar a publicação. O patch da integração PHP contém código e testes, sem dados do banco.

A primeira dependência cryptography selecionada (46.0.7) tinha alertas no pip-audit. Foi substituída por >=50,<51; a auditoria repetida informou nenhuma vulnerabilidade conhecida. Isso não representa garantia absoluta de ausência de vulnerabilidades.

Somente chave pública de assinatura está incorporada. Chave privada nova fica fora do Git, com acesso 600, e no secret de publicação do GitHub. Nenhum .env foi enviado ao GitHub. O segredo de assinatura não aparece nos artifacts nem em PRs.

Resultado: não foi identificado segredo ou risco relevante que impeça preparar a publicação. Alterar a visibilidade e publicar o primeiro Release público continuam pendentes de confirmação explícita do usuário, conforme a missão anexada. Não alegar que a auditoria automatizada substitui revisão contínua.
