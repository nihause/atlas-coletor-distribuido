"""Laço principal: registra, mantém heartbeat, pede tarefas (até MAX_CONCURRENCY ao mesmo tempo), executa, entrega em lotes e conclui.
Regras: o servidor decide o que cada computador faz; uma tarefa só termina quando o servidor confirma que persistiu tudo; ao pausar, a tarefa
atual é devolvida sem penalidade; ao perder a reserva (409) ela é abandonada sem reportar; reinício retoma pelo que o servidor confirmou."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from . import __version__
from .checkpoint import Checkpoint
from .client import ClientError, LeaseLost, NotFound, RadarClient, Rejected, ServerUnavailable, Unauthorized
from .collectors.datajud import DataJud, LoteIncompleto
from .collectors.djen import Djen, ErroDjen
from .collectors.limite import FonteIndisponivel, Limitador
from .config import Settings
from .heartbeat import Heartbeat
from .metrics import Metrics, identidade_maquina
from .tasks import Tarefa

log = logging.getLogger("atlas_worker")


class Devolver(Exception):
    """O servidor pausou/desativou este coletor: devolver a tarefa atual."""


@dataclass
class Contexto:
    tarefa: Tarefa
    lotes_ok: list[str] = field(default_factory=list)
    itens_enviados: int = 0
    inicio: float = field(default_factory=time.monotonic)
    progresso: str = ""


class Worker:
    def __init__(self, cfg: Settings, client: RadarClient, *, http_fontes: httpx.AsyncClient | None = None, sleep=asyncio.sleep, ocioso_max: float = 60.0, escala_tempo: float = 1.0):
        self.cfg, self.client, self._sleep = cfg, client, sleep
        self.metrics = Metrics()
        self.ck = Checkpoint(cfg.state_dir)
        self.parar = asyncio.Event()
        self.pausado = False
        self.max_conc = cfg.max_concurrency
        self.ativas: dict[int, asyncio.Task] = {}
        self.lote_itens = cfg.batch_items
        self.ocioso_max = ocioso_max
        self.escala = escala_tempo   # só os testes mudam (acelera esperas e renovações)
        self.http = http_fontes or httpx.AsyncClient(timeout=cfg.datajud_timeout, follow_redirects=False)
        self._http_proprio = http_fontes is None
        self.lim_djen = Limitador(client, "djen", sleep)
        self.lim_dj = Limitador(client, "datajud", sleep)
        self.hb = Heartbeat(client, self.metrics, cfg.heartbeat_interval, lambda: next(iter(self.ativas), None), self._receber_config, self._perdeu_acesso)

    # ---- controle -----------------------------------------------------------------------------------------------------
    def _receber_config(self, c: dict) -> None:
        cmd = c.get("comando", "continuar")
        if cmd == "parar" and not self.parar.is_set():
            log.warning("servidor desativou este coletor: encerrando")
            self.parar.set()
        novo = cmd == "pausar"
        if novo != self.pausado:
            log.warning("servidor %s este coletor", "pausou" if novo else "retomou")
        self.pausado = novo
        self.max_conc = max(1, min(self.cfg.max_concurrency, int(c.get("max_concorrencia", self.cfg.max_concurrency))))
        self.lote_itens = max(10, min(self.cfg.batch_items, int(c.get("lote_itens", self.cfg.batch_items))))

    def _perdeu_acesso(self) -> None:
        self.parar.set()
        for t in self.ativas.values():
            t.cancel()

    # ---- ciclo de vida ------------------------------------------------------------------------------------------------
    async def iniciar(self) -> None:
        cfg = await self.client.registrar({**identidade_maquina(), "versao": __version__, "nome": self.cfg.worker_name, "max_concorrencia": self.cfg.max_concurrency})
        self._receber_config(cfg)
        log.info("registrado como %s; comando do servidor: %s; até %d tarefas", self.cfg.worker_name, cfg.get("comando"), self.max_conc)

    async def rodar(self, uma_rodada: bool = False) -> None:
        try:
            await self.iniciar()
        except Unauthorized as e:
            log.error("chave recusada pelo servidor (%s); encerrando. Confira WORKER_TOKEN ou peça uma nova chave", e)
            self.parar.set()
            if self._http_proprio:
                await self.http.aclose()
            return
        hb = asyncio.create_task(self.hb.rodar(self.parar))
        try:
            await self._retomar_pendentes()
            ocioso = 0
            while not self.parar.is_set():
                if self.pausado or len(self.ativas) >= self.max_conc:
                    await self._dormir(2)
                    if uma_rodada and not self.ativas:
                        break
                    continue
                try:
                    r = await self.client.reservar(self.cfg.types)
                except Unauthorized:
                    log.error("chave não aceita; encerrando")
                    break
                except ClientError as e:
                    log.warning("não foi possível pedir tarefa: %s", e)
                    await self._dormir(min(120, 5 * 2 ** min(ocioso, 4)))
                    ocioso += 1
                    continue
                if r.get("comando") in ("pausar", "parar"):
                    self._receber_config({"comando": r["comando"]})
                t = r.get("tarefa")
                if not t:
                    if uma_rodada and not self.ativas:
                        break
                    ocioso = min(ocioso + 1, 6)
                    await self._dormir(min(self.ocioso_max, 5 * ocioso))
                    continue
                ocioso = 0
                tarefa = Tarefa.model_validate(t)
                self.ativas[tarefa.id] = asyncio.create_task(self._executar(tarefa))
            await self._esperar_ativas()
        finally:
            self.parar.set()
            await hb
            if self._http_proprio:
                await self.http.aclose()

    async def _dormir(self, s: float) -> None:
        try:
            await asyncio.wait_for(self.parar.wait(), s * self.escala)
        except asyncio.TimeoutError:
            pass

    async def _esperar_ativas(self) -> None:
        if self.ativas:
            _, pend = await asyncio.wait(list(self.ativas.values()), timeout=30)
            for t in pend:
                t.cancel()   # a reserva expira no servidor e a tarefa volta à fila do último checkpoint
            await asyncio.gather(*pend, return_exceptions=True)

    async def _retomar_pendentes(self) -> None:
        """Computador reiniciou no meio de uma tarefa: se a reserva ainda é nossa, continua; senão, descarta."""
        for t in self.ck.pendentes():
            try:
                await self.client.renovar(t["id"], t["lease_token"], "retomada após reinício")
            except (LeaseLost, NotFound):
                log.info("tarefa %s não é mais deste coletor; descartada", t["id"])
                self.ck.remover(t["id"])
                continue
            except ClientError as e:
                log.warning("não foi possível retomar a tarefa %s agora: %s", t["id"], e)
                continue
            log.info("retomando a tarefa %s depois do reinício", t["id"])
            self.ativas[t["id"]] = asyncio.create_task(self._executar(Tarefa.model_validate(t)))

    # ---- execução de uma tarefa -------------------------------------------------------------------------------------------
    async def _executar(self, tarefa: Tarefa) -> None:
        ctx = Contexto(tarefa, self.ck.carregar(tarefa.id))
        self.ck.salvar(tarefa.model_dump(mode="json"), ctx.lotes_ok)
        renovador = asyncio.create_task(self._renovar_enquanto(ctx))
        try:
            log.info("tarefa %s (%s) iniciada", tarefa.id, tarefa.tipo)
            resumo = await (self._djen(ctx) if tarefa.tipo == "djen_janela" else self._datajud(ctx))
            await self.client.concluir(tarefa.id, tarefa.lease_token, resumo)
            self.metrics.tarefas_concluidas += 1
            self.ck.remover(tarefa.id)
            log.info("tarefa %s concluída: %s", tarefa.id, {k: v for k, v in resumo.items() if isinstance(v, (int, float))})
        except (LeaseLost, NotFound) as e:
            log.warning("tarefa %s abandonada (reserva perdida): %s", tarefa.id, e)
            self.ck.remover(tarefa.id)
        except Unauthorized:
            self._perdeu_acesso()
        except Devolver:
            await self._reportar(ctx, "devolvida por pausa/desativação do servidor", sem_penalidade=True)
            self.ck.remover(tarefa.id)
        except asyncio.CancelledError:
            log.warning("tarefa %s interrompida; o servidor recupera a reserva ao vencer", tarefa.id)   # checkpoint local fica para a retomada
            raise
        except (FonteIndisponivel, LoteIncompleto, ErroDjen) as e:
            self.metrics.erros += 1
            await self._reportar(ctx, f"fonte: {e}", retentavel=True)
            self.ck.remover(tarefa.id)
        except (Rejected, ServerUnavailable, ClientError) as e:
            self.metrics.erros += 1
            await self._reportar(ctx, f"servidor: {e}", retentavel=True)
            self.ck.remover(tarefa.id)
        except Exception as e:  # noqa: BLE001 — um erro numa tarefa nunca derruba o coletor
            self.metrics.erros += 1
            log.exception("erro inesperado na tarefa %s", tarefa.id)
            await self._reportar(ctx, f"{type(e).__name__}: {e}", retentavel=True)
            self.ck.remover(tarefa.id)
        finally:
            renovador.cancel()
            self.ativas.pop(tarefa.id, None)

    async def _reportar(self, ctx: Contexto, erro: str, *, retentavel: bool = True, sem_penalidade: bool = False) -> None:
        try:
            await self.client.falhar(ctx.tarefa.id, ctx.tarefa.lease_token, erro, retentavel=retentavel, sem_penalidade=sem_penalidade)
        except ClientError as e:
            log.warning("não foi possível reportar a falha da tarefa %s: %s (a reserva expira sozinha)", ctx.tarefa.id, e)

    async def _renovar_enquanto(self, ctx: Contexto) -> None:
        """Renova a reserva a cada 2 min (e a cada heartbeat do servidor); perder a reserva cancela a tarefa; pausa é anotada."""
        t = ctx.tarefa
        while True:
            await asyncio.sleep(120 * self.escala)
            try:
                r = await self.client.renovar(t.id, t.lease_token, ctx.progresso or None)
                if r.get("comando") == "pausar":
                    self.pausado = True
            except (LeaseLost, NotFound):
                alvo = self.ativas.get(t.id)
                if alvo:
                    alvo.cancel()
                return
            except ClientError as e:
                log.warning("renovação da tarefa %s falhou: %s", t.id, e)

    def _checar_pausa(self) -> None:
        if self.pausado or self.parar.is_set():
            raise Devolver()

    # ---- tipos de tarefa ---------------------------------------------------------------------------------------------------
    async def _djen(self, ctx: Contexto) -> dict:
        p = ctx.tarefa.djen()
        d = Djen(self.lim_djen, self.http, self.lote_itens)
        async for chave, lote in d.janela(p):
            self._checar_pausa()
            if chave in ctx.lotes_ok:
                ctx.itens_enviados += len(lote)
                continue   # o servidor já confirmou este lote antes do reinício
            await self.client.resultados(ctx.tarefa.id, ctx.tarefa.lease_token, chave, lote)   # só segue depois do persistido=true
            ctx.lotes_ok.append(chave)
            ctx.itens_enviados += len(lote)
            self.metrics.itens_enviados += len(lote)
            ctx.progresso = f"{d.paginas} páginas, {ctx.itens_enviados} itens"
            self.ck.salvar(ctx.tarefa.model_dump(mode="json"), ctx.lotes_ok)
        self.metrics.requisicoes["djen"] += self.lim_djen.requisicoes
        return {"itens_enviados": ctx.itens_enviados, "total_itens": d.total_itens, "paginas": d.paginas, "dividida": d.dividida, "duracao_s": int(time.monotonic() - ctx.inicio)}

    async def _datajud(self, ctx: Contexto) -> dict:
        p = ctx.tarefa.datajud()
        if not self.cfg.datajud_api_key.get_secret_value():
            raise Rejected("DATAJUD_API_KEY não configurada neste computador")
        regs, nao = await DataJud(self.lim_dj, self.http, self.cfg.datajud_api_key.get_secret_value()).lote(p)
        for i in range(0, len(regs), 25):
            self._checar_pausa()
            chave = f"d{i // 25}-{len(regs[i:i + 25])}"
            if chave not in ctx.lotes_ok:
                await self.client.resultados(ctx.tarefa.id, ctx.tarefa.lease_token, chave, regs[i:i + 25])
                ctx.lotes_ok.append(chave)
                self.ck.salvar(ctx.tarefa.model_dump(mode="json"), ctx.lotes_ok)
            ctx.itens_enviados += len(regs[i:i + 25])
        self.metrics.requisicoes["datajud"] += self.lim_dj.requisicoes
        return {"encontrados": sorted({r["numero_cnj"] for r in regs}), "nao_localizados": nao, "itens_enviados": ctx.itens_enviados}
