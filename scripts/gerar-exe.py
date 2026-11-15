#!/usr/bin/env python3
"""Gera instalador Windows nativo, com Python/Qt, sem depender de Python no PC."""
import argparse,hashlib,os,platform,shutil,subprocess,sys,tempfile
from pathlib import Path
from atlas_worker import __version__

ROOT=Path(__file__).resolve().parents[1]

def build(output:Path):
    if platform.system()!='Windows' or platform.machine().lower() not in ('amd64','x86_64'):
        raise SystemExit('Gere o .exe em Windows x64 (runner windows-2022).')
    compiler=shutil.which('ISCC.exe') or str(Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Inno Setup 6'/'ISCC.exe')
    if not Path(compiler).is_file():raise SystemExit('Inno Setup 6 não encontrado.')
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='atlas-win-') as tmp:
        stage=Path(tmp)
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name','atlas-coletor','--distpath',str(stage/'dist'),'--workpath',str(stage/'build'),'--specpath',str(stage),'--paths',str(ROOT/'src'),'--collect-data','atlas_worker','--exclude-module','PySide6.QtWebEngineCore','--exclude-module','PySide6.QtWebEngineWidgets',str(ROOT/'packaging'/'launcher.py')],check=True,cwd=stage)
        subprocess.run([compiler,'/DAppVersion='+__version__,'/DSourceDir='+str(stage/'dist'/'atlas-coletor'),'/DOutputDir='+str(output),str(ROOT/'packaging'/'windows'/'atlas.iss')],check=True)
    target=output/f'atlas-coletor_{__version__}_windows_amd64.exe'
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.exe.sha256').write_text(digest+'  '+target.name+'\n')
    print(target)
    return target

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);build(p.parse_args().output)
