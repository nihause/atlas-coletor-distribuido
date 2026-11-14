# Diário de mudanças feitas por IA

Mais recente primeiro. Regras e formato em `AGENTS.md`.

## 2026-11-14 · Claude / Sonnet 5.5 · Criação do projeto
- **Pedido:** criar o coletor distribuído em Python, separado do Atlas/Radar, com servidor central distribuindo tarefas a vários computadores, pronto para o GitHub.
- **Mudou:** projeto inicial: `src/atlas_worker/` (config, client, worker, heartbeat, checkpoint, metrics, coletores DJEN/DataJud/cadernos), `tests/` (42 testes), instaladores Linux/Windows, README, `docs/CONTRATO-API.md`, `docs/OPERACAO.md`. Lado servidor no Radar: `radar/lib/coletores.php`, `radar/api/v1/coletores.php`, `radar/admin/coletores.php`, tabelas `coletor_tarefas` e colunas novas em `coletores`.
- **Testado:** 42 testes Python sem rede (servidor e fontes simulados); no Radar `tests/coletores.php` (47) e `tests/coletores-http.php` (8, coletor Python real contra a rota real, sem reservar tarefas de produção). NÃO testado: tarefas reais no DJEN/DataJud com este coletor, segundo computador de verdade, scripts do Windows.
- **Atenção:** nada foi implantado em outro computador. Os quatro trabalhadores PHP continuam como estão.
