# Chave pública padrão do DataJud — 0.2.3

O Atlas preenche o campo DataJud com a chave pública compartilhada pelo CNJ. Fonte oficial conferida em 15/11/2026: https://datajud-wiki.cnj.jus.br/api-publica/acesso/.

A constante em datajud_public.py é intencionalmente pública; não é uma credencial privada do Radar nem de usuário. Essa inclusão foi solicitada expressamente pelo usuário. A regra de não versionar segredos continua valendo para tokens Radar, chaves privadas de assinatura e credenciais particulares.

Settings usa o padrão quando DATAJUD_API_KEY está ausente, vazio ou somente com espaços. A configuração gráfica mostra o padrão quando o valor carregado está vazio. O arquivo .env não é reescrito apenas ao abrir a janela; salvar mantém os demais campos/extras. Qualquer chave personalizada não vazia prevalece.

O CNJ pode alterar a chave pública. O campo continua editável para substituição, sem atualização silenciosa por scraping e sem alterar limites das fontes. Não houve consulta/coleta real ao DataJud para este ajuste; a chave foi obtida na documentação oficial.

Atualize 0.2.2 pela aba Atualizações para obter a correção 0.2.3. Instalações antigas precisam primeiro obter o atualizador assinado conforme ATUALIZACOES.md.

Release validado: https://github.com/nihause/atlas-coletor-distribuido/releases/tag/v0.2.3. O atualizador consultou e baixou sem token, simulando versão instalada 0.2.2, e validou a assinatura Ed25519 e SHA-256. Actions da tag: 43728508204, sucesso. SHA-256 do pacote: `4586aaad44d30c3eb087af80f7f91a9e585457a2a328e8d33318d504b36a8cac`.
