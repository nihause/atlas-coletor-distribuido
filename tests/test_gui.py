"""Qt real em modo offscreen; motor real com Radar e fontes simulados."""
import asyncio
import json
import logging
import os
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
import httpx
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QFileDialog, QMessageBox

from atlas_worker.gui.app import Window
from atlas_worker.gui.runtime import EngineThread
from atlas_worker.gui.style import STYLE
from atlas_worker.client import RadarClient
from atlas_worker.config_store import ConfigStore, defaults
from atlas_worker.verification import check_connection
from atlas_worker.worker import Worker
from tests.fakes import FakeRadar, FakeFontes, Relogio, TOKEN, item


@pytest.fixture(scope='module')
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyle('Fusion'); instance.setStyleSheet(STYLE)
    yield instance


def wait_for(app, predicate, timeout=6000):
    end = time.monotonic() + timeout / 1000
    while not predicate() and time.monotonic() < end:
        app.processEvents(); QTest.qWait(10)
    assert predicate()


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'data'))
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path/'config'))
    path = tmp_path / '.env'
    ConfigStore(path).save({**defaults(), 'WORKER_TOKEN':TOKEN, 'STATE_DIR':str(tmp_path/'state')})
    handlers = logging.getLogger().handlers[:]
    w = Window(path); w.show(); app.processEvents()
    yield w
    w.background.setChecked(False); w.close_pending = True
    if w.engine: w.stop_engine(); wait_for(app,lambda:w.engine is None)
    wait_for(app,lambda:not w.jobs)
    w.close(); app.processEvents()
    logging.getLogger().handlers = handlers


def test_interface_mascara_chave_salva_e_gera_nova_sem_apagar(window, app, monkeypatch):
    w = window
    assert w.fields['WORKER_TOKEN'].echoMode() == QLineEdit.EchoMode.Password
    w.fields['WORKER_NAME'].setText('coletor-grafico'); w.save_btn.click()
    assert w.store.load()['WORKER_NAME'] == 'coletor-grafico'
    assert w.store.path.stat().st_mode & 0o777 == 0o600
    original = w.store.path.read_bytes()
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**kw:QMessageBox.StandardButton.Yes)
    w.new_btn.click()
    assert w.fields['WORKER_TOKEN'].text() == '' and w.store.path.read_bytes() == original
    w.save_btn.click()
    assert w.store.path.read_bytes() == original
    assert 'Confira' in w.message.text()


@pytest.mark.parametrize('status,code,expected',[(200,'','Conectado com sucesso'),(401,'nao_autorizado','Chave de API recusada'),(403,'sem_permissao','sem permissão de ingestão'),(302,'','Endereço da API')])
def test_teste_assincrono_e_mensagens(window,app,status,code,expected):
    async def check(cfg):
        await asyncio.sleep(.08)
        def response(req):
            if status==200: return httpx.Response(200,json={'dados':{'contrato':1,'comando':'continuar'}})
            return httpx.Response(status,json={'erro':{'codigo':code}},headers={'Location':'https://externo.invalid'})
        return await check_connection(cfg,lambda c:RadarClient(c,transport=httpx.MockTransport(response)))
    w=window; w.checker=check; ticks=[]
    timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(1));timer.start()
    w.test_btn.click()
    assert not w.test_btn.isEnabled()
    wait_for(app,lambda:not w.jobs)
    timer.stop()
    assert len(ticks)>1 and expected in w.message.text()
    assert TOKEN not in w.technical.toPlainText()


def test_logs_filtram_e_exportam_sem_credenciais(window,app,tmp_path,monkeypatch):
    w=window
    logging.getLogger().setLevel(logging.INFO)
    # O handler registra os segredos conhecidos na visualização e na exportação.
    logging.getLogger('atlas_worker').warning('tarefa 77: %s',TOKEN)
    wait_for(app,lambda:bool(w.entries))
    assert TOKEN not in json.dumps(w.entries)
    assert w.entries[-1]['task_id']==77
    w.log_filter.setCurrentText('Erro'); assert w.logs.rowCount()==0
    w.log_filter.setCurrentText('Aviso'); assert w.logs.rowCount()==1
    output=tmp_path/'diagnostico.json'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**k:(str(output),''))
    w.export_diagnostic()
    assert TOKEN not in output.read_text() and json.loads(output.read_text())['events']
    w.clear_logs(); assert w.logs.rowCount()==0


def test_gui_motor_real_conclui_tarefa_e_para_sem_rede(window,app):
    w=window;r=Relogio();srv=FakeRadar(r);fontes=FakeFontes()
    srv.adicionar_djen(1)
    fontes.djen['Banco Exemplo']=[item(i) for i in range(1,21)]
    w.store.save({'TASK_TYPES':'djen_janela'})
    def client_factory(cfg,observer=None):return RadarClient(cfg,transport=srv.transporte(),sleep=r.dormir,observer=observer)
    def worker_factory(cfg,client):
        return Worker(cfg,client,http_fontes=httpx.AsyncClient(transport=fontes.transporte()),ocioso_max=.1,escala_tempo=.01)
    w.engine_factory=lambda cfg,parent=None:EngineThread(cfg,client_factory=client_factory,worker_factory=worker_factory,parent=parent)
    w.start_btn.click()
    wait_for(app,lambda:srv.tarefas.get(1,{}).get('status')=='concluida')
    wait_for(app,lambda:w.metric_labels['completed'].text()=='1')
    assert w.metric_labels['received'].text()=='1'
    assert w.connection.text()=='Conectado'
    w.stop_btn.click();wait_for(app,lambda:w.engine is None)
    assert w.service.text()=='Parado' and all(v==1 for v in srv.itens_gravados.values())
    assert w.store.load()['WORKER_TOKEN']==TOKEN


def test_conectar_iniciar_chave_recusada_mostra_erro(window,app):
    w=window;r=Relogio();srv=FakeRadar(r);srv.token='outra-chave-ficticia'
    def client_factory(cfg,observer=None):return RadarClient(cfg,transport=srv.transporte(),sleep=r.dormir,observer=observer)
    w.engine_factory=lambda cfg,parent=None:EngineThread(cfg,client_factory=client_factory,parent=parent)
    w.start_btn.click()
    wait_for(app,lambda:w.engine is None)
    assert 'Chave de API recusada' in w.message.text()
    assert w.service.text()=='Parado'
    assert TOKEN not in w.message.text()+w.technical.toPlainText()


def test_logs_com_atribuicao_de_chave_preservam_json(window,app,tmp_path,monkeypatch):
    w=window
    w.add_log({'time':'2026-11-15T13:00:00+00:00','level':'WARNING','task_id':3,'message':'WORKER_TOKEN='+TOKEN})
    assert len(w.entries)==1 and TOKEN not in w.entries[0]['message']
    output=tmp_path/'export.json'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**k:(str(output),''))
    w.export_diagnostic()
    assert json.loads(output.read_text())['events'][0]['task_id']==3
    assert TOKEN not in output.read_text()
