"""Aplicativo nativo Atlas: configuração, motor existente, diagnóstico e atualizações."""
from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
    QSystemTrayIcon, QMenu, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from pydantic import ValidationError

from .. import __version__
from ..config import default_state_dir
from ..config_store import ConfigStore, atomic_private, config_path, defaults, save_preferences
from ..instance import AlreadyRunning, FileLock
from ..logging_config import JsonFormatter, RedactFilter, sanitize, sanitize_data, setup
from ..updates import ReleaseClient
from ..verification import Verification, check_connection
from .desktop import autostart_path, set_autostart
from .runtime import AsyncJob, EngineThread
from .style import STYLE


class LogBus(QObject):
    entry = Signal(dict)


class GuiLogHandler(logging.Handler):
    def __init__(self, bus, secrets):
        super().__init__()
        self.bus = bus
        self.addFilter(RedactFilter(secrets))
        self.setFormatter(JsonFormatter())

    def emit(self, record):
        self.bus.entry.emit(json.loads(self.format(record)))


class Window(QMainWindow):
    def __init__(self, env_path: Path, *, engine_factory=EngineThread, checker=check_connection):
        super().__init__()
        self.store = ConfigStore(env_path)
        self.engine_factory, self.checker = engine_factory, checker
        self.engine = None
        self.jobs = []
        self.entries = []
        self.secrets = []
        self.latest = None
        self.restart_pending = False
        self.close_pending = False
        self.install_pending = None
        self.last_snapshot = {}
        self.last_problem = False
        self.prefs_path = config_path().parent / "desktop.json"
        try:
            prefs = json.loads(self.prefs_path.read_text())
        except (OSError, ValueError):
            prefs = {}
        self.setWindowTitle("ATLAS — Coletor Distribuído")
        self.resize(1080, 820)
        self.setMinimumSize(760, 600)
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("atlas.svg"))))
        root = QWidget(); layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24); layout.setSpacing(14)
        title = QLabel("ATLAS — Coletor Distribuído"); title.setObjectName("title")
        layout.addWidget(title)
        self.identity = QLabel(f"{socket.gethostname()}  ·  Versão {__version__}"); self.identity.setObjectName("subtitle")
        layout.addWidget(self.identity)
        self.message = QLabel("Configure a API do Radar para conectar este computador."); self.message.setWordWrap(True); self.message.setObjectName("message")
        layout.addWidget(self.message)
        self.technical_toggle = QCheckBox("Mostrar detalhes técnicos")
        self.technical = QPlainTextEdit(); self.technical.setReadOnly(True); self.technical.setMaximumHeight(100); self.technical.hide()
        self.technical_toggle.toggled.connect(self.technical.setVisible)
        layout.addWidget(self.technical_toggle); layout.addWidget(self.technical)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        self.build_dashboard()
        self.build_config()
        self.build_logs()
        self.build_updates()
        self.setCentralWidget(root)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip("ATLAS — Coletor Distribuído")
            menu = QMenu(self)
            show = QAction("Abrir Atlas", self); show.triggered.connect(self.showNormal); menu.addAction(show)
            stop = QAction("Parar coletor", self); stop.triggered.connect(self.stop_engine); menu.addAction(stop)
            quit_action = QAction("Encerrar aplicativo", self); quit_action.triggered.connect(self.quit_requested); menu.addAction(quit_action)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.showNormal() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
            self.tray.show()
        self.background.setEnabled(self.tray is not None)
        self.background.setChecked(bool(prefs.get("background")) and self.tray is not None)
        self.background.toggled.connect(self.persist_preferences)
        initial = {**defaults(), **self.store.load()}
        self.fill(initial)
        self.load_recent_logs(Path(initial.get("STATE_DIR") or default_state_dir()))
        self.update_path()
        self.bus = LogBus(self); self.bus.entry.connect(self.add_log)
        self.log_handler = GuiLogHandler(self.bus, [])
        logging.getLogger().addHandler(self.log_handler)
        self.statusBar().showMessage("Pronto. Nenhuma tarefa é executada até você conectar.")

    def button(self, text, action, primary=False):
        btn = QPushButton(text); btn.clicked.connect(action)
        if primary: btn.setObjectName("primary")
        return btn

    def page(self, name):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(22, 22, 22, 22); layout.setSpacing(16)
        self.tabs.addTab(page, name)
        return layout

    def build_dashboard(self):
        outer = self.page("Painel")
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget(); content.setObjectName("surface"); layout = QVBoxLayout(content); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(14)
        scroll.setWidget(content); outer.addWidget(scroll)
        activity = QGroupBox("O que está sendo buscado agora"); activity_box = QVBoxLayout(activity)
        self.task_details = QLabel("Nenhuma tarefa em execução. Conecte para receber trabalho do Radar.")
        self.task_details.setTextFormat(Qt.TextFormat.PlainText); self.task_details.setWordWrap(True)
        self.task_details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        activity_box.addWidget(self.task_details); layout.addWidget(activity)
        self.recent_details = QLabel(""); self.recent_details.setWordWrap(True); self.recent_details.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.recent_details)
        connection = QGroupBox("Este computador"); grid = QGridLayout(connection)
        self.connection = QLabel("Desconectado")
        self.service = QLabel("Parado")
        self.last_contact = QLabel("—")
        self.worker_name_label = QLabel("—")
        for row, (name, field) in enumerate([("Coletor", self.worker_name_label), ("Servidor Radar", self.connection), ("Serviço coletor", self.service), ("Última comunicação", self.last_contact)]):
            grid.addWidget(QLabel(name), row, 0); grid.addWidget(field, row, 1)
        layout.addWidget(connection)
        metrics = QGridLayout(); self.metric_labels = {}
        for i, (key, label) in enumerate([("received", "Tarefas recebidas"), ("completed", "Concluídas"), ("errors", "Com erro"), ("active", "Em execução"), ("uptime", "Tempo de atividade"), ("read", "Itens lidos na fonte"), ("found", "Selecionados para envio"), ("sent", "Confirmados nesta execução")]):
            group = QGroupBox(label); box = QVBoxLayout(group)
            value = QLabel("0" if key != "uptime" else "00:00:00"); value.setObjectName("metric"); value.setMinimumHeight(44)
            box.addWidget(value); metrics.addWidget(group, i // 3, i % 3); self.metric_labels[key] = value
        layout.addLayout(metrics)
        note = QLabel("Os indicadores representam esta execução do aplicativo. O Radar mantém o histórico central das tarefas."); note.setWordWrap(True); note.setObjectName("subtitle"); layout.addWidget(note)
        actions = QHBoxLayout()
        self.start_btn = self.button("Conectar e iniciar", self.start_engine, True)
        self.stop_btn = self.button("Parar coleta", self.stop_engine); self.stop_btn.setEnabled(False)
        self.restart_btn = self.button("Reiniciar coletor", self.restart_engine); self.restart_btn.setEnabled(False)
        for btn in [self.start_btn, self.stop_btn, self.restart_btn]: actions.addWidget(btn)
        outer.addLayout(actions)
        self.background = QCheckBox("Continuar trabalhando ao fechar a janela (bandeja do sistema)")
        outer.addWidget(self.background)
        tray_note = QLabel("Se a bandeja não estiver disponível, fechar a janela encerra o coletor com segurança."); tray_note.setWordWrap(True); outer.addWidget(tray_note)
        layout.addStretch()

    def build_config(self):
        layout = self.page("Configuração")
        scroll = QScrollArea(); scroll.setWidgetResizable(True); content = QWidget(); content.setObjectName("surface"); form = QFormLayout(content)
        self.fields = {}
        for key, label in [("RADAR_API_URL", "Endereço da API do Radar"), ("WORKER_NAME", "Nome do computador / coletor"), ("WORKER_TOKEN", "Chave de API do Radar"), ("MAX_CONCURRENCY", "Concorrência máxima"), ("HEARTBEAT_INTERVAL", "Heartbeat (segundos)"), ("LOG_LEVEL", "Nível de log"), ("DATAJUD_API_KEY", "Chave DataJud (opcional)")]:
            if key in ("MAX_CONCURRENCY", "HEARTBEAT_INTERVAL"):
                field = QSpinBox(); field.setRange(*( (1, 8) if key == "MAX_CONCURRENCY" else (5, 300)))
            elif key == "LOG_LEVEL":
                field = QComboBox(); field.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
            else:
                field = QLineEdit()
            field.setObjectName(key)
            self.fields[key] = field
            if key in ("WORKER_TOKEN", "DATAJUD_API_KEY"):
                field.setEchoMode(QLineEdit.EchoMode.Password)
                line = QWidget(); row = QHBoxLayout(line); row.setContentsMargins(0, 0, 0, 0)
                row.addWidget(field)
                toggle = QCheckBox("Mostrar"); toggle.toggled.connect(lambda checked, f=field: f.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)); row.addWidget(toggle)
                form.addRow(label, line)
            else: form.addRow(label, field)
        self.path_label = QLabel(); self.path_label.setWordWrap(True); self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Arquivo local (permissão 600)", self.path_label)
        self.autostart = QCheckBox("Conectar automaticamente ao entrar no Ubuntu")
        self.autostart.setChecked(autostart_path().exists()); self.autostart.toggled.connect(self.change_autostart)
        form.addRow(self.autostart)
        scroll.setWidget(content); layout.addWidget(scroll)
        row = QGridLayout()
        self.save_btn = self.button("Salvar configurações", self.save)
        self.test_btn = self.button("Testar conexão", self.test_connection, True)
        self.new_btn = self.button("Gerar nova configuração", self.new_config)
        self.import_btn = self.button("Abrir .env existente", self.import_config)
        self.config_buttons = [self.save_btn, self.test_btn, self.new_btn, self.import_btn]
        for i, btn in enumerate(self.config_buttons): row.addWidget(btn, i // 2, i % 2)
        layout.addLayout(row)

    def build_logs(self):
        layout = self.page("Logs")
        row = QHBoxLayout(); row.addWidget(QLabel("Exibir"))
        self.log_filter = QComboBox(); self.log_filter.addItems(["Todos", "Informação", "Aviso", "Erro"]); self.log_filter.currentIndexChanged.connect(self.render_logs); row.addWidget(self.log_filter)
        row.addStretch(); row.addWidget(self.button("Limpar visualização", self.clear_logs)); row.addWidget(self.button("Exportar diagnóstico", self.export_diagnostic)); layout.addLayout(row)
        self.logs = QTableWidget(0, 4); self.logs.setHorizontalHeaderLabels(["Data e hora", "Evento", "Tarefa", "Mensagem"])
        self.logs.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.logs.setAlternatingRowColors(True)
        self.logs.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.logs.setColumnWidth(0, 175); self.logs.setColumnWidth(1, 95); self.logs.setColumnWidth(2, 70)
        layout.addWidget(self.logs)

    def build_updates(self):
        layout = self.page("Atualizações")
        self.update_label = QLabel(f"Versão instalada: {__version__}\nNenhuma consulta realizada."); self.update_label.setWordWrap(True); layout.addWidget(self.update_label)
        explanation = QLabel("As atualizações vêm dos Releases oficiais do projeto no GitHub. O pacote será verificado por SHA-256 e aberto no instalador do Ubuntu após sua confirmação. A configuração local é preservada."); explanation.setWordWrap(True); layout.addWidget(explanation)
        self.github_token = QLineEdit(); self.github_token.setEchoMode(QLineEdit.EchoMode.Password); self.github_token.setPlaceholderText("Token GitHub para o repositório privado (opcional, não é salvo)")
        layout.addWidget(self.github_token)
        note = QLabel("Use um token do GitHub com acesso de leitura ao conteúdo do repositório. Este campo nunca recebe a chave do Radar."); note.setWordWrap(True); layout.addWidget(note)
        self.check_updates_btn = self.button("Verificar atualizações", self.check_updates)
        self.update_btn = self.button("Atualizar", self.update_application); self.update_btn.setEnabled(False)
        layout.addWidget(self.check_updates_btn); layout.addWidget(self.update_btn); layout.addStretch()

    def fill(self, values):
        for key, field in self.fields.items():
            value = values.get(key, "")
            if isinstance(field, QSpinBox):
                try: field.setValue(int(value))
                except (ValueError, TypeError): field.setValue(2 if key == "MAX_CONCURRENCY" else 30)
            elif isinstance(field, QComboBox): field.setCurrentText(value)
            else: field.setText(value)
        self.worker_name_label.setText(values.get("WORKER_NAME", "—"))
        self.remember_secrets(values)

    def remember_secrets(self, values):
        for key in ("WORKER_TOKEN", "DATAJUD_API_KEY"):
            if values.get(key) and values[key] not in self.secrets: self.secrets.append(values[key])

    def values(self):
        result = {}
        for key, field in self.fields.items():
            result[key] = str(field.value()) if isinstance(field, QSpinBox) else field.currentText() if isinstance(field, QComboBox) else field.text().strip()
        self.remember_secrets(result)
        return result

    def update_path(self):
        self.path_label.setText(str(self.store.path))

    def show_message(self, message, detail=""):
        self.message.setText(sanitize(message, self.secrets))
        self.technical.setPlainText(sanitize(detail, self.secrets))

    def config_error(self, exc):
        if isinstance(exc, ValidationError):
            fields = ", ".join(".".join(str(x) for x in e["loc"]) or "endereço/chave" for e in exc.errors())
            self.show_message("Confira os campos de configuração.", "Campos inválidos: " + fields + ". Use HTTPS, nome com 3 a 64 caracteres e uma chave não vazia.")
        else: self.show_message("Não foi possível acessar a configuração.", type(exc).__name__)
        self.tabs.setCurrentIndex(1)

    def configuration(self):
        try:
            return self.store.settings({**self.store.load(), **self.values()})
        except (ValidationError, ValueError, OSError) as exc:
            self.config_error(exc); return None

    def save(self):
        try:
            cfg = self.store.save(self.values())
            self.worker_name_label.setText(cfg.worker_name)
            self.show_message("Configurações salvas com acesso restrito ao seu usuário.")
            return cfg
        except (ValidationError, ValueError, OSError) as exc:
            self.config_error(exc); return None

    def new_config(self):
        if QMessageBox.question(self, "Nova configuração", "Limpar os campos e preparar uma nova configuração? O arquivo atual só será alterado quando você salvar.") == QMessageBox.StandardButton.Yes:
            self.fill(defaults()); self.show_message("Nova configuração preparada. Informe a chave e salve para substituir a configuração atual.")

    def import_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir configuração existente", str(Path.home()), "Configuração (*.env .env);;Todos os arquivos (*)")
        if path:
            try:
                self.store = ConfigStore(Path(path)); self.fill({**defaults(), **self.store.load()}); self.update_path()
                if self.autostart.isChecked(): set_autostart(True, self.store.path)
                self.show_message("Configuração carregada. O arquivo original será preservado até você salvar.")
            except (OSError, ValueError) as exc: self.config_error(exc)

    def run_job(self, operation, callback):
        job = AsyncJob(operation, self); self.jobs.append(job)
        job.done.connect(callback); job.failed.connect(self.show_message)
        job.finished.connect(lambda: self.job_finished(job))
        self.set_controls(); job.start()

    def job_finished(self, job):
        self.jobs.remove(job); job.deleteLater(); self.set_controls()
        if self.close_pending and not self.jobs and not self.engine: self.close()

    def test_connection(self):
        cfg = self.configuration()
        if not cfg: return
        self.show_message("Testando conexão com o Radar…")
        self.run_job(lambda: self.checker(cfg), lambda result: self.connection_result(result, cfg))

    def connection_result(self, result, cfg):
        self.connection.setText("Conectado" if result.code == 0 else "Desconectado")
        if result.code == 0: self.last_contact.setText(datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S"))
        message = result.message
        if result.code == 0 and not cfg.datajud_api_key.get_secret_value(): message += " Para tarefas DataJud, informe também a chave DataJud."
        self.show_message(message, result.detail)
        logging.getLogger("atlas_worker.conexao").log(logging.INFO if result.code == 0 else logging.WARNING, "%s %s", result.message, result.detail)

    def set_controls(self):
        active = self.engine is not None
        busy = bool(self.jobs)
        for btn in self.config_buttons: btn.setEnabled(not active and not busy)
        for field in self.fields.values(): field.setEnabled(not active and not busy)
        self.autostart.setEnabled(not active and not busy)
        self.start_btn.setEnabled(not active and not busy)
        self.start_btn.setText("Conectando…" if active else "Conectar e iniciar")
        self.stop_btn.setEnabled(active)
        self.restart_btn.setEnabled(active and not self.restart_pending)
        self.check_updates_btn.setEnabled(not busy)
        self.update_btn.setEnabled(not busy and self.latest is not None)

    def start_engine(self):
        if self.engine or self.jobs: return
        cfg = self.save()
        if not cfg: return
        setup(cfg.log_level, cfg.state_dir, self.secrets)
        self.log_handler = GuiLogHandler(self.bus, self.secrets)
        logging.getLogger().addHandler(self.log_handler)
        self.engine = self.engine_factory(cfg, parent=self)
        self.engine.snapshot.connect(self.apply_snapshot); self.engine.problem.connect(self.engine_problem)
        self.engine.finished.connect(self.engine_finished)
        self.last_problem = False
        self.service.setText("Conectando…"); self.show_message("Conectando e iniciando o coletor…")
        self.set_controls(); self.engine.start(); self.tabs.setCurrentIndex(0)

    def apply_snapshot(self, data):
        self.last_snapshot = data
        self.connection.setText("Conectado" if data["connected"] else "Desconectado")
        self.last_contact.setText(data["last_contact"]); self.service.setText(data["service"])
        for key, field in self.metric_labels.items():
            value = data.get(key, 0)
            field.setText(f"{value // 3600:02}:{value % 3600 // 60:02}:{value % 60:02}" if key == "uptime" else str(value))
        self.statusBar().showMessage(data["service"])
        tasks = data.get("tasks", [])
        lines = []
        for task in tasks:
            lines.append(f"{task['fonte']} · tarefa #{task['id']} · {task['alvo']}\n{task['periodo']}\n{task['fase']} · {task['paginas']} páginas/consultas · {task['lidos']} lidos · {task['encontrados']} selecionados · {task['confirmados']} confirmados no Radar")
        self.task_details.setText(sanitize("\n\n".join(lines) if lines else data.get("waiting", "Aguardando tarefas do Radar"), self.secrets))
        self.recent_details.setText(sanitize("\n".join(f"Última tarefa #{t['id']}: {t['alvo']} · {t['fase']} · {t['confirmados']} confirmados" for t in data.get("recent", [])[:2]), self.secrets))
        stopping = bool(self.engine and self.engine.stop_requested)
        self.start_btn.setText("Parando coleta…" if stopping else (f"Coletando · {data['active']} tarefa(s)" if data["active"] else ("Coletor pausado" if data["service"] == "Pausado pelo Radar" else ("Aguardando tarefas" if data["connected"] else "Conectando ao Radar…"))))
        if data["connected"]:
            self.show_message(f"Coleta em andamento: {data['active']} tarefa(s) em execução." if tasks else data.get("waiting", "Conectado. Aguardando tarefas do Radar."))

    def engine_problem(self, result):
        self.last_problem = True
        if isinstance(result, Verification): self.show_message(result.message, result.detail)
        else: self.show_message(str(result))
        logging.getLogger("atlas_worker.gui").error("Não foi possível manter o coletor em execução.")

    def stop_engine(self):
        if self.engine:
            self.service.setText("Encerrando com segurança…"); self.engine.stop(); self.stop_btn.setEnabled(False); self.start_btn.setText("Parando coleta…")

    def restart_engine(self):
        if self.engine:
            self.restart_pending = True; self.set_controls(); self.stop_engine()

    def engine_finished(self):
        engine = self.engine; self.engine = None
        if engine: engine.deleteLater()
        self.connection.setText("Desconectado"); self.service.setText("Parado"); self.metric_labels["active"].setText("0")
        self.task_details.setText("Coleta parada. Conecte para receber novas tarefas.")
        self.set_controls()
        if not self.last_problem:
            self.show_message("Coletor desconectado. As tarefas confirmadas permanecem no Radar.")
        if self.install_pending:
            path = self.install_pending; self.install_pending = None; self.open_installer(path)
        elif self.close_pending and not self.jobs: self.close()
        elif self.restart_pending:
            self.restart_pending = False; self.start_engine()

    def persist_preferences(self):
        try: save_preferences(self.prefs_path, {"background": self.background.isChecked()})
        except OSError: self.show_message("Não foi possível salvar a preferência da bandeja.")

    def change_autostart(self, enabled):
        if enabled and not self.save():
            self.autostart.blockSignals(True); self.autostart.setChecked(False); self.autostart.blockSignals(False); return
        try:
            set_autostart(enabled, self.store.path)
            self.show_message("Inicialização automática ativada para sua sessão Ubuntu." if enabled else "Inicialização automática desativada.")
        except OSError as exc: self.config_error(exc)

    def load_recent_logs(self, state_dir):
        try:
            with (state_dir / "logs" / "worker.log").open("rb") as source:
                source.seek(0, 2)
                size = source.tell()
                source.seek(max(0, size - 262144))
                lines = source.read().decode("utf-8", errors="replace").splitlines()
            for line in lines[-1000:]:
                try:
                    entry = json.loads(line)
                    if all(k in entry for k in ("time", "level", "message")):
                        self.entries.append(sanitize_data(entry, self.secrets))
                except (ValueError, TypeError):
                    continue
            self.render_logs()
        except OSError:
            pass

    def add_log(self, entry):
        entry = sanitize_data(entry, self.secrets)
        self.entries.append(entry); self.entries = self.entries[-1000:]
        self.render_logs()

    def render_logs(self):
        if not hasattr(self, "logs"): return
        selected = self.log_filter.currentText()
        levels = {"Informação": {"INFO", "DEBUG"}, "Aviso": {"WARNING"}, "Erro": {"ERROR", "CRITICAL"}}
        entries = [e for e in self.entries if selected == "Todos" or e["level"] in levels[selected]]
        self.logs.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            try: when = datetime.fromisoformat(entry["time"]).astimezone().strftime("%d/%m/%Y %H:%M:%S")
            except ValueError: when = "—"
            for column, value in enumerate([when, entry["level"], entry.get("task_id") or "—", entry["message"]]):
                item = QTableWidgetItem(str(value)); item.setToolTip(str(value)); self.logs.setItem(row, column, item)
        self.logs.scrollToBottom()

    def clear_logs(self):
        self.entries.clear(); self.render_logs()

    def export_diagnostic(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar diagnóstico sem credenciais", str(Path.home() / "atlas-diagnostico.json"), "JSON (*.json)")
        if path:
            payload = {"version": __version__, "service": self.service.text(), "connection": self.connection.text(), "snapshot": self.last_snapshot, "events": self.entries}
            try:
                atomic_private(Path(path), json.dumps(sanitize_data(payload, self.secrets), ensure_ascii=False, indent=2))
                self.show_message("Diagnóstico exportado sem configuração ou credenciais.")
            except OSError: self.show_message("Não foi possível gravar o diagnóstico.")

    def check_updates(self):
        token = self.github_token.text().strip()
        if token: self.secrets.append(token)
        self.latest = None
        self.update_label.setText("Consultando Releases no GitHub…")
        async def operation():
            client = ReleaseClient(token)
            try: return await client.latest(__version__)
            finally: await client.close()
        def received(release):
            self.latest = release
            self.update_label.setText(f"Versão instalada: {__version__}\n" + (f"Disponível: {release.version} · {release.name}" if release else "Você está na versão mais recente publicada."))
        self.run_job(operation, received)

    def update_application(self):
        if not self.latest or self.jobs: return
        if QMessageBox.question(self, "Atualizar Atlas", "Baixar o pacote verificado e abrir o instalador do Ubuntu? Se o coletor estiver ativo, ele será encerrado com segurança antes da instalação.") != QMessageBox.StandardButton.Yes: return
        release = self.latest; token = self.github_token.text().strip()
        if token: self.secrets.append(token)
        async def operation():
            client = ReleaseClient(token)
            try: return await client.download(release, default_state_dir() / "downloads")
            finally: await client.close()
        def downloaded(path):
            if self.engine:
                self.install_pending = path; self.stop_engine()
            else: self.open_installer(path)
        self.run_job(operation, downloaded)

    def open_installer(self, path):
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.show_message("Pacote verificado. Conclua a instalação na janela do Ubuntu e depois reabra o Atlas.")
        else: self.show_message("Não foi possível abrir o instalador do Ubuntu.", f"Abra o pacote verificado em {path} com um instalador de pacotes .deb.")

    def quit_requested(self):
        self.close_pending = True; self.close()

    def closeEvent(self, event: QCloseEvent):
        if not self.close_pending and self.tray and self.background.isChecked():
            self.hide(); event.ignore(); return
        if self.engine or self.jobs:
            self.close_pending = True; self.restart_pending = False
            self.stop_engine(); self.show_message("Aguarde o encerramento seguro das tarefas e operações em andamento.")
            event.ignore(); return
        if self.tray: self.tray.hide()
        logging.getLogger().removeHandler(self.log_handler)
        event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser(description="ATLAS — Coletor Distribuído")
    parser.add_argument("--env", type=Path, help="arquivo existente, compatível com a CLI")
    parser.add_argument("--start", action="store_true", help="conecta após abrir a interface")
    args = parser.parse_args(argv)
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Atlas Coletor"); app.setDesktopFileName("atlas-coletor"); app.setStyle("Fusion"); app.setStyleSheet(STYLE)
    path = args.env or (Path.cwd() / ".env" if (Path.cwd() / ".env").is_file() else config_path())
    lock = FileLock("gui:" + str(path.expanduser().resolve()))
    try: lock.acquire()
    except AlreadyRunning:
        QMessageBox.information(None, "Atlas já aberto", "Já existe uma janela do Atlas usando esta configuração. Confira também a bandeja do sistema.")
        return 6
    try:
        setup("INFO", default_state_dir(), [])
        window = Window(path); window.show()
        if args.start: QTimer.singleShot(0, window.start_engine)
        return app.exec()
    finally: lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
