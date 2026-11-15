"""Contrato dos pacotes Windows, com fontes e assinaturas simuladas."""
import base64,hashlib,json,os,shutil
from pathlib import Path
import httpx,pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from atlas_worker import release_manifest as trust
from atlas_worker.updates import API,ReleaseClient

async def test_windows_baixa_manifesto_proprio_e_recusa_linux(tmp_path,monkeypatch):
    key=Ed25519PrivateKey.generate()
    monkeypatch.setattr(trust,'PUBLIC_KEY_HEX',key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex())
    package=b'instalador de teste';name='atlas-coletor_0.3.0_windows_amd64.exe'
    manifest=dict(schema=1,repository=trust.REPO,version='0.3.0',packages=[dict(name=name,os='windows',arch='amd64',size=len(package),sha256=hashlib.sha256(package).hexdigest())])
    raw=json.dumps(manifest).encode();sig=base64.b64encode(key.sign(raw))
    names=[name,'manifest-windows.json','manifest-windows.sig']
    def handler(req):
        if req.url.path.endswith('/latest'):return httpx.Response(200,json=dict(tag_name='v0.3.0',assets=[dict(name=n,url=API+'/releases/assets/'+str(i)) for i,n in enumerate(names)]))
        return httpx.Response(200,content={'0':package,'1':raw,'2':sig}[req.url.path.rsplit('/',1)[1]])
    client=ReleaseClient(transport=httpx.MockTransport(handler))
    try:
        release=await client.latest('0.2.4',machine='AMD64',system='Windows')
        path=await client.download(release,tmp_path)
        assert path.name==name
        trust.verify_package(path,raw,sig,'0.2.4',machine='AMD64',system='Windows')
        with pytest.raises(ValueError,match='incompatível'):trust.verify_package(path,raw,sig,'0.2.4',machine='x86_64',system='Linux',os_release={'ID':'ubuntu','VERSION_ID':'24.04'})
        from atlas_worker import windows_runtime
        monkeypatch.setattr(trust.platform,'system',lambda:'Windows')
        monkeypatch.setattr(trust.platform,'machine',lambda:'AMD64')
        calls=[]
        windows_runtime.launch_update(path,tmp_path/'dados com espaços'/'config.env',True,runner=lambda args,**kw:calls.append(args))
        args=calls[0]
        assert '/ATLASSTART=1' in args and f'/ATLASWAITPID={os.getpid()}' in args
        assert any(x.startswith('/ATLASENV=') for x in args)
        shutil.rmtree(Path(args[0]).parent)
    finally:await client.close()

@pytest.mark.parametrize('system,machine',[('Windows','ARM64'),('Darwin','x86_64')])
def test_plataforma_nao_suportada(system,machine):
    with pytest.raises(ValueError):trust.platform_target(system=system,machine=machine)

@pytest.mark.skipif(os.name!='nt',reason='Integração nativa Windows no runner')
def test_autostart_windows_e_mutex(tmp_path,monkeypatch):
    from atlas_worker.gui.desktop import set_autostart,autostart_path
    from atlas_worker.windows_runtime import installation_mutex,close_mutex
    monkeypatch.setenv('APPDATA',str(tmp_path/'Roaming'))
    path=tmp_path/"configuração com espaço"/'.env'
    set_autostart(True,path)
    assert autostart_path().is_file()
    set_autostart(False,path)
    assert not autostart_path().exists() and not path.exists()
    handle=installation_mutex();assert handle;close_mutex(handle)
