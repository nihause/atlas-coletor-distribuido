"""Diagnóstico isolado do binário para homologação do pacote nos runners."""
import json,os,tempfile
from pathlib import Path
from . import __version__

def run(output:Path):
    os.environ['QT_QPA_PLATFORM']='offscreen'
    with tempfile.TemporaryDirectory(prefix='atlas-probe-') as tmp:
        root=Path(tmp)
        os.environ['XDG_CONFIG_HOME']=str(root/'config');os.environ['XDG_DATA_HOME']=str(root/'data')
        os.environ['LOCALAPPDATA']=str(root/'local');os.environ['APPDATA']=str(root/'roaming')
        from PySide6.QtWidgets import QApplication
        from .gui.app import Window
        from .gui.style import STYLE
        from .datajud_public import DATAJUD_PUBLIC_KEY
        app=QApplication([]);app.setStyleSheet(STYLE)
        w=Window(root/'.env');w.show();app.processEvents()
        result={'version':__version__,'datajud_default':w.fields['DATAJUD_API_KEY'].text()==DATAJUD_PUBLIC_KEY,'engine_stopped':w.engine is None,'gui':w.isVisible()}
        w.close_pending=True;w.close();app.processEvents()
        output.write_text(json.dumps(result),encoding='utf-8')
