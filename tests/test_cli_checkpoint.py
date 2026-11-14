"""Linha de comando, estado local e instaladores (estáticos)."""
import json
import re
from pathlib import Path

import pytest

from atlas_worker import main as cli
from atlas_worker.checkpoint import Checkpoint
from atlas_worker.client import RadarClient
from tests.fakes import FakeRadar, Relogio, TOKEN


def test_checkpoint_atomico_e_ignora_lixo(tmp_path):
    ck = Checkpoint(tmp_path)
    ck.salvar({"id": 7, "tipo": "djen_janela", "lease_token": "x", "params": {}}, ["0-a", "1-b"])
    assert ck.carregar(7) == ["0-a", "1-b"] and [t["id"] for t in ck.pendentes()] == [7]
    (ck.dir / "9.json").write_text("{quebrado", encoding="utf-8")        # arquivo corrompido por queda de energia
    assert [t["id"] for t in ck.pendentes()] == [7] and not (ck.dir / "9.json").exists()
    ck.remover(7)
    assert ck.pendentes() == [] and ck.carregar(7) == []
    assert not list(ck.dir.glob("*.tmp"))


def test_configuracao_invalida_sai_com_codigo_2_e_mensagem(monkeypatch, capsys, tmp_path):
    for k in ("RADAR_API_URL", "WORKER_NAME", "WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as e:
        cli.carregar(None)
    assert e.value.code == 2 and "worker_token" in capsys.readouterr().err.lower()


async def test_verificar_sucesso_e_chave_recusada(cfg, monkeypatch, capsys):
    r = Relogio(); srv = FakeRadar(r)
    monkeypatch.setattr(cli, "RadarClient", lambda c: RadarClient(c, transport=srv.transporte(), sleep=r.dormir))
    assert await cli.verificar(cfg) == 0
    out = capsys.readouterr().out
    assert "Autenticação: ok" in out and "Contrato: 1" in out and "15/min" in out.replace("DJEN remoto 15/min", "15/min")
    srv.token = "outra" * 8
    assert await cli.verificar(cfg) == 4


def test_instaladores_nao_gravam_segredo_e_nao_sobrescrevem():
    raiz = Path(__file__).resolve().parents[1]
    sh = (raiz / "scripts" / "instalar-linux.sh").read_text(encoding="utf-8")
    ps = (raiz / "scripts" / "instalar-windows.ps1").read_text(encoding="utf-8")
    assert "read -r -s" in sh and "Restart=always" in sh and "chmod 600 .env" in sh and "[ -f .env ] && [ \"$FORCAR_CFG\" = \"0\" ]" in sh
    assert "-AsSecureString" in ps and "Test-Path \".env\") -and -not $ForcarConfig" in ps and "RestartCount" in ps
    ex = (raiz / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^WORKER_TOKEN=\s*(#.*)?$", ex, re.M) and "RADAR_API_URL=https://" in ex
    gi = (raiz / ".gitignore").read_text(encoding="utf-8")
    for padrao in (".env", "*.key", "*.log", "*.dump", "*.sql", "cadernos/", ".venv/", "state/"):
        assert padrao in gi


def test_nenhum_segredo_no_repositorio():
    raiz = Path(__file__).resolve().parents[1]
    achados = []
    for f in list(raiz.rglob("*.py")) + list(raiz.rglob("*.sh")) + list(raiz.rglob("*.md")) + list(raiz.rglob("*.ps1")) + [raiz / ".env.example"]:
        if ".venv" in f.parts or f.name.startswith("test_") or f.name == "fakes.py" or f.name == "conftest.py":
            continue
        t = f.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"(?i)(token|senha|password|api[_-]?key)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{24,}", t):
            achados.append(str(f))
    assert achados == []
