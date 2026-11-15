# Chave pública padrão do DataJud — 0.2.3

O Atlas preenche o campo DataJud com a chave pública compartilhada pelo CNJ. Fonte oficial conferida em 15/11/2026: https://datajud-wiki.cnj.jus.br/api-publica/acesso/.

A constante em datajud_public.py é intencionalmente pública; não é uma credencial privada do Radar nem de usuário. Essa inclusão foi solicitada expressamente pelo usuário. A regra de não versionar segredos continua valendo para tokens Radar, chaves privadas de assinatura e credenciais particulares.

Settings usa o padrão quando DATAJUD_API_KEY está ausente, vazio ou somente com espaços. A configuração gráfica mostra o padrão quando o valor carregado está vazio. O arquivo .env não é reescrito apenas ao abrir a janela; salvar mantém os demais campos/extras. Qualquer chave personalizada não vazia prevalece.

O CNJ pode alterar a chave pública. O campo continua editável para substituição, sem atualização silenciosa por scraping e sem alterar limites das fontes. Não houve consulta/coleta real ao DataJud para este ajuste; a chave foi obtida na documentação oficial.

Atualize 0.2.2 pela aba Atualizações para obter a correção 0.2.3. Instalações antigas precisam primeiro obter o atualizador assinado conforme ATUALIZACOES.md.
