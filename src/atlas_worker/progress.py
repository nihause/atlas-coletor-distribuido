"""Dados públicos de uma tarefa: nunca expõe reserva, token ou registros coletados."""
from __future__ import annotations

from dataclasses import dataclass, field
import time

from .tasks import Tarefa


def describe(task: Tarefa) -> tuple[str, str]:
    params = task.params
    if task.tipo == 'datajud_lote':
        return f"{params.get('tribunal', 'DataJud')} · {len(params.get('cnjs', []))} processos", 'Lote de movimentações'
    queries = params.get('consultas', [])
    first = queries[0].get('params', {}) if queries else {}
    target = params.get('descricao') or first.get('nomeParte') or first.get('nomeAdvogado')
    if not target:
        target = ('OAB ' + str(first['numeroOab']) + '/' + str(first.get('ufOab', ''))) if first.get('numeroOab') else 'Favorito #' + str(params.get('favorito', {}).get('ref_id', ''))
    return str(target)[:180], f"{params.get('de', '—')} até {params.get('ate', '—')} · {len(queries)} consulta(s)"


@dataclass
class Contexto:
    tarefa: Tarefa
    lotes_ok: list[str] = field(default_factory=list)
    itens_enviados: int = 0
    inicio: float = field(default_factory=time.monotonic)
    progresso: str = ''
    fase: str = 'Preparando consulta'
    paginas: int = 0
    lidos: int = 0
    encontrados: int = 0

    def snapshot(self) -> dict:
        target, period = describe(self.tarefa)
        return {'id': self.tarefa.id, 'fonte': 'DJEN' if self.tarefa.tipo == 'djen_janela' else 'DataJud',
                'alvo': target, 'periodo': period, 'fase': self.fase, 'paginas': self.paginas,
                'lidos': self.lidos, 'encontrados': self.encontrados, 'confirmados': self.itens_enviados,
                'duracao': int(time.monotonic() - self.inicio)}
