"""Instalação elevada limitada ao pacote oficial autenticado; sem configuração do usuário."""
from __future__ import annotations
import os,shutil,subprocess,tempfile
from pathlib import Path
from . import __version__
from .release_manifest import verify_package

def install_verified(source: Path, *, runner=subprocess.run):
    # O pkexec invoca somente o executável instalado, de propriedade de root.
    # Cópia privada elimina troca do pacote pelo usuário após a validação.
    if os.geteuid()!=0: raise ValueError('A instalação precisa da autorização gráfica do Ubuntu.')
    source=source.resolve()
    with tempfile.TemporaryDirectory(prefix='atlas-install-') as tmp:
        package=Path(tmp)/source.name
        if source.stat().st_size>1024**3: raise ValueError('Pacote grande demais.')
        shutil.copyfile(source,package)
        raw=source.with_suffix('.deb.manifest.json').read_bytes()
        signature=source.with_suffix('.deb.manifest.sig').read_bytes()
        current=runner(['/usr/bin/dpkg-query','-W','-f=${Version}','atlas-coletor'],capture_output=True,text=True,check=True).stdout.strip()
        data=verify_package(package,raw,signature,current)
        info=runner(['/usr/bin/dpkg-deb','-f',str(package),'Package','Version','Architecture'],capture_output=True,text=True,check=True).stdout
        fields=dict(line.split(': ',1) for line in info.strip().splitlines())
        entry=next(p for p in data['packages'] if p['name']==package.name)
        if fields!={'Package':'atlas-coletor','Version':data['version'],'Architecture':entry['arch']}:
            raise ValueError('Metadados do pacote divergem do manifesto.')
        runner(['/usr/bin/apt-get','-y','--no-remove','-o','DPkg::Lock::Timeout=120','install',str(package)],check=True,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','DEBIAN_FRONTEND':'noninteractive'})
        installed=runner(['/usr/bin/dpkg-query','-W','-f=${Version}','atlas-coletor'],capture_output=True,text=True,check=True).stdout.strip()
        if installed!=data['version']: raise ValueError('Não foi possível confirmar a versão instalada.')
        return installed

def main(args):
    if len(args)!=1: return 2
    try:
        print('Atlas instalado: '+install_verified(Path(args[0])))
        return 0
    except Exception as exc:
        print('Não foi possível instalar a atualização: '+type(exc).__name__)
        return 1
