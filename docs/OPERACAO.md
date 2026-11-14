# Operação e diagnóstico

## Ver o que o coletor está fazendo
- Linux (serviço): `journalctl -u atlas-worker -f`. Sem serviço: saída do terminal. Arquivo: `~/.local/share/atlas-worker/logs/worker.log` (Windows: `%LOCALAPPDATA%\atlas-worker\logs`). O token nunca aparece nos logs.
- No Radar: **Administração → Coletores** (situação, último sinal, tarefa atual e há quanto tempo, CPU/memória, produtividade da última hora, erros) e **Buscas → Fila de monitoramento**.

## Situações comuns
| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `verificar` sai com 4 | Chave inválida, revogada ou de outro coletor | Criar nova chave no Radar e rodar `scripts/instalar-linux.sh --forcar-config` |
| `verificar` sai com 5 | Servidor inacessível / TLS inválido | Conferir a URL (HTTPS), a rede e o relógio do computador |
| `verificar` sai com 3 | Contrato diferente do servidor | `scripts/atualizar-linux.sh` |
| Aparece "pausado" | Alguém pausou o coletor no Radar | Retomar na tela Coletores |
| Muitas esperas / "fonte" nos erros | A fonte limitou (429) ou está fora do ar | Normal: o limite é global e o servidor aplica espera crescente. Nada a fazer |
| Tarefa "abandonada (reserva perdida)" | O computador ficou sem rede por mais de 10 min | Normal: o servidor reatribuiu; nada foi duplicado |
| Computador reiniciou no meio de uma tarefa | — | Ao subir, o coletor tenta retomar; se a reserva venceu, descarta e pede outra |

## Parar com segurança
`sudo systemctl stop atlas-worker` (ou Ctrl+C): a tarefa em curso é devolvida e o servidor a recupera ao vencer a reserva.

## Estado local
`~/.local/share/atlas-worker/tarefas/*.json`: só a tarefa em curso e os lotes que o servidor já confirmou. O servidor é a fonte da verdade; apagar essa pasta é seguro (a tarefa volta pela reserva).

## Revogar um computador
No Radar, revogue a chave dele (Administração → API) ou **Desativar** na tela Coletores. A chave revogada deixa de funcionar na próxima chamada.
