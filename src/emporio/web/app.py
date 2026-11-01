"""Interface web do atendimento (SPEC-006), no estilo do painel do projeto ALJ: FastAPI + Jinja2 +
Bootstrap 5 + HTMX, sem build de front-end.

- `/`          atendimento: a conversa com a Lia, roteiro de perguntas, chegada por canal (SPEC-005) e o
               rastro das tools em cada resposta;
- `/vendedor`  painel do vendedor: a fila de alertas (SPEC-003), atualizada a cada 2 s, com som no navegador.

O agente é o mesmo do CLI e dos evals; a interface só mostra. Um processo, conversas em memória
(protótipo): cada navegador tem a sua, identificada por um cookie aleatório.
"""

from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from emporio.agent import Agente, Conversa
from emporio.agent.prompt import AVISO_PRIVACIDADE
from emporio.alertas.central import caminho_fila, ler_fila
from emporio.config import Config, montar_agente
from emporio.rules import origem as origem_lead
from emporio.rules.horario import FUSO

PASTA = Path(__file__).resolve().parent
COOKIE = "emporio_conversa"
LIMITE_TEXTO = 1000
PERGUNTAS = (
    "Quais violões vocês têm até R$ 1000?",
    "Quanto custa o Takamine GD20?",
    "Estão abertos agora?",
    "Me arrependi da compra, posso devolver?",
    "Qual o status do pedido 8? Telefone (67) 99654-7821",
    "Quero falar com um vendedor",
)


@dataclass
class Mensagem:
    de: str                                   # "cliente", "lia" ou "alerta"
    texto: str
    hora: str
    aviso: bool = False                       # a resposta trouxe o aviso de privacidade
    rastro: list = field(default_factory=list)
    detalhes: str = ""                        # latência, tokens e custo do turno
    segura: bool = False
    origem: str | None = None


@dataclass
class Atendimento:
    conversa: Conversa
    mensagens: list[Mensagem] = field(default_factory=list)


def formatar(texto: str) -> Markup:
    """Markdown mínimo e seguro das respostas: escapa tudo, depois **negrito** e _itálico_."""
    seguro = str(escape(texto))
    seguro = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", seguro)
    seguro = re.sub(r"(?<![\w/])_(.+?)_(?![\w/])", r"<em>\1</em>", seguro)
    return Markup(seguro)


def criar_app(agente: Agente | None = None, config: Config | None = None) -> FastAPI:
    config = config or Config.do_ambiente()
    agente = agente or montar_agente(config)
    if agente.alertas is not None:
        agente.alertas.avisar = None              # na web o alerta aparece na conversa e no painel do vendedor
    fila = agente.alertas.fila if agente.alertas is not None else caminho_fila()
    atendimentos: dict[str, Atendimento] = {}
    trava = threading.Lock()                       # protótipo de um processo: um turno por vez

    app = FastAPI(title="Empório da Música · atendimento", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")
    tpl = Jinja2Templates(directory=PASTA / "templates")
    tpl.env.filters["formatar"] = formatar

    def hora() -> str:
        return datetime.now(FUSO).strftime("%H:%M")

    def atual(request: Request) -> tuple[str, Atendimento]:
        chave = request.cookies.get(COOKIE) or ""
        if chave not in atendimentos:
            chave = uuid.uuid4().hex
            atendimentos[chave] = Atendimento(agente.nova_conversa())
        return chave, atendimentos[chave]

    def contexto(request: Request, at: Atendimento) -> dict:
        s = at.conversa.sessao
        o = origem_lead.POR_CHAVE.get(s.origem or "")
        return {
            "request": request, "mensagens": at.mensagens, "perguntas": PERGUNTAS, "origens": origem_lead.ORIGENS,
            "mensagem_canal": origem_lead.MENSAGEM_PADRAO, "inicio": not at.mensagens,
            "modelo": agente.llm.modelo, "demo": agente.llm.modelo.startswith("demo/"),
            "origem": f"{o.marcador} {o.nome}" if o else None, "pedido": s.pedido_verificado,
            "protocolos": s.registros, "data_referencia": config.data_referencia,
        }

    def com_cookie(resposta, chave: str):
        resposta.set_cookie(COOKIE, chave, httponly=True, samesite="lax")
        return resposta

    @app.get("/", response_class=HTMLResponse)
    def atendimento(request: Request):
        chave, at = atual(request)
        return com_cookie(tpl.TemplateResponse(request, "atendimento.html", contexto(request, at)), chave)

    @app.post("/mensagem", response_class=HTMLResponse)
    def mensagem(request: Request, texto: str = Form("")):
        chave, at = atual(request)
        texto = " ".join(texto.split())[:LIMITE_TEXTO]
        if texto:
            with trava:
                at.mensagens.append(Mensagem("cliente", texto, hora()))
                resp = agente.responder(at.conversa, texto)
            for a in resp.alertas:
                at.mensagens.append(Mensagem("alerta", a.aviso(), hora()))
            corpo, aviso = resp.texto, False
            if corpo.endswith(AVISO_PRIVACIDADE):
                corpo, aviso = corpo[: -len(AVISO_PRIVACIDADE)].rstrip(), True
            at.mensagens.append(Mensagem(
                "lia", corpo, hora(), aviso=aviso, segura=resp.segura, origem=resp.origem,
                rastro=[{"tool": e.tool, "args": e.argumentos, "resultado": e.resultado, "ms": e.duracao_ms,
                         "erro": e.erro} for e in resp.rastro],
                detalhes=f"{resp.latencia_s:.1f} s · {resp.tokens_entrada}+{resp.tokens_saida} tokens · "
                         f"US$ {resp.custo_usd:.5f}"))
        if request.headers.get("HX-Request"):
            return com_cookie(tpl.TemplateResponse(request, "_painel.html", contexto(request, at)), chave)
        return com_cookie(RedirectResponse("/", status_code=303), chave)

    @app.post("/nova")
    def nova(request: Request):
        chave, _ = atual(request)
        atendimentos[chave] = Atendimento(agente.nova_conversa())
        return com_cookie(RedirectResponse("/", status_code=303), chave)

    def alertas() -> list[dict]:
        itens = ler_fila(fila)[-50:]
        for a in itens:
            o = origem_lead.POR_CHAVE.get(a.get("origem") or "")
            a["origem_rotulo"] = f"{o.marcador} {o.nome}" if o else None
            a["hora"] = (a.get("quando") or "")[11:16]
        return list(reversed(itens))

    @app.get("/vendedor", response_class=HTMLResponse)
    def vendedor(request: Request):
        return tpl.TemplateResponse(request, "vendedor.html", {"request": request, "alertas": alertas()})

    @app.get("/vendedor/alertas", response_class=HTMLResponse)
    def vendedor_alertas(request: Request):
        return tpl.TemplateResponse(request, "_alertas.html", {"request": request, "alertas": alertas()})

    return app
