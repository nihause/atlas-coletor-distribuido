# Favoritos: coleta diária e teto de 10 mil — 16/11/2026

## Regra vigente
Cada nova tarefa da fila cobre exatamente uma data de disponibilização: início igual ao fim, para partes, advogados e comarcas/órgãos favoritos. Configurações antigas de 7/30 dias são ignoradas na reserva; não é necessário zerar os dados. Depois da confirmação, o checkpoint avança um dia. Tarefas já reservadas não são reescritas.

A documentação oficial (`https://comunicaapi.pje.jus.br/swagger/djen.yml`, consultada em 16/11/2026) aceita datas `yyyy-mm-dd`, sem filtro por hora, e informa teto de 10 mil nas pesquisas textuais/OAB. Não se adicionam horas a campos de data: isso não comprovaria uma divisão válida.

## Divisão sem perder filtros
`djen_paginar` (PHP) e o código novo do coletor Python detectam o teto tanto no count inicial quanto ao receber 10 mil registros: em algumas respostas count conta só a página. A amostra que atingiu o teto é descartada e a consulta é refeita por partições, sem pedir página 101 daquela consulta:
1. Se ainda houver mais de uma data, separar as datas (Python já envia cada dia separadamente, inclusive em tarefas antigas).
2. Se não estiver restrita a um tribunal, usar a lista oficial `/api/v1/comunicacao/tribunal`, aceitando formato plano ou agrupado por UF e removendo siglas repetidas. Não se usa o catálogo local amostrado como prova de cobertura nacional.
3. Se o tribunal/dia ainda atingir o teto, separar diário (`D`) e edital (`E`), preservando nome, OAB, órgão e demais filtros.
4. Se a folha tribunal/dia/meio continuar saturada, interromper com erro explícito; não confirmar o checkpoint nem declarar a amostra como completa. A alternativa por caderno oficial está aguardando autorização específica solicitada ao usuário. Nenhum caderno foi ligado/ampliado.

As partições podem voltar a somar mais de 10 mil no total; o teto vale para cada consulta. Um total agregado grande não é prova de truncamento se todas as partições terminaram corretamente.

## Compatibilidade e situação de instalação
O servidor Radar já entrega tarefas diárias, usa o paginador PHP novo e recusa confirmação de coletor antigo com volume declarado de 10 mil ou mais sem a confirmação adicional `particoes_verificadas`. Esse campo é enviado pelo coletor novo somente após terminar todas as partições. O contrato continua 1: campo adicional opcional e sem alteração incompatível de autenticação/reserva/resultado.

**O código Python foi atualizado e testado, mas não foi empacotado, publicado nem instalado nos PCs.** Os aplicativos antigos recebem o dia único do servidor, mas não ganham a divisão interna por tribunal/meio sem atualização. Em caso de saturação, podem falhar e precisar da versão nova. A proteção do servidor depende do volume declarado pelo aplicativo; ela não consegue detectar sozinha um aplicativo antigo que devolva menos itens do que a fonte anunciou. Não se afirma garantia de completude dos aplicativos antigos.

## Validação e custo
- PHP: 49 verificações do servidor, 30 de rendimento/completude, 19 de partições e 19 de progresso: 117 aprovadas, em tabelas temporárias/fontes simuladas.
- Python no repositório real: 106 testes aprovados e 1 específico de Windows omitido; segredos, cliente, fila, paginação, interface e progresso na suíte. O teste gráfico precisou atualizar o servidor simulado para o novo dia único; a execução intermediária com a fixture antiga excedeu seu tempo e abortou Qt. Execução final completa aprovada.
- Casos novos: configuração antiga de 30 dias ainda gera um dia; continuidade de 90 dias sem lacunas; lista oficial agrupada e duplicada; divisão por diário/edital sem perder nome/data; count por página, teto detectado na página 100 sem pedir 101; falha intermediária; total maior que página curta; folha saturada sem confirmação.
- Exemplo simulado de 90 dias vazios: antes a janela adaptativa podia fazer 5 consultas; agora faz 90 consultas diárias. É uma escolha explícita por dias isolados, sem promessa de acelerar todo o histórico. Ritmo global e concorrência existentes não foram aumentados.
- Não testados consultas reais de favoritos com 10 mil, recuperação ponta a ponta em produção, instalação nos PCs, Windows físico, erro 500 real nem produtividade sustentada. Somente Swagger e lista pública de tribunais foram consultados na rede, sem nomes de favoritos.

## Operação e reversão
Backup dos arquivos substituídos: `/home/justisoft/backups/radar-codigo/diario-20261116-190604` (subpastas radar e worker). Não se iniciou coletor duplicado, reiniciou serviço, alterou agendamento, liberou tarefa antecipadamente ou mudou o checkpoint. As próximas execuções naturais carregam as regras novas. Reverter os arquivos exige preservar alterações posteriores e não muda os dados já gravados. Preparação isolada dos testes em `/tmp/radar-diario-MkMfs4`.
