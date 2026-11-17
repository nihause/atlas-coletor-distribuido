"""Progresso antes do primeiro lote, confirmação real e ausência de credenciais."""
import asyncio

import httpx

from atlas_worker.tasks import Tarefa
from atlas_worker.progress import Contexto
from tests.conftest import novo_worker
from tests.fakes import item, doc, TOKEN


async def test_progresso_djen_antes_do_primeiro_envio_e_heartbeat(cfg,mundo):
    _,srv,fontes=mundo
    fontes.djen['Banco Exemplo']=[item(i) for i in range(1,251)]
    srv.adicionar_djen(1)
    w,c=novo_worker(cfg,mundo)
    await w.http.aclose()
    reached=asyncio.Event();release=asyncio.Event()
    original=fontes.transporte()
    async def fonte(req):
        if req.url.params.get('pagina')=='2':
            reached.set();await release.wait()
        return await original.handle_async_request(req)
    w.http=httpx.AsyncClient(transport=httpx.MockTransport(fonte))
    await w.iniciar()
    tarefa=Tarefa.model_validate((await c.reservar(cfg.types))['tarefa'])
    job=asyncio.create_task(w._executar(tarefa));w.ativas[tarefa.id]=job
    try:
        await asyncio.wait_for(reached.wait(),3)
        ctx=w.contextos[1]
        assert ctx.lidos==100 and ctx.paginas==1 and ctx.itens_enviados==0
        assert ctx.snapshot()['alvo']=='Banco Exemplo'
        assert '2026-11-03 até 2026-11-03' in ctx.snapshot()['periodo']
        assert tarefa.lease_token not in repr(ctx.snapshot()) and TOKEN not in repr(ctx.snapshot())
        await w.hb.uma_vez()
        hb=[body for rota,body in srv.chamadas if rota=='heartbeat'][-1]
        assert hb['progresso_tarefas'][0]['id']==1 and '100 lidos' in hb['progresso_tarefas'][0]['progresso']
        release.set();await asyncio.wait_for(job,5)
        assert w.metrics.itens_lidos==250 and w.metrics.itens_encontrados==250
        assert w.metrics.itens_enviados==250 and not w.contextos
        assert w.recentes[0]['fase']=='Concluída' and w.recentes[0]['confirmados']==250
    finally:
        release.set();await asyncio.gather(job,return_exceptions=True)
        await w.http.aclose();await c.aclose()


async def test_contagem_so_aumenta_apos_confirmacao_e_nao_no_envio(cfg,mundo):
    _,srv,fontes=mundo
    fontes.djen['Banco Exemplo']=[item(1)]
    srv.adicionar_djen(1);w,c=novo_worker(cfg,mundo);await w.iniciar()
    tarefa=Tarefa.model_validate((await c.reservar(cfg.types))['tarefa'])
    original=c.resultados
    observed=[]
    async def verificar(*args):
        observed.append((w.contextos[1].itens_enviados,w.metrics.itens_enviados))
        return await original(*args)
    c.resultados=verificar
    await w._executar(tarefa)
    assert observed==[(0,0)] and w.metrics.itens_enviados==1
    await w.http.aclose();await c.aclose()


def test_descricao_datajud_nao_expoe_lista_nem_reserva():
    tarefa=Tarefa(id=8,tipo='datajud_lote',lease_token='segredo-de-reserva-ficticio',params={'tribunal':'TJPR','cnjs':['1'*20,'2'*20]})
    snap=Contexto(tarefa).snapshot()
    assert snap['alvo']=='TJPR · 2 processos'
    assert tarefa.lease_token not in repr(snap) and '1'*20 not in repr(snap)

async def test_atualizacao_aguarda_tarefa_sem_cancelar_e_sem_novas_reservas(cfg,mundo):
    _,srv,fontes=mundo
    fontes.djen['Banco Exemplo']=[item(1)];srv.adicionar_djen(1);srv.adicionar_djen(2)
    w,c=novo_worker(cfg,mundo);w.max_conc=1
    arrived=asyncio.Event();release=asyncio.Event()
    original=fontes.transporte()
    async def fonte(req):
        arrived.set();await release.wait();return await original.handle_async_request(req)
    await w.http.aclose();w.http=httpx.AsyncClient(transport=httpx.MockTransport(fonte))
    motor=asyncio.create_task(w.rodar())
    try:
        await asyncio.wait_for(arrived.wait(),3);w.drenando=True
        reservations=len([x for x in srv.chamadas if x[0]=='tarefas/reservar']);initial=len(w.ativas)
        await asyncio.sleep(.08)
        assert not motor.done() and not w.parar.is_set() and w.ativas
        assert len([x for x in srv.chamadas if x[0]=='tarefas/reservar'])==reservations
        release.set();await asyncio.wait_for(motor,3)
        assert w.metrics.tarefas_concluidas==initial and srv.tarefas[1]['concluida'] is not None
        assert len([x for x in srv.chamadas if x[0]=='tarefas/reservar'])==reservations
    finally:
        release.set();w.parar.set();await asyncio.gather(motor,return_exceptions=True);await c.aclose();await w.http.aclose()
