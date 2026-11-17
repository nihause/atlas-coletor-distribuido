"""Servidor central simulado (contrato v1) e fontes simuladas. Sem rede. O relógio é virtual: dormir avança o tempo."""
from __future__ import annotations

import json
from collections import defaultdict

import httpx

TOKEN = "t" * 40


class Relogio:
    def __init__(self) -> None:
        self.t = 1000.0
        self.dormidas: list[float] = []

    async def dormir(self, s: float) -> None:
        import asyncio
        self.dormidas.append(s)
        self.t += s
        await asyncio.sleep(0)


class FakeRadar:
    """Implementa o contrato: reserva com token, resultados idempotentes por (tarefa, chave), conclusão só com tudo confirmado,
    limite global de requisições por fonte, pausa/desativação, expiração de reserva."""

    def __init__(self, relogio: Relogio, limite_min: dict | None = None):
        self.r = relogio
        self.token = TOKEN
        self.estado = "ativo"
        self.fila: list[dict] = []
        self.tarefas: dict[int, dict] = {}
        self.chamadas: list[tuple[str, dict]] = []
        self.limite_min = limite_min or {"djen": 15, "datajud": 60}
        self.proxima_vaga: dict[str, float] = defaultdict(float)
        self.vagas: dict[str, list[float]] = defaultdict(list)
        self.pausa_ate: dict[str, float] = defaultdict(float)
        self.falha_na_rede = 0          # próximas N chamadas levantam erro de conexão
        self.responder_5xx = 0          # próximas N chamadas respondem 503
        self.resultados_perdidos = 0    # próximas N respostas de "resultados" não chegam, MAS o servidor grava (perda de conexão depois de gravar)
        self.itens_gravados: dict[str, int] = defaultdict(int)   # item → quantas vezes foi gravado
        self.max_conc = 2
        self.coletores: set[str] = set()

    def adicionar_djen(self, tid: int, itens_esperados: int = 0, **params) -> None:
        p = {"favorito": {"tipo": "parte", "ref_id": 1}, "de": "2026-11-03", "ate": "2026-11-03", "janela_dias": 1, "base_dias": 1,
             "consultas": [{"params": {"nomeParte": "Banco Exemplo"}, "filtro": {"tipo": "parte", "termo_norm": "BANCO EXEMPLO"}}]}
        p.update(params)
        self.fila.append({"id": tid, "tipo": "djen_janela", "params": p})

    def adicionar_datajud(self, tid: int, cnjs: list[str]) -> None:
        self.fila.append({"id": tid, "tipo": "datajud_lote", "params": {"tribunal": "TJPR", "alias": "api_publica_tjpr", "cnjs": cnjs, "ids": list(range(len(cnjs)))}})

    def expirar(self, tid: int) -> None:
        self.tarefas[tid]["status"] = "expirada"
        self.fila.insert(0, {"id": tid, "tipo": self.tarefas[tid]["tipo"], "params": self.tarefas[tid]["params"], "reenfileirada": True})

    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._tratar)

    def _resp(self, status: int, dados=None, erro: str | None = None) -> httpx.Response:
        if erro:
            return httpx.Response(status, json={"erro": {"codigo": "x", "mensagem": erro}})
        return httpx.Response(status, json={"contrato": 1, "dados": dados})

    def _cfg(self) -> dict:
        return {"contrato": 1, "comando": {"ativo": "continuar", "pausado": "pausar", "desativado": "parar"}[self.estado], "max_concorrencia": self.max_conc,
                "lote_itens": 100, "limites": {"datajud_min": self.limite_min["datajud"], "djen_min": self.limite_min["djen"]}}

    def _tratar(self, req: httpx.Request) -> httpx.Response:
        if self.falha_na_rede > 0:
            self.falha_na_rede -= 1
            raise httpx.ConnectError("sem rota")
        if req.headers.get("authorization") != f"Bearer {self.token}":
            return self._resp(401, erro="Token ausente, expirado ou revogado.")
        if req.headers.get("x-contrato") != "1":
            return self._resp(400, erro="contrato incompatível")
        if self.responder_5xx > 0:
            self.responder_5xx -= 1
            return self._resp(503, erro="indisponível")
        rota = req.url.path.split("/coletores.php/")[1]
        corpo = json.loads(req.content) if req.content else dict(req.url.params)
        self.chamadas.append((rota, corpo))
        h = getattr(self, "_h_" + rota.replace("/", "_"))
        return h(corpo)

    # ---- rotas -----------------------------------------------------------------------------------------------------------
    def _h_registrar(self, c):
        self.coletores.add(c["coletor"])
        return self._resp(200, self._cfg())

    _h_heartbeat = _h_registrar
    _h_configuracao = _h_registrar

    def _h_tarefas_reservar(self, c):
        if self.estado != "ativo":
            return self._resp(200, {"tarefa": None, "comando": self._cfg()["comando"]})
        ativas = sum(1 for t in self.tarefas.values() if t["status"] == "reservada" and t["coletor"] == c["coletor"])
        if ativas >= self.max_conc or not self.fila:
            return self._resp(200, {"tarefa": None, "comando": "continuar"})
        t = self.fila.pop(0)
        tok = f"tok{t['id']}x{len(self.tarefas)}".ljust(32, "0")[:32]
        self.tarefas[t["id"]] = {"tipo": t["tipo"], "params": t["params"], "status": "reservada", "coletor": c["coletor"], "token": tok, "lotes": {}, "itens": 0, "concluida": None, "falhas": []}
        return self._resp(200, {"tarefa": {"id": t["id"], "tipo": t["tipo"], "lease_token": tok, "lease_ate": "2026-11-14 18:00:00", "params": t["params"]}, "comando": "continuar"})

    def _lease(self, c):
        t = self.tarefas.get(c["tarefa_id"])
        if not t or t["coletor"] != c["coletor"] or t["token"] != c["lease_token"]:
            return None, self._resp(404, erro="Tarefa não encontrada para este coletor.")
        if t["status"] != "reservada":
            return None, self._resp(409, erro="Reserva perdida: a tarefa está " + t["status"])
        return t, None

    def _h_tarefas_renovar(self, c):
        t, e = self._lease(c)
        return e or self._resp(200, {"lease_ate": "2026-11-14 18:10:00", "comando": self._cfg()["comando"]})

    def _h_resultados(self, c):
        t, e = self._lease(c)
        if e:
            return e
        itens = c["itens"]
        dup = c["chave"] in t["lotes"]
        if not dup:
            t["lotes"][c["chave"]] = len(itens)
            t["itens"] += len(itens)
            for x in itens:
                chave = str(x["item"]["id"]) if "item" in x else str(x.get("numero_cnj"))
                self.itens_gravados[f"{c['tarefa_id']}:{chave}"] += 1
        if self.resultados_perdidos > 0:
            self.resultados_perdidos -= 1
            raise httpx.ReadTimeout("resposta perdida")
        return self._resp(200, {"persistido": True, "duplicado": dup, "itens": t["lotes"][c["chave"]], "aceitos": t["lotes"][c["chave"]], "desconhecidos": 0, "rejeitados": 0})

    def _h_tarefas_concluir(self, c):
        t, e = self._lease(c)
        if e:
            return e
        r = c["resumo"]
        if t["tipo"] == "djen_janela" and r.get("itens_enviados") != t["itens"]:
            return self._resp(409, erro=f"Itens declarados ({r.get('itens_enviados')}) diferem dos confirmados ({t['itens']})")
        t["status"], t["concluida"] = "concluida", r
        return self._resp(200, {"concluida": True})

    def _h_tarefas_falhar(self, c):
        t, e = self._lease(c)
        if e:
            return e
        t["status"] = "devolvida" if c["sem_penalidade"] else "falhou"
        t["falhas"].append(c)
        return self._resp(200, {"registrada": True, "status": t["status"]})

    def _h_limites_vaga(self, c):
        f = c["fonte"]
        if self.pausa_ate[f] > self.r.t:
            return self._resp(200, {"espera_s": self.pausa_ate[f] - self.r.t, "pausa": True})
        intervalo = 60 / self.limite_min[f]
        vaga = max(self.proxima_vaga[f], self.r.t)
        self.proxima_vaga[f] = vaga + intervalo
        self.vagas[f].append(vaga)
        return self._resp(200, {"espera_s": vaga - self.r.t, "pausa": False, "limite_min": self.limite_min[f]})

    def _h_limites_resultado(self, c):
        if c["http"] == 429:
            self.pausa_ate[c["fonte"]] = self.r.t + (c.get("retry_after") or 15)
        return self._resp(200, {"pausa_s": 0})


class FakeFontes:
    """DJEN e DataJud simulados. DJEN: dicionário nomeParte -> lista de itens; paginação de 100."""

    def __init__(self) -> None:
        self.djen: dict[str, list[dict]] = {}
        self.djen_http = 200
        self.djen_count_fake: int | None = None
        self.djen_repete = False
        self.datajud: dict[str, dict] = {}
        self.datajud_http: list[int] = []
        self.requisicoes = {"djen": 0, "datajud": 0}

    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._tratar)

    def _tratar(self, req: httpx.Request) -> httpx.Response:
        if req.url.host == "comunicaapi.pje.jus.br":
            self.requisicoes["djen"] += 1
            if self.djen_http != 200:
                return httpx.Response(self.djen_http, headers={"Retry-After": "30"} if self.djen_http == 429 else {}, json={})
            q = dict(req.url.params)
            itens = self.djen.get(q.get("nomeParte") or q.get("nomeAdvogado") or q.get("orgaoId") or "", [])
            de, ate = q["dataDisponibilizacaoInicio"], q["dataDisponibilizacaoFim"]
            itens = [i for i in itens if de <= i["data_disponibilizacao"] <= ate]
            pag = int(q["pagina"])
            if self.djen_repete and pag > 1:
                return httpx.Response(200, json={"count": 100, "items": itens[:100]})
            return httpx.Response(200, json={"count": self.djen_count_fake or len(itens[(pag - 1) * 100:pag * 100]), "items": itens[(pag - 1) * 100:pag * 100]})
        if req.url.host == "api-publica.datajud.cnj.jus.br":
            self.requisicoes["datajud"] += 1
            if self.datajud_http:
                cod = self.datajud_http.pop(0)
                if cod != 200:
                    return httpx.Response(cod, json={"error": "x"})
            cnjs = json.loads(req.content)["query"]["terms"]["numeroProcesso"]
            hits = [{"_id": f"TJPR_G1_{c}", "_source": self.datajud[c]} for c in cnjs if c in self.datajud]
            return httpx.Response(200, json={"took": 5, "timed_out": False, "_shards": {"failed": 0}, "hits": {"total": {"value": len(hits), "relation": "eq"}, "hits": hits}})
        return httpx.Response(404)


def item(i: int, parte: str = "BANCO EXEMPLO S.A.", dia: str = "2026-11-03") -> dict:
    return {"id": i, "numero_processo": f"{i:020d}", "data_disponibilizacao": dia, "destinatarios": [{"nome": parte, "polo": "A"}], "destinatarioadvogados": [], "texto": "t"}


def doc(cnj: str, sigilo: int = 0) -> dict:
    return {"numeroProcesso": cnj, "grau": "G1", "nivelSigilo": sigilo, "classe": {"codigo": 7, "nome": "Procedimento"}, "orgaoJulgador": {"codigo": 9161, "nome": "Vara"}, "assuntos": [{"codigo": 1, "nome": "A"}],
            "dataAjuizamento": "2024-01-10T00:00:00.000Z", "dataHoraUltimaAtualizacao": "2026-11-01T00:00:00.000Z", "movimentos": [{"codigo": 26, "nome": "Distribuição", "dataHora": "2024-01-10T10:00:00.000Z"}]}
