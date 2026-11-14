"""Estado local mínimo para o coletor reiniciar sem perder o fio: a tarefa em curso e quais lotes o servidor já confirmou.
O servidor é a fonte da verdade (reserva, checkpoint do favorito, idempotência por lote); isto só evita refazer trabalho."""
from __future__ import annotations

import json
import os
from pathlib import Path


class Checkpoint:
    def __init__(self, state_dir: Path):
        self.dir = state_dir / "tarefas"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _p(self, tarefa_id: int) -> Path:
        return self.dir / f"{int(tarefa_id)}.json"

    def salvar(self, tarefa: dict, lotes_ok: list[str]) -> None:
        tmp = self._p(tarefa["id"]).with_suffix(".tmp")
        tmp.write_text(json.dumps({"tarefa": tarefa, "lotes_ok": sorted(lotes_ok)}), encoding="utf-8")
        os.replace(tmp, self._p(tarefa["id"]))   # troca atômica: nunca fica meio gravado

    def carregar(self, tarefa_id: int) -> list[str]:
        try:
            return list(json.loads(self._p(tarefa_id).read_text(encoding="utf-8")).get("lotes_ok", []))
        except (OSError, ValueError):
            return []

    def pendentes(self) -> list[dict]:
        """Tarefas que estavam em curso quando o computador parou/reiniciou."""
        out = []
        for f in sorted(self.dir.glob("*.json")):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8"))["tarefa"])
            except (OSError, ValueError, KeyError):
                f.unlink(missing_ok=True)
        return out

    def remover(self, tarefa_id: int) -> None:
        self._p(tarefa_id).unlink(missing_ok=True)
