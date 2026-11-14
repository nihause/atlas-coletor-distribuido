"""Fluxo completo do worker contra o servidor simulado: reserva, entrega em lotes, conclusão durável, reinício, perda de conexão,
resultados repetidos, perda de reserva, pausa, falhas, DataJud e quatro computadores ao mesmo tempo."""
import asyncio

import pytest

from tests.conftest import novo_worker
from tests.fakes import item, doc, TOKEN


def _itens(f, n, dia="2026-11-03"):
    f.djen["Banco Exemplo"] = [item(i, dia=dia) for i in range(1, n + 1)]


async def _rodar(w, c):
    await asyncio.wait_for(w.rodar(uma_rodada=True), 20)
    await c.aclose()


async def test_tarefa_djen_completa(cfg, mundo):
    r, srv, f = mundo
    _itens(f, 250)
    srv.adicionar_djen(1)
    w, c = novo_worker(cfg, mundo)
    await _rodar(w, c)
    t = srv.tarefas[1]
    assert t["status"] == "concluida" and t["itens"] == 250 and list(t["lotes"].values()) == [100, 100, 50]
    assert t["concluida"]["itens_enviados"] == 250 and t["concluida"]["paginas"] == 3
    assert all(v == 1 for v in srv.itens_gravados.values())                  # nenhum item gravado duas vezes
    assert w.ck.pendentes() == []                                            # estado local limpo ao concluir
    assert srv.coletores == {"coletor-01"} and any(rota == "heartbeat" for rota, _ in srv.chamadas)


async def test_concluir_so_depois_do_servidor_confirmar_todos_os_lotes(cfg, mundo):
    r, srv, f = mundo
    _itens(f, 30)
    srv.adicionar_djen(1)
    ordem = []
    orig_res, orig_con = srv._h_resultados, srv._h_tarefas_concluir
    srv._h_resultados = lambda c: (ordem.append("resultados"), orig_res(c))[1]
    srv._h_tarefas_concluir = lambda c: (ordem.append("concluir"), orig_con(c))[1]
    w, c = novo_worker(cfg, mundo)
    await _rodar(w, c)
    assert ordem == ["resultados", "concluir"]


async def test_resposta_perdida_depois_de_gravar_nao_duplica(cfg, mundo):
    """O servidor gravou, mas a resposta não chegou: o coletor reenvia o mesmo lote e o servidor o reconhece."""
    r, srv, f = mundo
    _itens(f, 40)
    srv.adicionar_djen(1)
    srv.resultados_perdidos = 1
    w, c = novo_worker(cfg, mundo)
    await _rodar(w, c)
    assert srv.tarefas[1]["status"] == "concluida" and srv.tarefas[1]["itens"] == 40
    assert all(v == 1 for v in srv.itens_gravados.values())
    assert sum(1 for rota, _ in srv.chamadas if rota == "resultados") == 2    # tentou duas vezes, gravou uma


async def test_perda_de_conexao_e_5xx_sao_absorvidos(cfg, mundo):
    r, srv, f = mundo
    _itens(f, 20)
    srv.adicionar_djen(1)
    w, c = novo_worker(cfg, mundo)
    await w.iniciar()
    srv.falha_na_rede, srv.responder_5xx = 2, 1
    await asyncio.wait_for(w.rodar(uma_rodada=True), 20)
    await c.aclose()
    assert srv.tarefas[1]["status"] == "concluida"


async def test_reinicio_retoma_sem_regravar_lotes_ja_confirmados(cfg, mundo, tmp_path):
    r, srv, f = mundo
    _itens(f, 250)
    srv.adicionar_djen(1)
    estado = tmp_path / "estado-reinicio"
    # 1ª execução: cai (computador desligado) depois do 1º lote confirmado
    w1, c1 = novo_worker(cfg, mundo, estado=estado)
    original = c1.resultados

    async def cai_no_segundo(tid, tok, chave, itens):
        if len(w1.ck.carregar(tid)) >= 1:
            raise asyncio.CancelledError()
        return await original(tid, tok, chave, itens)

    c1.resultados = cai_no_segundo
    await w1.iniciar()
    ex = asyncio.create_task(w1._executar(__import__("atlas_worker.tasks", fromlist=["Tarefa"]).Tarefa.model_validate(await _reservar(c1))))
    with pytest.raises(asyncio.CancelledError):
        await ex
    await c1.aclose()
    assert srv.tarefas[1]["status"] == "reservada" and srv.tarefas[1]["itens"] == 100          # parou com 1 lote gravado
    assert [t["id"] for t in __import__("atlas_worker.checkpoint", fromlist=["Checkpoint"]).Checkpoint(estado).pendentes()] == [1]
    # 2ª execução, mesmo diretório de estado (o computador voltou): retoma a mesma tarefa
    w2, c2 = novo_worker(cfg, mundo, estado=estado)
    await _rodar(w2, c2)
    t = srv.tarefas[1]
    assert t["status"] == "concluida" and t["itens"] == 250
    assert all(v == 1 for v in srv.itens_gravados.values())
    assert sum(1 for rota, _ in srv.chamadas if rota == "resultados") == 3          # 1 antes da queda + os 2 que faltavam; o 1º não foi reenviado


async def _reservar(client):
    return (await client.reservar(["djen_janela"]))["tarefa"]


async def test_reserva_perdida_abandona_sem_reportar_falha(cfg, mundo):
    r, srv, f = mundo
    _itens(f, 250)
    srv.adicionar_djen(1)
    w, c = novo_worker(cfg, mundo)
    original = c.resultados

    async def perde(tid, tok, chave, itens):
        res = await original(tid, tok, chave, itens)
        srv.expirar(1)       # o servidor expira a reserva e reatribui a tarefa
        srv.fila.clear()
        return res

    c.resultados = perde
    await _rodar(w, c)
    assert srv.tarefas[1]["status"] == "expirada" and srv.tarefas[1]["falhas"] == []      # não chamou "falhar" numa reserva que já não era sua
    assert w.ck.pendentes() == []


async def test_tarefa_expirada_e_reatribuida_a_outro_coletor_sem_duplicar(cfg, mundo, tmp_path):
    r, srv, f = mundo
    _itens(f, 120)
    srv.adicionar_djen(1)
    wa, ca = novo_worker(cfg, mundo, nome="coletor-A", estado=tmp_path / "a")
    ta = (await (await _iniciar(wa, ca)).reservar(["djen_janela"]))["tarefa"]
    await ca.resultados(ta["id"], ta["lease_token"], "0-x", [{"q": 0, "item": item(1)}])   # A grava um lote e some
    srv.expirar(1)
    wb, cb = novo_worker(cfg, mundo, nome="coletor-B", estado=tmp_path / "b")
    await _rodar(wb, cb)
    assert srv.tarefas[1]["coletor"] == "coletor-B" and srv.tarefas[1]["status"] == "concluida"
    with pytest.raises(Exception):
        await ca.renovar(1, ta["lease_token"])                                 # A acorda depois: cercado (409)
    await ca.aclose()


async def _iniciar(w, c):
    await w.iniciar()
    return c


async def test_pausa_pelo_servidor_devolve_a_tarefa_sem_penalidade(cfg, mundo):
    r, srv, f = mundo
    _itens(f, 250)
    srv.adicionar_djen(1)
    w, c = novo_worker(cfg, mundo)
    original = c.resultados

    async def pausa_depois_do_primeiro(tid, tok, chave, itens):
        res = await original(tid, tok, chave, itens)
        srv.estado = "pausado"
        await w.hb.uma_vez()          # o próximo heartbeat traz o comando
        return res

    c.resultados = pausa_depois_do_primeiro
    await _rodar(w, c)
    t = srv.tarefas[1]
    assert t["status"] == "devolvida" and t["falhas"][0]["sem_penalidade"] is True and t["itens"] == 100
    assert w.pausado is True


async def test_coletor_pausado_nao_pede_tarefa(cfg, mundo):
    r, srv, f = mundo
    srv.estado = "pausado"
    srv.adicionar_djen(1)
    w, c = novo_worker(cfg, mundo)
    await _rodar(w, c)
    assert 1 in [t["id"] for t in srv.fila] and srv.tarefas == {}


async def test_coletor_desativado_encerra(cfg, mundo):
    r, srv, f = mundo
    srv.estado = "desativado"
    w, c = novo_worker(cfg, mundo)
    await asyncio.wait_for(w.rodar(), 10)
    await c.aclose()
    assert w.parar.is_set() and srv.tarefas == {}


async def test_chave_revogada_encerra_sem_loop(cfg, mundo):
    r, srv, f = mundo
    srv.adicionar_djen(1)
    w, c = novo_worker(cfg, mundo)
    await w.iniciar()
    srv.token = "outra" * 8      # chave revogada depois do registro
    await asyncio.wait_for(w.rodar(), 10)
    await c.aclose()
    assert srv.tarefas == {}


async def test_fonte_fora_do_ar_reporta_falha_retentavel(cfg, mundo):
    r, srv, f = mundo
    _itens(f, 10)
    f.djen_http = 503
    srv.adicionar_djen(1)
    w, c = novo_worker(cfg, mundo)
    await _rodar(w, c)
    t = srv.tarefas[1]
    assert t["status"] == "falhou" and t["falhas"][0]["retentavel"] is True and "djen" in t["falhas"][0]["erro"].lower()
    assert t["itens"] == 0 and w.metrics.erros == 1


async def test_servidor_recusa_conclusao_com_itens_divergentes(cfg, mundo):
    r, srv, f = mundo
    _itens(f, 30)
    srv.adicionar_djen(1)
    w, c = novo_worker(cfg, mundo)
    original = c.concluir

    async def mente(tid, tok, resumo):
        return await original(tid, tok, {**resumo, "itens_enviados": resumo["itens_enviados"] + 1})

    c.concluir = mente
    await _rodar(w, c)
    t = srv.tarefas[1]
    assert t["concluida"] is None and t["status"] == "reservada" and t["falhas"] == []      # não foi dada como concluída; o servidor a recupera pela expiração
    assert w.ck.pendentes() == [] and t["itens"] == 30


async def test_tarefa_datajud_com_nao_localizados(cfg, mundo):
    r, srv, f = mundo
    cn = [f"{i:020d}" for i in range(1, 6)]
    f.datajud = {c: doc(c) for c in cn[:3]}
    srv.adicionar_datajud(9, cn)
    w, c = novo_worker(cfg, mundo)
    await _rodar(w, c)
    t = srv.tarefas[9]
    assert t["status"] == "concluida" and t["concluida"]["encontrados"] == cn[:3] and t["concluida"]["nao_localizados"] == cn[3:]
    assert t["itens"] == 3


async def test_datajud_sem_chave_e_recusado_sem_consultar(cfg, mundo):
    r, srv, f = mundo
    srv.adicionar_datajud(9, ["0" * 19 + "1"])
    w, c = novo_worker(cfg.model_copy(update={"datajud_api_key": __import__("pydantic").SecretStr("")}), mundo)
    await _rodar(w, c)
    assert srv.tarefas[9]["status"] == "falhou" and f.requisicoes["datajud"] == 0


async def test_quatro_computadores_ao_mesmo_tempo_sem_duplicar(cfg, mundo, tmp_path):
    r, srv, f = mundo
    f.djen["Banco Exemplo"] = [item(i) for i in range(1, 181)]
    for tid in range(1, 9):
        srv.adicionar_djen(tid)
    ws = [novo_worker(cfg, mundo, nome=f"coletor-0{i}", estado=tmp_path / f"w{i}") for i in range(1, 5)]
    await asyncio.wait_for(asyncio.gather(*[w.rodar(uma_rodada=True) for w, _ in ws]), 60)
    for _, c in ws:
        await c.aclose()
    assert srv.fila == [] and all(t["status"] == "concluida" for t in srv.tarefas.values()) and len(srv.tarefas) == 8
    por_coletor = {t["coletor"] for t in srv.tarefas.values()}
    assert len(por_coletor) >= 2                                              # o servidor distribuiu entre computadores
    assert all(v == 1 for v in srv.itens_gravados.values()) and len(srv.itens_gravados) == 8 * 180      # cada tarefa gravou seus itens uma vez
    vagas = sorted(srv.vagas["djen"])
    assert min(b - a for a, b in zip(vagas, vagas[1:])) >= 60 / 15 - 1e-6      # e o limite global foi respeitado pelos quatro
