"""Configuração, diagnósticos, travas e atualização: sem rede real."""
import asyncio
import hashlib
import json
import logging
import os
import socket
import ssl
from pathlib import Path

import httpx
import pytest

from atlas_worker.config_store import ConfigStore, defaults
from atlas_worker.instance import AlreadyRunning, RunLock
from atlas_worker.logging_config import JsonFormatter, RedactFilter, sanitize
from atlas_worker.verification import check_connection
from atlas_worker.client import RadarClient
from atlas_worker.updates import API, ReleaseClient, Release


def factory(handler):
    return lambda cfg: RadarClient(cfg, transport=httpx.MockTransport(handler), sleep=lambda _: asyncio.sleep(0))


def test_env_roundtrip_preserva_extras_e_permissoes(tmp_path):
    path = tmp_path / '.env'
    path.write_text("TASK_TYPES=djen_janela\nREQUEST_TIMEOUT=15\n# Mantido o valor extra\nCUSTOM_VALUE='opção anterior'\n")
    store = ConfigStore(path)
    token = "valor fictício com # $ e ' e \\ e ${VAR}"
    values = {**defaults(), 'WORKER_TOKEN': token, 'DATAJUD_API_KEY': 'valor de teste'}
    cfg = store.save(values)
    loaded = store.load()
    assert cfg.worker_token.get_secret_value() == token == loaded['WORKER_TOKEN']
    assert cfg.task_types == 'djen_janela' and cfg.request_timeout == 15
    assert loaded['CUSTOM_VALUE'] == 'opção anterior'
    assert path.stat().st_mode & 0o777 == 0o600
    store.save({'MAX_CONCURRENCY': '4'})
    assert store.load()['WORKER_TOKEN'] == token
    assert store.load()['CUSTOM_VALUE'] == 'opção anterior'


def test_env_invalido_nao_substitui_anterior(tmp_path):
    store = ConfigStore(tmp_path / '.env')
    store.save({**defaults(), 'WORKER_TOKEN': 'teste'})
    original = store.path.read_bytes()
    with pytest.raises(ValueError): store.save({'WORKER_TOKEN': ''})
    assert store.path.read_bytes() == original


def test_config_nao_escreve_em_symlink(tmp_path):
    target = tmp_path / 'original'; target.write_text('original')
    path = tmp_path / '.env'; path.symlink_to(target)
    with pytest.raises(ValueError): ConfigStore(path).save({**defaults(), 'WORKER_TOKEN': 'teste'})
    assert target.read_text() == 'original'


@pytest.mark.parametrize('status,code,text', [(401, 'nao_autorizado', 'Chave de API recusada'), (403, 'sem_permissao', 'sem permissão de ingestão'), (403, 'proibido', 'Acesso recusado'), (404, 'nao_encontrado', 'Endereço da API'), (503, 'indisponivel', 'Servidor indisponível'), (400, 'contrato_incompativel', 'Versão incompatível')])
async def test_conexao_http_com_evidencias(cfg, status, code, text):
    def handler(req): return httpx.Response(status, json={'erro': {'codigo': code, 'mensagem': 'simulação'}})
    result = await check_connection(cfg, factory(handler))
    assert text in result.message


@pytest.mark.parametrize('kind,text', [('dns','Falha de DNS'), ('ssl','certificado SSL'), ('timeout','Tempo de conexão'), ('unknown','Servidor indisponível')])
async def test_falhas_de_rede(cfg, kind, text):
    def handler(req):
        if kind == 'timeout': raise httpx.ConnectTimeout('simulação', request=req)
        if kind == 'dns': raise httpx.ConnectError('simulação', request=req) from socket.gaierror(-2, 'simulação')
        if kind == 'ssl': raise httpx.ConnectError('simulação', request=req) from ssl.SSLCertVerificationError('simulação')
        raise httpx.ConnectError('simulação', request=req)
    result = await check_connection(cfg, factory(handler))
    assert text in result.message and result.code == 5


@pytest.mark.parametrize('status,body', [(200,'<html>login</html>'),(302,'redirecionamento')])
async def test_html_redirect_nao_culpa_chave(cfg, status, body):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(status, text=body, headers={'Location': 'https://outro.invalid/login'})
    result = await check_connection(cfg, factory(handler))
    assert result.code == 5 and 'Endereço da API' in result.message
    assert len(calls) == 1


async def test_contrato_incompativel_e_sucesso(cfg):
    for contract, expected in [(1,0),(2,3)]:
        result = await check_connection(cfg, factory(lambda req: httpx.Response(200,json={'dados':{'contrato':contract}})))
        assert result.code == expected


def test_trava_compartilhada_cli_gui(cfg, monkeypatch, tmp_path):
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
    with RunLock(cfg):
        with pytest.raises(AlreadyRunning):
            with RunLock(cfg): pass
    with RunLock(cfg): pass


def test_logs_incluem_tarefa_e_removem_segredo_de_excecao():
    secret = 'fictício com detalhes'
    record = logging.LogRecord('atlas_worker', logging.ERROR, '', 1, 'tarefa 12 falhou: %s', (secret,), None)
    try: raise RuntimeError(secret)
    except RuntimeError:
        import sys
        record.exc_info = sys.exc_info()
    assert RedactFilter([secret]).filter(record)
    text = JsonFormatter().format(record)
    assert secret not in text and json.loads(text)['task_id'] == 12
    assert 'outra-chave' not in sanitize('Authorization: Bearer outra-chave')


async def test_update_integridade_e_token_separado(tmp_path):
    package = b'pacote-simulado'
    digest = hashlib.sha256(package).hexdigest()
    requests = []
    def handler(req):
        requests.append(req)
        if req.url.path.endswith('/latest'):
            return httpx.Response(200, json={'tag_name':'v0.3.0','assets':[{'name':'atlas-coletor_0.3.0_ubuntu24.04_amd64.deb','url':API+'/releases/assets/7','digest':'sha256:'+digest}]})
        if req.url.host == 'api.github.com':
            return httpx.Response(302, headers={'Location':'https://release-assets.githubusercontent.com/pacote'})
        assert 'Authorization' not in req.headers
        return httpx.Response(200, content=package)
    client = ReleaseClient('credencial-github-ficticia', httpx.MockTransport(handler))
    try:
        release = await client.latest('0.2.0', machine='x86_64',os_release={'ID':'ubuntu','VERSION_ID':'24.04'})
        path = await client.download(release,tmp_path)
        assert path.read_bytes() == package
        assert requests[0].headers['Authorization'] == 'Bearer credencial-github-ficticia'
        release.sha256 = '0' * 64
        with pytest.raises(ValueError, match='Integridade'): await client.download(release, tmp_path)
    finally: await client.close()


async def test_updates_bloqueiam_destino_externo_e_checksum_ausente():
    def handler(req): return httpx.Response(200,json={'tag_name':'v0.3.0','assets':[{'name':'atlas-coletor_0.3.0_ubuntu24.04_amd64.deb','url':API+'/releases/assets/7'}]})
    client = ReleaseClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError,match='fora do GitHub'): await client.request('https://externo.invalid/pacote')
        with pytest.raises(ValueError,match='checksum'): await client.latest('0.2.0', machine='x86_64',os_release={'ID':'ubuntu','VERSION_ID':'24.04'})
    finally: await client.close()


def test_autostart_nao_toca_config_e_preserva_argumentos(tmp_path, monkeypatch):
    from atlas_worker.gui.desktop import set_autostart, autostart_path
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    path = tmp_path / 'pasta com espaço' / '.env'
    set_autostart(True,path)
    content = autostart_path().read_text()
    assert '--start' in content and '"'+str(path)+'"' in content
    assert not path.exists()
    set_autostart(False,path)
    assert not autostart_path().exists()


def test_detecta_servico_antigo_sem_alterar(cfg,monkeypatch,tmp_path):
    from types import SimpleNamespace
    import psutil
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'dados'))
    path=tmp_path/'.env'
    ConfigStore(path).save({**defaults(),'RADAR_API_URL':cfg.base_url,'WORKER_NAME':cfg.worker_name,'WORKER_TOKEN':'teste','STATE_DIR':str(cfg.state_dir)})
    fake=SimpleNamespace(pid=os.getpid()+100,info={'cmdline':['/legado/.venv/bin/atlas-worker','--env',str(path),'run']})
    monkeypatch.setattr(psutil,'process_iter',lambda *a:[fake])
    with pytest.raises(AlreadyRunning,match='terminal/serviço'):
        with RunLock(cfg):pass


async def test_update_fallback_checksum_e_versao_atual(tmp_path):
    package=b'pacote para teste'; digest=hashlib.sha256(package).hexdigest()
    name='atlas-coletor_0.3.0_ubuntu24.04_amd64.deb'
    def handler(req):
        if req.url.path.endswith('/latest'):
            return httpx.Response(200,json={'tag_name':'v0.3.0','assets':[{'name':name,'url':API+'/releases/assets/2'},{'name':name+'.sha256','url':API+'/releases/assets/3'}]})
        if req.url.path.endswith('/3'):return httpx.Response(200,text=digest+'  '+name+'\n')
        return httpx.Response(200,content=package)
    client=ReleaseClient(transport=httpx.MockTransport(handler))
    try:
        assert await client.latest('0.3.0',machine='x86_64',os_release={'ID':'ubuntu','VERSION_ID':'24.04'}) is None
        release=await client.latest('0.2.0',machine='x86_64',os_release={'ID':'ubuntu','VERSION_ID':'24.04'})
        assert release.sha256==digest
        assert (await client.download(release,tmp_path)).read_bytes()==package
    finally:await client.close()


async def test_motor_recusa_contrato_sem_reservar_tarefas(cfg):
    from atlas_worker.worker import Worker
    from atlas_worker.client import Rejected
    from atlas_worker.verification import classify
    paths=[]
    def handler(req):
        paths.append(req.url.path)
        return httpx.Response(200,json={'dados':{'contrato':2}})
    client=RadarClient(cfg,transport=httpx.MockTransport(handler))
    worker=Worker(cfg,client)
    try:
        with pytest.raises(Rejected) as err: await worker.iniciar()
        assert classify(err.value).code==3
        assert paths==['/radar/api/v1/coletores.php/registrar']
    finally:
        await client.aclose();await worker.http.aclose()
