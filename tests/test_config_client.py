"""Configuração segura e cliente: autenticação, TLS, contrato, repetição e confirmação durável."""
import logging

import httpx
import pytest
from pydantic import ValidationError

from atlas_worker.client import LeaseLost, NotFound, RadarClient, Rejected, ServerUnavailable, Unauthorized
from atlas_worker.config import Settings
from atlas_worker.logging_config import RedactFilter
from tests.fakes import TOKEN, FakeRadar, Relogio


def _cfg(**kw):
    base = dict(radar_api_url="https://s.exemplo.com/api", worker_name="coletor-01", worker_token=TOKEN, _env_file=None)
    base.update(kw)
    return Settings(**base)


def test_exige_https_fora_de_teste_local():
    with pytest.raises(ValidationError):
        _cfg(radar_api_url="http://s.exemplo.com/api")
    with pytest.raises(ValidationError):
        _cfg(radar_api_url="http://s.exemplo.com/api", allow_insecure_http=True)      # http só em endereço local
    assert _cfg(radar_api_url="http://127.0.0.1:8000/api", allow_insecure_http=True).base_url.startswith("http://127.0.0.1")


def test_token_nome_e_limites_validados():
    with pytest.raises(ValidationError):
        _cfg(worker_token="")
    with pytest.raises(ValidationError):
        _cfg(worker_name="x")
    with pytest.raises(ValidationError):
        _cfg(worker_name="com espaço")
    with pytest.raises(ValidationError):
        _cfg(max_concurrency=99)
    assert "WORKER_TOKEN" not in repr(_cfg()) and TOKEN not in repr(_cfg())      # SecretStr: não vaza no repr


def test_token_nunca_aparece_no_log(caplog):
    f = RedactFilter([TOKEN])
    rec = logging.LogRecord("x", logging.INFO, "", 0, f"Authorization: Bearer {TOKEN}", (), None)
    f.filter(rec)
    assert TOKEN not in rec.getMessage() and "***" in rec.getMessage()


async def _cliente(srv, r, **kw):
    return RadarClient(_cfg(**kw), transport=srv.transporte(), sleep=r.dormir)


async def test_envia_credencial_e_contrato():
    r = Relogio(); srv = FakeRadar(r)
    c = await _cliente(srv, r)
    out = await c.registrar({"nome": "pc"})
    assert out["contrato"] == 1 and srv.coletores == {"coletor-01"}
    await c.aclose()


async def test_chave_errada_e_nao_repete():
    r = Relogio(); srv = FakeRadar(r)
    c = await _cliente(srv, r, worker_token="outra" * 8)
    with pytest.raises(Unauthorized):
        await c.registrar({})
    assert len(srv.chamadas) == 0 and r.dormidas == []      # 401 não é repetido
    await c.aclose()


async def test_repete_rede_e_5xx_com_espera_crescente():
    r = Relogio(); srv = FakeRadar(r); srv.falha_na_rede = 2; srv.responder_5xx = 1
    c = await _cliente(srv, r)
    assert (await c.heartbeat({}))["comando"] == "continuar"
    assert len(r.dormidas) == 3 and r.dormidas[1] > r.dormidas[0] * 1.2      # esperas crescentes (com variação)
    await c.aclose()


async def test_desiste_depois_de_tentar():
    r = Relogio(); srv = FakeRadar(r); srv.falha_na_rede = 99
    c = await _cliente(srv, r)
    with pytest.raises(ServerUnavailable):
        await c.heartbeat({})
    await c.aclose()


async def test_erros_de_negocio_tipados():
    r = Relogio(); srv = FakeRadar(r)
    c = await _cliente(srv, r)
    with pytest.raises(NotFound):
        await c.renovar(999, "x" * 32)
    srv.fila.append({"id": 5, "tipo": "djen_janela", "params": {}})
    t = (await c.reservar(["djen_janela"]))["tarefa"]
    srv.tarefas[5]["status"] = "expirada"
    with pytest.raises(LeaseLost):
        await c.renovar(5, t["lease_token"])
    await c.aclose()


async def test_resultado_so_vale_com_persistido_true():
    r = Relogio(); srv = FakeRadar(r)
    c = await _cliente(srv, r)
    srv.fila.append({"id": 7, "tipo": "djen_janela", "params": {}})
    t = (await c.reservar(["djen_janela"]))["tarefa"]
    srv._h_resultados = lambda body: srv._resp(200, {"persistido": False})
    with pytest.raises(ServerUnavailable):
        await c.resultados(7, t["lease_token"], "0-a", [])
    await c.aclose()
