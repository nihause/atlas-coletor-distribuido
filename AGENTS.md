# Regras para qualquer IA (Claude, Codex, etc.) neste projeto

Projeto: `atlas-coletor-distribuido`, worker Python que serve ao Radar (`/var/www/html`, PHP/MySQL) e ao Atlas (`/home/justisoft/atlas`, FastAPI/PostgreSQL).

## Documentar o que fizer
Ao terminar qualquer mudança, acrescente uma entrada **no topo** de `docs/LOG-IA.md` (crie se não existir) com: `## AAAA-MM-DD · <IA/modelo> · título`, e as linhas **Pedido**, **Causa / motivo**, **Mudou**, **Testado** (diga o que NÃO foi testado) e **Atenção**. Não apague entradas antigas. Registre também em `docs/LOG-IA.md` do Radar quando mexer no servidor. Diga ao usuário, no fim, o que mudou e o que não foi testado. Idioma: português do Brasil.

## Regras do projeto
- **Nunca** grave token, senha ou chave em código, testes, logs, documentação ou commit. `.env` fica fora do Git. Teste `tests/test_cli_checkpoint.py::test_nenhum_segredo_no_repositorio` deve passar.
- O worker **não acessa o banco**: só a API do Radar (contrato em `docs/CONTRATO-API.md`). Mudança incompatível na API = novo número de contrato (`atlas_worker.CONTRATO`) e ajuste nos dois lados.
- Uma tarefa só termina quando o servidor confirma; reenviar é sempre seguro (idempotência). Perda de reserva (409) = abandonar sem reportar falha.
- O limite de requisições às fontes é **global** e vem do servidor (`limites/vaga`). Não crie limite local que o contorne e **não** implemente contorno de CAPTCHA, bloqueio, autenticação ou limite de fonte.
- Escopo de coleta: favoritos. A descoberta geral permanece desligada; não habilite sem ordem do usuário.
- Registros sigilosos (`nivel_sigilo > 0`) não saem do computador.
- Testes sem rede: servidor e fontes simulados (`tests/fakes.py`). Rode `.venv/bin/python -m pytest -q` antes de concluir. Os scripts do Windows não são testados automaticamente: diga isso.
- Ações que usam sudo, mexem em produção, enviam dados para fora ou trocam senhas: **pergunte antes**. Não implante em outro computador sem o usuário pedir.
- Mudanças no servidor (PHP) ficam no Radar, com testes em `tests/coletores*.php` (tabelas temporárias).
