# Progresso da coleta — Atlas 0.2.1 e Radar

O painel Atlas mostra o alvo e período de cada tarefa, fonte, fase, páginas/consultas, itens lidos na fonte, encontrados após filtros e confirmados pelo Radar. Os números de execução começam ao conectar; tarefas recentes permanecem no painel. Lidos não significa aceitos: a confirmação só aumenta após a resposta do servidor. Enquanto a fonte pagina, o progresso aparece mesmo antes do primeiro envio.

O botão fica desativado e indica Conectando, Coletando, Aguardando tarefas, Pausado ou Parando. Para encerrar, use Parar coleta. Esperas por limite da API aparecem na fase; os limites e a prioridade dos favoritos continuam iguais.

No Radar, /radar/buscas/fila.php exibe cartões de reservas ativas e identifica o coletor por ID e nome também na linha da fila. Os contadores recebidos/aceitos/novos vêm do servidor. A tela atualiza a cada 15 segundos; a fase remota chega pelo heartbeat, portanto não é instantânea. Clientes antigos continuam funcionando, mas não enviam o detalhamento novo. Reservas expiradas não aparecem como ativas.

O heartbeat aceita progresso_tarefas opcional (até oito tarefas); cada atualização exige reserva vigente pertencente ao coletor autenticado. A telemetria não renova lease nem altera os contadores confirmados. Contrato permanece 1. Novas tarefas DJEN podem trazer descricao opcional do favorito; tarefas antigas usam os campos existentes.

## Atualizar o outro computador

1. No PC1, clique em Parar coleta e aguarde; feche o Atlas.
2. Instale atlas-coletor_0.2.1_ubuntu24.04_amd64.deb pelo instalador do Ubuntu 24.04 amd64.
3. Abra ATLAS — Coletor Distribuído pelo menu. Mantenha o .env existente e a chave vigente. Clique em Conectar e iniciar.
4. Confira alvo, fase e contadores no aplicativo e nome do coletor na fila do Radar. Se não houver tarefa, Aguardando tarefas é normal.

Pacote e SHA-256 locais em /home/justisoft/Downloads/atlas-coletor/. A branch de desenvolvimento oferece artifact no GitHub Actions; ainda não existe Release desta versão. Não executar CLI/serviço antigo junto com a GUI.

## Validação e reprodução

Atlas: 81 testes aprovados, incluindo paginação antes do primeiro lote, confirmação após resposta, heartbeat e estados reais Qt offscreen. Radar: 112 verificações aprovadas (progresso 14, servidor 47, administração 41, Authorization 10). Consulta de reservas medida em 2,18 ms com duas tarefas; não consulta processos. Não foi feita coleta real, instalação no PC1, nem teste visual interativo no desktop do usuário.

O Radar neste servidor não possui Git. A integração PHP aplicada está registrada no repositório Atlas em integracoes/radar/progresso-coletores.patch, com caminhos relativos à raiz do Radar. O patch é para auditoria/replicação; NÃO reaplicar no servidor já atualizado. Revisar com git apply --check em outra cópia compatível antes de aplicar. Nenhuma migração é necessária.
