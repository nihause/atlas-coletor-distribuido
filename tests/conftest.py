import pytest

from atlas_worker.client import RadarClient
from atlas_worker.config import Settings
from atlas_worker.worker import Worker
from tests.fakes import TOKEN, FakeFontes, FakeRadar, Relogio


@pytest.fixture
def cfg(tmp_path):
    return Settings(radar_api_url="https://servidor.exemplo.com/radar/api/v1", worker_name="coletor-01", worker_token=TOKEN, state_dir=tmp_path / "estado",
                    datajud_api_key="chave-publica-datajud", max_concurrency=2, _env_file=None)


@pytest.fixture
def mundo(cfg):
    r = Relogio()
    srv = FakeRadar(r)
    fontes = FakeFontes()
    return r, srv, fontes


def novo_worker(cfg, mundo, nome="coletor-01", estado=None):
    import httpx
    r, srv, fontes = mundo
    c = cfg.model_copy(update={"worker_name": nome, **({"state_dir": estado} if estado else {})})
    client = RadarClient(c, transport=srv.transporte(), sleep=r.dormir)
    http = httpx.AsyncClient(transport=fontes.transporte())
    return Worker(c, client, http_fontes=http, sleep=r.dormir, ocioso_max=1.0, escala_tempo=0.001), client
