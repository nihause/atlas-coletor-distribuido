"""Coletores de fonte: paginação, filtro de homônimos, divisão de período, limite global, lote do DataJud, cadernos."""
import hashlib
import json
import zipfile
from datetime import date

import httpx
import pytest

from atlas_worker.client import RadarClient
from atlas_worker.collectors import cadernos
from atlas_worker.collectors.datajud import DataJud, LoteIncompleto
from atlas_worker.collectors.djen import Djen, ErroDjen, dividir
from atlas_worker.collectors.limite import FonteIndisponivel, Limitador
from atlas_worker.tasks import ParamsDatajudLote, ParamsDjenJanela
from tests.fakes import FakeFontes, FakeRadar, Relogio, doc, item
from tests.test_config_client import _cfg


def _djen(fontes, srv, r, batch=100):
    cl = RadarClient(_cfg(), transport=srv.transporte(), sleep=r.dormir)
    return Djen(Limitador(cl, "djen", r.dormir), httpx.AsyncClient(transport=fontes.transporte()), batch), cl


def _params(**kw):
    p = {"favorito": {"tipo": "parte", "ref_id": 1}, "de": "2026-11-01", "ate": "2026-11-07",
         "consultas": [{"params": {"nomeParte": "Banco Exemplo"}, "filtro": {"tipo": "parte", "termo_norm": "BANCO EXEMPLO"}}]}
    p.update(kw)
    return ParamsDjenJanela.model_validate(p)


async def _tudo(d, p):
    return [x async for x in d.janela(p)]


async def test_pagina_ate_a_ultima_filtra_homonimos_e_remove_repetidos():
    r, srv, f = Relogio(), FakeRadar(Relogio()), FakeFontes()
    srv.r = r
    f.djen["Banco Exemplo"] = [item(i) for i in range(1, 251)] + [item(900, "PESSOA HOMONIMA")] + [item(5)]    # 250 válidos, 1 homônimo, 1 repetido
    d, cl = _djen(f, srv, r)
    lotes = await _tudo(d, _params())
    ids = [x["item"]["id"] for _, l in lotes for x in l]
    assert len(ids) == 250 and len(set(ids)) == 250 and 900 not in ids
    assert d.paginas == 3 and f.requisicoes["djen"] == 3
    assert [len(l) for _, l in lotes] == [100, 100, 50]
    await cl.aclose()


async def test_chave_do_lote_muda_se_o_conteudo_mudar():
    r, srv, f = Relogio(), FakeRadar(Relogio()), FakeFontes()
    srv.r = r
    f.djen["Banco Exemplo"] = [item(i) for i in range(1, 11)]
    d, cl = _djen(f, srv, r)
    k1 = [k for k, _ in await _tudo(d, _params())]
    d2, _ = _djen(f, srv, r)
    assert k1 == [k for k, _ in await _tudo(d2, _params())]      # mesmo conteúdo, mesma chave (reenvio é reconhecido)
    f.djen["Banco Exemplo"].append(item(11))
    d3, _ = _djen(f, srv, r)
    assert k1 != [k for k, _ in await _tudo(d3, _params())]       # conteúdo novo nunca é mascarado por um lote antigo
    await cl.aclose()


async def test_periodo_dividido_quando_a_fonte_acusa_volume_alto():
    assert dividir(date(2026, 11, 1), date(2026, 11, 7)) == [(date(2026, 11, 1), date(2026, 11, 4)), (date(2026, 11, 5), date(2026, 11, 7))]
    assert dividir(date(2026, 11, 1), date(2026, 11, 1)) == []
    r, srv, f = Relogio(), FakeRadar(Relogio()), FakeFontes()
    srv.r = r
    f.djen["Banco Exemplo"] = [item(1, dia="2026-11-02"), item(2, dia="2026-11-06")]
    f.djen_count_fake = 10_000
    d, cl = _djen(f, srv, r)
    assert len([x for _, l in await _tudo(d, _params()) for x in l]) == 2 and d.dividida
    await cl.aclose()


async def test_paginacao_que_repete_e_erro_e_fonte_fora_do_ar_e_fonte_indisponivel():
    r, srv, f = Relogio(), FakeRadar(Relogio()), FakeFontes()
    srv.r = r
    f.djen["Banco Exemplo"] = [item(i) for i in range(1, 201)]
    f.djen_repete = True
    d, cl = _djen(f, srv, r)
    with pytest.raises(ErroDjen):
        await _tudo(d, _params())
    f.djen_repete, f.djen_http = False, 429
    d, _ = _djen(f, srv, r)
    with pytest.raises(FonteIndisponivel):
        await _tudo(d, _params())
    rel = [c for rota, c in srv.chamadas if rota == "limites/resultado"]
    assert rel and rel[-1]["http"] == 429 and rel[-1]["retry_after"] == 30       # o 429 e o Retry-After chegam ao servidor
    await cl.aclose()


def test_parametros_de_consulta_nao_permitidos_sao_recusados():
    with pytest.raises(Exception):
        _params(consultas=[{"params": {"nomeParte": "x", "url": "http://malicioso"}, "filtro": None}])
    with pytest.raises(Exception):
        _params(de="2026-11-09", ate="2026-11-01")


async def test_limite_global_vale_para_todos_os_trabalhadores_somados():
    """Quatro limitadores (quatro computadores) disputando a mesma fonte: o servidor dá um ritmo só."""
    r = Relogio(); srv = FakeRadar(r, {"djen": 15, "datajud": 60})
    import asyncio
    clientes = [RadarClient(_cfg(worker_name=f"coletor-0{i}"), transport=srv.transporte(), sleep=r.dormir) for i in range(1, 5)]
    lims = [Limitador(c, "djen", r.dormir) for c in clientes]

    async def uma(resp=None):
        from atlas_worker.collectors.limite import Resposta
        async def fazer(): return Resposta(200, {})
        return await asyncio.gather(*[l.requisitar(fazer) for l in lims for _ in range(5)])

    await uma()
    v = sorted(srv.vagas["djen"])
    assert len(v) == 20
    gaps = [b - a for a, b in zip(v, v[1:])]
    assert min(gaps) >= 60 / 15 - 1e-6                      # 15/min no total, não 15/min por computador
    for c in clientes:
        await c.aclose()


async def test_espera_pela_pausa_do_servidor_e_desiste_se_for_longa():
    r = Relogio(); srv = FakeRadar(r)
    srv.pausa_ate["djen"] = r.t + 40
    c = RadarClient(_cfg(), transport=srv.transporte(), sleep=r.dormir)
    lim = Limitador(c, "djen", r.dormir)
    from atlas_worker.collectors.limite import Resposta
    async def ok(): return Resposta(200, {})
    await lim.requisitar(ok)
    assert r.t >= 1040                                       # esperou a pausa inteira
    srv.pausa_ate["djen"] = r.t + 10_000
    with pytest.raises(FonteIndisponivel):
        await lim.requisitar(ok)
    await c.aclose()


CNJ = lambda i: f"{i:020d}"  # noqa: E731


async def test_datajud_lote_encontrados_nao_localizados_e_sigilo():
    r, srv, f = Relogio(), FakeRadar(Relogio()), FakeFontes()
    srv.r = r
    f.datajud = {CNJ(1): doc(CNJ(1)), CNJ(2): doc(CNJ(2), sigilo=3)}
    cl = RadarClient(_cfg(), transport=srv.transporte(), sleep=r.dormir)
    dj = DataJud(Limitador(cl, "datajud", r.dormir), httpx.AsyncClient(transport=f.transporte()), "k")
    regs, nao = await dj.lote(ParamsDatajudLote(tribunal="TJPR", alias="api_publica_tjpr", cnjs=[CNJ(1), CNJ(2), CNJ(3)]))
    assert [x["numero_cnj"] for x in regs] == [CNJ(1)]       # o sigiloso não sai do computador
    assert nao == [CNJ(3)]                                   # o sigiloso existe: não é "não localizado"
    assert regs[0]["movimentos"][0]["codigo"] == 26 and regs[0]["assuntos"][0]["codigo"] == 1
    await cl.aclose()


async def test_datajud_429_e_timeout_nao_reduzem_o_lote_nem_viram_lote_incompleto():
    r, srv, f = Relogio(), FakeRadar(Relogio()), FakeFontes()
    srv.r = r
    f.datajud_http = [429]
    cl = RadarClient(_cfg(), transport=srv.transporte(), sleep=r.dormir)
    dj = DataJud(Limitador(cl, "datajud", r.dormir), httpx.AsyncClient(transport=f.transporte()), "k")
    with pytest.raises(FonteIndisponivel):
        await dj.lote(ParamsDatajudLote(tribunal="TJPR", alias="api_publica_tjpr", cnjs=[CNJ(i) for i in range(1, 51)]))
    assert f.requisicoes["datajud"] == 1                     # uma tentativa: a decisão de repetir é do servidor (pausa/backoff), não do lote
    await cl.aclose()


async def test_datajud_resposta_incompleta_divide_o_lote():
    r, srv = Relogio(), FakeRadar(Relogio())
    srv.r = r
    chamadas = []

    def tratar(req):
        cnjs = json.loads(req.content)["query"]["terms"]["numeroProcesso"]
        chamadas.append(len(cnjs))
        if len(cnjs) > 2:      # simula "total maior que o recebido" para lotes grandes
            return httpx.Response(200, json={"timed_out": False, "_shards": {"failed": 0}, "hits": {"total": {"value": 99, "relation": "eq"}, "hits": []}})
        return httpx.Response(200, json={"timed_out": False, "_shards": {"failed": 0}, "hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}})

    cl = RadarClient(_cfg(), transport=srv.transporte(), sleep=r.dormir)
    dj = DataJud(Limitador(cl, "datajud", r.dormir), httpx.AsyncClient(transport=httpx.MockTransport(tratar)), "k")
    regs, nao = await dj.lote(ParamsDatajudLote(tribunal="TJPR", alias="api_publica_tjpr", cnjs=[CNJ(i) for i in range(1, 5)]))
    assert chamadas == [4, 2, 2] and len(nao) == 4
    await cl.aclose()


async def test_datajud_resposta_com_falha_de_shard_e_incompleta():
    r, srv = Relogio(), FakeRadar(Relogio())
    srv.r = r
    t = httpx.MockTransport(lambda req: httpx.Response(200, json={"timed_out": True, "hits": {"total": {"value": 0}, "hits": []}}))
    cl = RadarClient(_cfg(), transport=srv.transporte(), sleep=r.dormir)
    dj = DataJud(Limitador(cl, "datajud", r.dormir), httpx.AsyncClient(transport=t), "k")
    with pytest.raises(LoteIncompleto):
        await dj.lote(ParamsDatajudLote(tribunal="TJPR", alias="api_publica_tjpr", cnjs=[CNJ(1)]))
    await cl.aclose()


def _zip(tmp_path, itens):
    p = tmp_path / "origem.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("TJPR-D-2026-11-13_1.json", json.dumps({"count": len(itens), "items": itens}))
    return p


async def test_caderno_baixa_confere_hash_e_nao_repete(tmp_path):
    origem = _zip(tmp_path, [{"id": 1, "nomeOrgao": "1ª Vara Cível de Testópolis", "destinatarios": [{"nome": "Maria"}]},
                              {"id": 2, "nomeOrgao": "Outra Vara", "destinatarios": [{"nome": "Banco Exemplo S.A."}]},
                              {"id": 3, "nomeOrgao": "Outra Vara", "destinatarios": [{"nome": "José"}], "destinatarioadvogados": [{"advogado": {"numero_oab": "012345", "uf_oab": "pr"}}]},
                              {"id": 4, "nomeOrgao": "Outra Vara", "destinatarios": [{"nome": "Ana"}]}])
    h = hashlib.sha256(origem.read_bytes()).hexdigest()
    n = {"v": 0}

    def tratar(req):
        n["v"] += 1
        return httpx.Response(200, content=origem.read_bytes())

    http = httpx.AsyncClient(transport=httpx.MockTransport(tratar))
    meta = {"sigla_tribunal": "TJPR", "data": "2026-11-13", "meio": "D", "versao": 1, "hash": h, "url": "https://x/c.zip"}
    arq = await cadernos.baixar(http, meta, tmp_path / "cadernos")
    await cadernos.baixar(http, meta, tmp_path / "cadernos")
    assert n["v"] == 1                                       # já íntegro: não baixa de novo
    achados = {i["id"] for i in cadernos.filtrar(arq, {"1A VARA CIVEL DE TESTOPOLIS".replace("1A", "A")} | {"A VARA CIVEL DE TESTOPOLIS"}, {"BANCO EXEMPLO"}, {"PR|12345"})}
    assert achados == {1, 2, 3}                              # órgão, parte e OAB favoritos; o resto nem sai do computador
    with pytest.raises(cadernos.CadernoCorrompido):
        await cadernos.baixar(http, {**meta, "hash": "0" * 64, "versao": 2}, tmp_path / "cadernos")
    assert not list((tmp_path / "cadernos").glob("*.tmp"))
    assert await cadernos.metadados(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))), "TJPR", "2026-11-14") is None
