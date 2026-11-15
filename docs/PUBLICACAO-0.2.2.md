# Publicação validada — Atlas 0.2.2

- Release público: https://github.com/nihause/atlas-coletor-distribuido/releases/tag/v0.2.2
- Instalador: https://github.com/nihause/atlas-coletor-distribuido/releases/download/v0.2.2/atlas-coletor_0.2.2_ubuntu24.04_amd64.deb
- SHA-256: `d26165ee1ab066e81d5bee4b7dc683d28ded8468332435a5bbaccdda009baa51`
- Arquivos oficiais: instalador .deb, .deb.sha256, manifest.json e manifest.sig.
- Workflow: https://github.com/nihause/atlas-coletor-distribuido/actions/runs/43727933187 — sucesso nos dois jobs, inclusive assinatura e publicação.
- Tag v0.2.2 aponta ao commit 288744e2f72ee3bd3afb75e6eca20b65193e99ed da main. Não foi sobrescrita tag ou Release.

## Verificação executada

98 testes Python/Qt repetidos antes da tag. pip check aprovado, pip-audit sem vulnerabilidades conhecidas e Gitleaks sem segredos no histórico e arquivos. Actions repetiu testes/auditorias antes de gerar e assinar o pacote com a chave existente, sem rotação.

Release consultado na API pública, sem token: publicado, estável, tag correta, quatro arquivos esperados. O cliente real da versão 0.2.2, simulando versão instalada 0.2.1, identificou a atualização, baixou o pacote e validou assinatura Ed25519 com chave pública incorporada, tamanho e SHA-256. O arquivo .sha256 público também correspondeu. A consulta simulando 0.2.2 não ofereceu reinstalação/downgrade.

Metadados Debian confirmaram atlas-coletor, 0.2.2 e amd64; pacote contém atalho Ubuntu e executável, sem .env. CLI e GUI do pacote publicado foram conferidas fora do venv com configuração isolada. Instalação segura, preservação do .env e falhas de instalação são testadas por simulação; nenhuma instalação administrativa real foi executada.

## Computador consulta

No Ubuntu 24.04 amd64, clique em Parar coleta, aguarde e feche o Atlas. Baixe o instalador pelo link oficial acima e abra no instalador gráfico do Ubuntu. Instale, reabra o Atlas pelo menu, mantenha .env/chave existentes e clique em Conectar e iniciar. Não precisa copiar arquivos de outro computador nem informar token GitHub. A partir de 0.2.2, futuras versões usam a aba Atualizações.

Não foi usado SSH, sudo ou coleta de produção. Não foram testados instalação real no consulta, atualização completa entre versões instaladas, reinício/reconexão remota, GNOME/bandeja/autostart real ou Windows. A publicação está validada; a instalação remota ainda depende da ação do usuário.
