"""Atualização autenticada: fontes simuladas e nenhuma instalação real."""
import base64,hashlib,json,subprocess
from pathlib import Path
from types import SimpleNamespace
import httpx,pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from atlas_worker import release_manifest as trust
from atlas_worker.updates import API,ReleaseClient
from atlas_worker.installer import install_verified

@pytest.fixture
def signed(monkeypatch):
    key=Ed25519PrivateKey.generate()
    monkeypatch.setattr(trust,'PUBLIC_KEY_HEX',key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex())
    package=b'pacote simulado oficial';name='atlas-coletor_0.3.0_ubuntu24.04_amd64.deb'
    manifest=dict(schema=1,repository=trust.REPO,version='0.3.0',packages=[dict(name=name,os='ubuntu24.04',arch='amd64',size=len(package),sha256=hashlib.sha256(package).hexdigest())])
    raw=json.dumps(manifest).encode();signature=base64.b64encode(key.sign(raw))
    assets=[dict(name=n,url=API+f'/releases/assets/{i}') for i,n in enumerate([name,'manifest.json','manifest.sig'],1)]
    payload=dict(tag_name='v0.3.0',assets=assets,body='Melhorias da versão')
    def handler(req):
        if req.url.path.endswith('/latest'):return httpx.Response(200,json=payload)
        if req.url.path.endswith('/2'):return httpx.Response(200,content=raw)
        if req.url.path.endswith('/3'):return httpx.Response(200,content=signature)
        if req.url.host=='api.github.com':return httpx.Response(302,headers={'Location':'https://release-assets.githubusercontent.com/pacote'})
        assert 'Authorization' not in req.headers
        return httpx.Response(200,content=package)
    return SimpleNamespace(package=package,name=name,raw=raw,signature=signature,key=key,payload=payload,handler=handler)

async def latest(client,current='0.2.2'):
    return await client.latest(current,machine='x86_64',os_release={'ID':'ubuntu','VERSION_ID':'24.04'})

async def test_download_assinado_com_progresso_sem_vazar_token(signed,tmp_path):
    c=ReleaseClient('credencial-github-ficticia',httpx.MockTransport(signed.handler));progress=[]
    try:
        release=await latest(c);assert release.version=='0.3.0' and release.notes=='Melhorias da versão'
        path=await c.download(release,tmp_path,lambda a,b:progress.append((a,b)))
        assert path.read_bytes()==signed.package and progress[-1]==(len(signed.package),len(signed.package))
        trust.verify_package(path,path.with_suffix('.deb.manifest.json').read_bytes(),path.with_suffix('.deb.manifest.sig').read_bytes(),'0.2.2')
        release.sha256='0'*64
        with pytest.raises(ValueError,match='Manifesto'):await c.download(release,tmp_path)
    finally:await c.close()

async def test_versao_atual_e_downgrade(signed):
    c=ReleaseClient(transport=httpx.MockTransport(signed.handler))
    try:
        assert await latest(c,'0.3.0') is None
        assert await latest(c,'0.4.0') is None
        with pytest.raises(ValueError,match='Ubuntu'):await c.latest('0.2.2',machine='x86_64',os_release={'ID':'debian'})
    finally:await c.close()

@pytest.mark.parametrize('alteration',['assinatura','conteudo','repositorio'])
def test_manifesto_adulterado(signed,alteration):
    raw=signed.raw;sig=signed.signature
    if alteration=='assinatura':sig=base64.b64encode(b'0'*64)
    if alteration=='conteudo':raw+=b' '
    if alteration=='repositorio':raw=raw.replace(trust.REPO.encode(),b'invasor/repositorio');sig=base64.b64encode(signed.key.sign(raw))
    with pytest.raises(ValueError,match='Assinatura'):trust.verify_manifest(raw,sig)

async def test_recusa_checksum_sem_assinatura_e_destino_externo(signed):
    signed.payload['assets']=signed.payload['assets'][:1]
    c=ReleaseClient(transport=httpx.MockTransport(signed.handler))
    try:
        with pytest.raises(ValueError,match='manifesto'):await latest(c)
        with pytest.raises(ValueError,match='fora do GitHub'):await c.request('https://externo.invalid/pacote')
    finally:await c.close()

@pytest.mark.parametrize('status',[403,429,503])
async def test_limites_indisponibilidade(status):
    c=ReleaseClient(transport=httpx.MockTransport(lambda r:httpx.Response(status)))
    try:
        with pytest.raises((ValueError,httpx.HTTPStatusError)):await latest(c)
    finally:await c.close()

async def test_download_interrompido_remove_temporario(signed,tmp_path):
    class Broken(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'pac'
            raise httpx.ReadError('interrompido')
    def handler(req):
        if req.url.host!='api.github.com':return httpx.Response(200,stream=Broken())
        return signed.handler(req)
    c=ReleaseClient(transport=httpx.MockTransport(handler))
    try:
        release=await latest(c)
        with pytest.raises(httpx.ReadError):await c.download(release,tmp_path)
        assert not list(tmp_path.iterdir())
    finally:await c.close()

async def test_checksum_tamanho_pacote_invalido(signed,tmp_path):
    def handler(req):
        if req.url.host!='api.github.com':return httpx.Response(200,content=b'x'*len(signed.package))
        return signed.handler(req)
    c=ReleaseClient(transport=httpx.MockTransport(handler))
    try:
        release=await latest(c)
        with pytest.raises(ValueError,match='Integridade'):await c.download(release,tmp_path)
        assert not list(tmp_path.iterdir())
    finally:await c.close()

def test_instalacao_preserva_env_e_confirma_versao(signed,tmp_path,monkeypatch):
    package=tmp_path/signed.name;package.write_bytes(signed.package)
    package.with_suffix('.deb.manifest.json').write_bytes(signed.raw);package.with_suffix('.deb.manifest.sig').write_bytes(signed.signature)
    env=tmp_path/'.env';env.write_text('CONFIGURACAO=preservada\n');before=env.read_bytes()
    monkeypatch.setattr('os.geteuid',lambda:0);calls=[]
    def run(args,**kw):
        calls.append(args)
        if 'dpkg-query' in args[0]:return SimpleNamespace(stdout='0.3.0' if any('apt-get'==Path(c[0]).name for c in calls) else '0.2.2')
        if 'dpkg-deb' in args[0]:return SimpleNamespace(stdout='Package: atlas-coletor\nVersion: 0.3.0\nArchitecture: amd64\n')
        assert args[0]=='/usr/bin/apt-get' and 'install' in args
        assert Path(args[-1]).read_bytes()==signed.package
        return SimpleNamespace(returncode=0)
    assert install_verified(package,runner=run)=='0.3.0'
    assert env.read_bytes()==before
    def fail(args,**kw):
        if args[0]=='/usr/bin/apt-get':raise subprocess.CalledProcessError(1,args)
        return run(args,**kw)
    calls.clear()
    with pytest.raises(subprocess.CalledProcessError):install_verified(package,runner=fail)
    assert env.read_bytes()==before

def test_pacote_incompativel_e_downgrade_bloqueados(signed,tmp_path):
    path=tmp_path/signed.name;path.write_bytes(signed.package)
    with pytest.raises(ValueError,match='incompatível'):
        trust.verify_package(path,signed.raw,signed.signature,'0.2.2',machine='aarch64',os_release={'ID':'ubuntu','VERSION_ID':'24.04'})
    with pytest.raises(ValueError,match='Downgrade'):
        trust.verify_package(path,signed.raw,signed.signature,'0.3.0')
