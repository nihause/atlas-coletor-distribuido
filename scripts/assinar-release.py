#!/usr/bin/env python3
"""Assina manifesto com chave recebida por ambiente, nunca incluída no pacote."""
import argparse,base64,hashlib,json,os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from atlas_worker import __version__
from atlas_worker.release_manifest import REPO,verify_manifest

p=argparse.ArgumentParser();p.add_argument('directory',type=Path);args=p.parse_args()
key=serialization.load_pem_private_key(os.environ['ATLAS_RELEASE_SIGNING_KEY'].encode(),None)
packages=[]
for path in sorted(args.directory.glob('*.deb')):
 arch=path.stem.rsplit('_',1)[1]
 packages.append(dict(name=path.name,arch=arch,os='ubuntu24.04',size=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
if not packages:raise SystemExit('Nenhum pacote para assinar.')
raw=json.dumps(dict(schema=1,repository=REPO,version=__version__,packages=packages),sort_keys=True,separators=(',',':')).encode()
signature=base64.b64encode(key.sign(raw));verify_manifest(raw,signature)
(args.directory/'manifest.json').write_bytes(raw);(args.directory/'manifest.sig').write_bytes(signature)
print('Manifesto assinado e verificado com a chave pública incorporada.')
