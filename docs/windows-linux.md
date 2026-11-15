# Instaladores Windows e Linux

A versão 0.2.4 introduz instalador Windows x64 por usuário (Windows 10/11), com Python e Qt incluídos e atalho no menu Iniciar. O Linux continua com pacote Ubuntu 24.04 amd64. O Windows grava configuração em AppData/Roaming/atlas-worker e dados em AppData/Local/atlas-worker, fora do aplicativo; configurações antigas são preservadas. A inicialização na sessão é opcional na interface.

O atualizador verifica Ed25519, tamanho, SHA-256, versão, sistema e arquitetura antes de executar o instalador. Windows usa manifest-windows.json/sig; Linux mantém manifest.json/sig para compatibilidade com 0.2.2/0.2.3. Antes de atualizar, o motor termina a tarefa corrente. O instalador aguarda a saída do processo e recusa substituir arquivos com outro Atlas aberto. Nenhuma tarefa é encerrada à força.

O workflow compila nativamente em Ubuntu e Windows, executa testes e instala/reinstala/desinstala o EXE em runner Windows. Só publica após os dois jobs passarem. O instalador inicial não possui certificado Authenticode; o Windows pode exibir aviso de editor desconhecido. A assinatura Ed25519 protege as atualizações do Atlas.

No PC2: baixar o EXE oficial, executar, abrir Atlas no menu Iniciar, informar URL/identificador/chave exclusivos do PC2 gerados no Radar e clicar em Conectar e iniciar. Não copiar a chave de outro coletor. A chave pública DataJud já vem preenchida.
