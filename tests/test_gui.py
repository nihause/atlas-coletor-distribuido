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
        time.sleep(0.005)  # Libera explicitamente o GIL para a thread Python do motor no runner Qt.
    assert predicate()


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'data'))
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path/'config'))
    path = tmp_path / '.env'
    ConfigStore(path).save({**defaults(), 'WORKER_TOKEN':TOKEN, 'STATE_DIR':str(tmp_path/'state')})
    handlers = logging.getLogger().handlers[:]
    monkeypatch.setattr('atlas_worker.gui.app.QTimer.singleShot', lambda *args: None)
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
    if os.name != 'nt': assert w.store.path.stat().st_mode & 0o777 == 0o600
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


def test_painel_mostra_alvo_contadores_e_botao_coletando(window,app):
    from types import SimpleNamespace
    w=window;w.engine=SimpleNamespace(stop_requested=False)
    try:
        w.set_controls()
        w.apply_snapshot({'connected':True,'last_contact':'agora','received':1,'completed':0,'errors':0,'active':1,'uptime':12,'read':120,'found':100,'sent':80,'service':'Coletando','tasks':[{'id':7,'fonte':'DJEN','alvo':'Banco Exemplo','periodo':'2026-11-01 até 2026-11-07','fase':'Consultando DJEN','paginas':2,'lidos':120,'encontrados':100,'confirmados':80}]})
        assert 'Banco Exemplo' in w.task_details.text() and '120 lidos' in w.task_details.text() and '80 confirmados' in w.task_details.text()
        assert w.start_btn.text()=='Coletando · 1 tarefa(s)' and not w.start_btn.isEnabled()
        assert w.metric_labels['read'].text()=='120'
        w.apply_snapshot({'connected':True,'last_contact':'agora','received':1,'completed':1,'errors':0,'active':0,'uptime':13,'service':'Aguardando tarefas','tasks':[],'waiting':'Nenhuma tarefa disponível.'})
        assert w.start_btn.text()=='Aguardando tarefas' and 'Nenhuma tarefa disponível.' in w.task_details.text()
    finally:w.engine=None;w.set_controls()


async def test_encerramento_publica_contadores_finais(cfg,app):
    class Finito(Worker):
        async def rodar(self,*args):
            self.metrics.tarefas_concluidas=2
            self.metrics.itens_enviados=45
            self.parar.set()
    def client(cfg,observer=None):return RadarClient(cfg,transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'dados':{}})),observer=observer)
    engine=EngineThread(cfg,client_factory=client,worker_factory=Finito)
    values=[];engine.snapshot.connect(values.append)
    await engine.execute()
    assert values[-1]['completed']==2 and values[-1]['sent']==45

def test_cancelar_atualizacao_libera_coleta(window,app):
    from types import SimpleNamespace
    calls=[];w=window
    w.engine=SimpleNamespace(drain=lambda enabled=True:calls.append(enabled),report_update=lambda s:None,stop_requested=False)
    try:
        w.prepare_install(Path('/tmp/atlas-teste.deb'))
        assert calls==[True] and w.install_pending and 'Aguardando finalização' in w.update_status.text()
        w.cancel_update()
        assert calls==[True,False] and w.install_pending is None
    finally:w.engine=None;w.set_controls()


def test_reiniciar_aplicativo_espera_processo_anterior(window,monkeypatch):
    from atlas_worker.gui import app as module
    w=window;calls=[]
    original=Path.is_file
    monkeypatch.setattr(Path,'is_file',lambda p:True if p.as_posix()=='/usr/bin/atlas-coletor' else original(p))
    monkeypatch.setattr(module.QProcess,'startDetached',lambda exe,args:calls.append((exe,args)) or (True,12345))
    monkeypatch.setattr(w,'close',lambda:None)
    w.restart_application()
    assert calls[0][0]=='/usr/bin/atlas-coletor' and '--restart-after' in calls[0][1]
    assert '--env' in calls[0][1] and str(w.store.path) in calls[0][1]


def test_verificacao_automatica_sem_instalar(window,monkeypatch):
    w=window;calls=[]
    monkeypatch.setattr(w,'check_updates',lambda:calls.append('consulta'))
    assert w.update_timer.interval()==6*60*60*1000
    w.automatic_check();assert calls==['consulta'] and w.install_process is None

@pytest.mark.parametrize('size',[(1100,700),(1180,970)])
def test_painel_cabe_sem_rolagem_em_alturas_usuais(window,app,size):
    w=window;w.resize(*size)
    w.apply_snapshot({'connected':True,'last_contact':'agora','received':1,'completed':0,'errors':0,'active':1,'uptime':12,'read':120,'found':100,'sent':80,'service':'Coletando','tasks':[{'id':7,'fonte':'DJEN','alvo':'Banco Exemplo','periodo':'01/11/2026 até 07/11/2026','fase':'Consultando DJEN','paginas':2,'lidos':120,'encontrados':100,'confirmados':80}]})
    app.processEvents()
    assert w.dashboard_scroll.verticalScrollBar().maximum()==0
    assert w.dashboard_scroll.horizontalScrollBar().maximum()==0
    assert all(label.visibleRegion().isEmpty() is False for label in w.metric_labels.values())


def test_falha_reinicio_nao_fecha_janela(window,monkeypatch):
    from atlas_worker.gui import app as module
    w=window;original=Path.is_file
    monkeypatch.setattr(Path,'is_file',lambda p:True if p.as_posix()=='/usr/bin/atlas-coletor' else original(p))
    monkeypatch.setattr(module.QProcess,'startDetached',lambda *a:(False,-1))
    w.restart_application()
    assert not w.close_pending and 'Não foi possível reiniciar' in w.update_status.text()


def test_datajud_publico_preenchido_sem_sobrescrever(window):
    from atlas_worker.datajud_public import DATAJUD_PUBLIC_KEY
    w=window;values=w.values();values['DATAJUD_API_KEY']='';w.fill(values)
    assert w.fields['DATAJUD_API_KEY'].text()==DATAJUD_PUBLIC_KEY
    values['DATAJUD_API_KEY']='chave-personalizada-ficticia';w.fill(values)
    assert w.fields['DATAJUD_API_KEY'].text()=='chave-personalizada-ficticia'
