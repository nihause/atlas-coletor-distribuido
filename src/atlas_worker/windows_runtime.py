"""Integração Windows: mutex de instalação e handoff do pacote autenticado."""
from __future__ import annotations
import os,subprocess,tempfile,shutil
from pathlib import Path
from . import __version__
from .release_manifest import verify_package

MUTEX='Local\\JustisoftAtlasColetor'

def installation_mutex():
    import ctypes
    from ctypes import wintypes
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR]
    api.CreateMutexW.restype=wintypes.HANDLE
    handle=api.CreateMutexW(None,False,MUTEX)
    if not handle:raise OSError('Não foi possível proteger a instalação Windows.')
    return handle

def close_mutex(handle):
    import ctypes
    from ctypes import wintypes
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CloseHandle.argtypes=[wintypes.HANDLE];api.CloseHandle.restype=wintypes.BOOL
    api.CloseHandle(handle)

def launch_update(source:Path,env_path:Path,resume:bool,*,runner=subprocess.Popen):
    # Pasta independente do diretório instalado. Nunca passa o conteúdo do .env ao instalador.
    root=Path(tempfile.mkdtemp(prefix='atlas-update-'))
    target=root/source.name
    try:
        shutil.copyfile(source,target)
        raw=source.with_suffix(source.suffix+'.manifest.json').read_bytes()
        signature=source.with_suffix(source.suffix+'.manifest.sig').read_bytes()
        verify_package(target,raw,signature,__version__)
        args=[str(target),'/SILENT','/NORESTART',f'/ATLASWAITPID={os.getpid()}',f'/ATLASENV={env_path.resolve()}']
        if resume:args.append('/ATLASSTART=1')
        # O instalador compilado aguarda a saída do aplicativo; nunca força encerramento de coleta.
        return runner(args,cwd=root,close_fds=True)
    except Exception:
        shutil.rmtree(root,ignore_errors=True)
        raise
