"""Homologação nativa do instalador, sem conectar ao Radar."""
import json,os,subprocess,tempfile
from pathlib import Path
from atlas_worker import __version__

package=next(Path(os.environ['ATLAS_PACKAGES']).glob('*.exe'))
with tempfile.TemporaryDirectory(prefix='atlas-install-') as tmp:
    root=Path(tmp);dest=root/'Aplicativo';config=root/'dados'/'config.env';config.parent.mkdir()
    config.write_text('TESTE=preservado\n',encoding='utf-8')
    for _ in range(2):
        subprocess.run([str(package),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/DIR='+str(dest)],check=True,timeout=180)
        result=root/'resultado.json'
        subprocess.run([str(dest/'atlas-coletor.exe'),'--diagnostico-instalacao',str(result)],check=True,timeout=60)
        data=json.loads(result.read_text(encoding='utf-8'))
        assert data==dict(version=__version__,datajud_default=True,engine_stopped=True,gui=True),data
        assert config.read_text(encoding='utf-8')=='TESTE=preservado\n'
        assert (dest/'unins000.exe').exists()
    shortcuts=list((Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/ATLAS Coletor').glob('*.lnk'))
    assert shortcuts,'Atalho do menu não foi instalado'
    subprocess.run([str(dest/'unins000.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],check=True,timeout=90)
    assert config.exists()
print('Instalação, GUI empacotada, reinstalação e desinstalação verificadas; nenhuma coleta iniciada.')
