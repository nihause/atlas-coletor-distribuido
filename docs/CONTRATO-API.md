# Contrato da API de coletores — versão 1

Servidor: Radar. Base: `https://SERVIDOR/radar/api/v1/coletores.php/<rota>`. Autenticação: `Authorization: Bearer <chave>` (uma por computador; permissão `ingestao`). Cabeçalho `X-Contrato: 1`: contrato diferente recebe 400 `contrato_incompativel` (atualize o coletor). Respostas: `{"contrato":1,"dados":{...}}`; erros: `{"erro":{"codigo","mensagem"}}`.

| Rota | Método | Corpo (resumo) | Resposta (resumo) |
|---|---|---|---|
| `registrar` | POST | `coletor, nome, cpus, ram_mb, sistema, hostname, versao, max_concorrencia` | configuração (abaixo). A chave fica vinculada ao coletor: outra chave recebe 403 |
| `heartbeat` | POST | `coletor, cpu_pct, mem_pct, tarefa_id, erros, versao` | configuração (traz o `comando`) |
| `configuracao` | GET | `?coletor=ID` | configuração |
| `tarefas/reservar` | POST | `coletor, tipos[]` | `{tarefa:{id,tipo,lease_token,lease_ate,params}\|null, comando}` |
| `tarefas/renovar` | POST | `coletor, tarefa_id, lease_token, progresso` | `{lease_ate, comando}`; 409 se a reserva foi perdida |
| `resultados` | POST | `coletor, tarefa_id, lease_token, chave, itens[]` | `{persistido:true, duplicado, itens, aceitos, desconhecidos, rejeitados}` |
| `tarefas/concluir` | POST | `coletor, tarefa_id, lease_token, resumo{}` | `{concluida:true}`; 409 se os itens declarados diferem dos confirmados |
| `tarefas/falhar` | POST | `coletor, tarefa_id, lease_token, erro, retentavel, sem_penalidade` | `{registrada, status}` |
| `limites/vaga` | POST | `coletor, fonte` (`djen`\|`datajud`) | `{espera_s, pausa, limite_min}`; o coletor espera `espera_s` e então faz UMA requisição |
| `limites/resultado` | POST | `coletor, fonte, http, ms, retry_after` | `{pausa_s}` |

**Configuração:** `{contrato, comando: continuar|pausar|parar, max_concorrencia, intervalo_heartbeat_s, lease_s, lote_itens, tipos[], limites{datajud_min, djen_min}}`.

**Garantias:**
- *Reserva atômica*: a mesma tarefa (e o mesmo favorito) nunca vai para dois coletores; reserva vence em 10 min sem renovação e a tarefa volta à fila do último checkpoint.
- *Idempotência*: `resultados` é idempotente por `(tarefa, chave)`; reenviar devolve `duplicado:true` sem regravar. A chave de lote do `djen_janela` inclui o hash dos ids do lote.
- *Confirmação durável*: `persistido:true` só é devolvido depois do commit no banco. A tarefa só conclui se `resumo.itens_enviados` for igual ao total confirmado.
- *Cerca*: com `lease_token` antigo, o servidor responde 409; o coletor abandona a tarefa sem reportar falha.
- *Pausa/desativação*: `comando=pausar` → o coletor devolve a tarefa atual com `sem_penalidade:true` e não pede outra; `parar` → encerra.

## Tarefas
**`djen_janela`** — `params`: `favorito{tipo,ref_id}`, `de`, `ate`, `consultas[{params, filtro}]`, `janela_dias`, `base_dias`. O coletor pagina cada consulta (100 por página) no período, divide o período se a fonte acusar 10 mil ou mais, remove repetidos, aplica `filtro` (partes e advogados por nome: sem homônimos) e envia `itens: [{q: índice_da_consulta, item: <comunicação do DJEN>}]`. O servidor reaplica o filtro e o período. `resumo`: `itens_enviados, total_itens, paginas, dividida, duracao_s`.

**`datajud_lote`** — `params`: `tribunal, alias, cnjs[≤50], ids[]`. O coletor consulta em lote (resposta incompleta divide o lote; 429/5xx/tempo esgotado não reduzem o lote), normaliza e envia `itens: [registros]`. `resumo`: `encontrados[], nao_localizados[], itens_enviados`. Não localizado é reconsultado em 1, 7, 30 e 90 dias.

## Compatibilidade
Mudança incompatível = novo número de contrato. O servidor recusa contrato desconhecido com mensagem clara; o `verificar` detecta e a atualização (`scripts/atualizar-*`) resolve.
