# Operação e diagnóstico

## Interface gráfica Ubuntu

Abra **ATLAS — Coletor Distribuído** no menu. Configuração, teste de conexão, iniciar/parar/reiniciar e diagnóstico ficam na janela. Veja [Aplicativo Linux](APLICATIVO-LINUX.md). Para migrar um serviço antigo, pare-o antes de conectar pela interface; os dois modos não devem operar a mesma identidade/estado simultaneamente. O pacote não altera serviços existentes.


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

## Preparação local: início automático e registro de erros (17/11/2026)

Na versão de código preparada localmente, ao abrir a janela o coletor aguarda dez segundos. Clique, tecla, rolagem ou toque na janela cancela esse início; o botão **Conectar e iniciar** permanece disponível. Se uma operação interna estiver em andamento, o início espera sua conclusão. O parâmetro antigo `--start` continua aceito e também aguarda os dez segundos. O coletor usa exclusivamente as tarefas oferecidas pelo Radar; não liga descoberta geral ou caderno DJEN.

Novas configurações sugerem quatro tarefas simultâneas; configurações existentes não são sobrescritas. A concorrência efetiva respeita a configuração local, o máximo de cada coletor no Radar, limites globais por tipo, disponibilidade de tarefas e cotas das fontes. Não há garantia de quatro consultas simultâneas quando não há tarefas disponíveis ou o servidor impõe limites menores.

Os erros são gravados em `logs/erros.jsonl` dentro do diretório de dados do coletor (Linux: `~/.local/share/atlas-worker`; Windows: `%LOCALAPPDATA%\\atlas-worker`, salvo configuração diferente). Cada linha é um JSON com data UTC, nível, origem, versão, mensagem, número da tarefa quando identificado e detalhes. O arquivo gira após 10 MiB, com cinco cópias; credenciais conhecidas são ocultadas. Não há envio automático ao Radar: é um arquivo local para análise, além da exportação de diagnóstico existente. Nomes e números processuais eventualmente presentes em mensagens continuam sendo dados sensíveis; compartilhe conscientemente.

Código preparado apenas na árvore local: não foi publicado, empacotado, instalado nos computadores nem ativado no servidor. A complementação e a disponibilidade de quatro tarefas de DataJud dependem da fila e dos limites configurados no Radar; este ajuste não amplia o escopo dos favoritos nem cria reconsultas.
