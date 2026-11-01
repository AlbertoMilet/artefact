"""Interface web (SPEC-006 e SPEC-007), no estilo do painel do projeto ALJ: FastAPI + Jinja2 +
Bootstrap 5 + HTMX, sem build de front-end.

- `/atendimento`            painel da loja: conversas, alertas e o histórico de cada conversa; o vendedor
                            assume a conversa (a Lia pausa), responde e devolve à Lia;
- `/simulador`              simulador de WhatsApp: você é o cliente, identificado pelo telefone.

O agente é o mesmo do CLI e dos evals; a camada web só guarda o histórico (mascarado) e mostra.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from emporio.agent import Agente, Conversa
from emporio.agent.prompt import AVISO_PRIVACIDADE
from emporio.config import Config, montar_agente
from emporio.rules import origem as origem_lead
from emporio.web.auth import Limitador, Sessoes, carregar_usuarios, conferir_senha, hash_senha, segredo_da_sessao
from emporio.web.repositorio import Repositorio

PASTA = Path(__file__).resolve().parent
COOKIE_TELEFONE = "emporio_telefone"
COOKIE_SESSAO = "emporio_sessao"
LIVRES = ("/login", "/static/")
USUARIO_DEMO, SENHA_DEMO = "demo", "demo1234"
TELEFONE_PADRAO = "(67) 98888-0001"
LIMITE_TEXTO = 1000
PERGUNTAS = (
    "Quais violões vocês têm até R$ 1000?",
    "Quanto custa o Takamine GD20?",
    "Estão abertos agora?",
    "Me arrependi da compra, posso devolver?",
    "Qual o status do pedido 8? Telefone (67) 99654-7821",
    "Quero falar com um vendedor",
)
ROTULO_VENDEDOR = "Vendedor da loja"


def formatar(texto: str) -> Markup:
    """Markdown mínimo e seguro das respostas: escapa tudo, depois **negrito** e _itálico_."""
    seguro = str(escape(texto))
    seguro = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", seguro)
    seguro = re.sub(r"(?<![\w/])_(.+?)_(?![\w/])", r"<em>\1</em>", seguro)
    return Markup(seguro)


def rotulo_origem(chave: str | None) -> str | None:
    o = origem_lead.POR_CHAVE.get(chave or "")
    return f"{o.marcador} {o.nome}" if o else None


def criar_app(agente: Agente | None = None, config: Config | None = None,
              repositorio: Repositorio | None = None, usuarios: dict[str, str] | None = None,
              sessoes: Sessoes | None = None) -> FastAPI:
    config = config or Config.do_ambiente()
    agente = agente or montar_agente(config)
    repo = repositorio or Repositorio()
    demo = agente.llm.modelo.startswith("demo/")
    usuarios = carregar_usuarios() if usuarios is None else usuarios
    login_demo = not usuarios and demo           # só no modo demonstração e só sem usuários no .env
    if login_demo:
        usuarios = {USUARIO_DEMO: hash_senha(SENHA_DEMO)}
    sessoes = sessoes or Sessoes(segredo_da_sessao()[0])
    limitador = Limitador()
    if agente.alertas is not None:
        agente.alertas.avisar = None              # na web o alerta vai para a conversa e para o painel
    memoria: dict[str, Conversa] = {}             # estado do agente por conversa (o histórico fica no banco)
    trava = threading.Lock()                       # protótipo de um processo: um turno por vez

    app = FastAPI(title="Empório da Música · atendimento", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")
    tpl = Jinja2Templates(directory=PASTA / "templates")
    tpl.env.filters["formatar"] = formatar
    tpl.env.filters["origem"] = rotulo_origem
    base = {"modelo": agente.llm.modelo, "demo": demo}

    def pagina(request: Request, arquivo: str, **ctx):
        usuario = getattr(request.state, "usuario", None)
        return tpl.TemplateResponse(request, arquivo, {"request": request, "usuario": usuario, **base, **ctx})

    # ---------------------------------------------------------------- login (SPEC-008)
    @app.middleware("http")
    async def exigir_login(request: Request, chamar):
        request.state.usuario = sessoes.validar(request.cookies.get(COOKIE_SESSAO))
        if request.state.usuario not in usuarios:
            request.state.usuario = None
        if request.state.usuario is None and not request.url.path.startswith(LIVRES):
            if request.headers.get("HX-Request"):
                return HTMLResponse("", status_code=401, headers={"HX-Redirect": "/login"})
            proximo = request.url.path if request.method == "GET" else "/"
            return RedirectResponse(f"/login?proximo={quote(proximo)}", status_code=303)
        return await chamar(request)

    def destino_seguro(proximo: str | None) -> str:
        return proximo if proximo and proximo.startswith("/") and not proximo.startswith("//") else "/atendimento"

    @app.get("/login", response_class=HTMLResponse)
    def login(request: Request, proximo: str = "/atendimento"):
        return pagina(request, "login.html", proximo=destino_seguro(proximo), sem_usuarios=not usuarios,
                      login_demo=login_demo, usuario_demo=USUARIO_DEMO, senha_demo=SENHA_DEMO)

    @app.post("/login", response_class=HTMLResponse)
    def entrar(request: Request, usuario: str = Form(""), senha: str = Form(""), proximo: str = Form("/")):
        origem = request.client.host if request.client else "?"
        ctx = {"proximo": destino_seguro(proximo), "sem_usuarios": not usuarios, "login_demo": login_demo,
               "usuario_demo": USUARIO_DEMO, "senha_demo": SENHA_DEMO, "nome": usuario[:64]}
        espera = limitador.bloqueado(origem)
        if espera:
            return pagina(request, "login.html", erro=f"Muitas tentativas. Tente de novo em {espera} s.", **ctx)
        guardado = usuarios.get(usuario.strip())
        if guardado is None or not conferir_senha(senha, guardado):
            limitador.falhou(origem)
            return pagina(request, "login.html", erro="Usuário ou senha incorretos.", **ctx)
        limitador.acertou(origem)
        resposta = RedirectResponse(ctx["proximo"], status_code=303)
        resposta.set_cookie(COOKIE_SESSAO, sessoes.emitir(usuario.strip()), httponly=True, samesite="lax",
                            secure=request.url.scheme == "https", max_age=sessoes.duracao_s)
        return resposta

    @app.post("/sair")
    def sair():
        resposta = RedirectResponse("/login", status_code=303)
        resposta.delete_cookie(COOKIE_SESSAO)
        return resposta

    # ---------------------------------------------------------------- estado do agente
    def conversa_do_agente(cid: str) -> Conversa:
        """Recria o contexto do agente a partir do banco depois de um reinício (sem o pedido verificado)."""
        if cid not in memoria:
            c = Conversa(id=cid)
            salva = repo.conversa(cid)
            c.sessao.origem = salva.origem if salva else None
            for m in repo.mensagens(cid)[-40:]:
                if m.autor == "cliente":
                    c.historico.append({"role": "user", "content": m.texto})
                    c.turnos += 1
                elif m.autor in ("lia", "vendedor"):
                    prefixo = f"[{ROTULO_VENDEDOR}] " if m.autor == "vendedor" else ""
                    c.historico.append({"role": "assistant", "content": prefixo + m.texto})
            memoria[cid] = c
        return memoria[cid]

    def receber_do_cliente(telefone: str, texto: str) -> str:
        conv = repo.conversa_do_telefone(telefone)
        with trava:
            agente_conv = conversa_do_agente(conv.id)
            repo.adicionar(conv.id, "cliente", texto)
            if conv.status == "vendedor":
                # Um vendedor assumiu: a Lia não responde, mas guarda o contexto para quando voltar
                agente_conv.historico.append({"role": "user", "content": repo.mensagens(conv.id)[-1].texto})
                agente_conv.turnos += 1
                return conv.id
            resp = agente.responder(agente_conv, texto)
        if resp.origem:
            repo.atualizar(conv.id, origem=resp.origem)
        for a in resp.alertas:
            repo.adicionar(conv.id, "alerta", a.aviso(), {"id": a.id, "tipo": a.tipo, "motivo": a.motivo,
                                                          "protocolo": a.protocolo, "tocar": a.tocar,
                                                          "origem": a.origem, "trecho": a.trecho})
            if a.tipo == "pedido_vendedor" or "atendimento humano" in a.motivo:
                repo.atualizar(conv.id, aguardando_vendedor=1)
        corpo, aviso = resp.texto, False
        if corpo.endswith(AVISO_PRIVACIDADE):
            corpo, aviso = corpo[: -len(AVISO_PRIVACIDADE)].rstrip(), True
        repo.adicionar(conv.id, "lia", corpo, {
            "aviso": aviso, "segura": resp.segura, "origem": rotulo_origem(resp.origem),
            "rastro": [{"tool": e.tool, "args": e.argumentos, "resultado": e.resultado, "ms": e.duracao_ms,
                        "erro": e.erro} for e in resp.rastro],
            "metricas": f"{resp.latencia_s:.1f} s · {resp.tokens_entrada}+{resp.tokens_saida} tokens · "
                        f"US$ {resp.custo_usd:.5f}"})
        return conv.id

    def sessao_do_agente(cid: str) -> dict:
        c = memoria.get(cid)
        return {"pedido": c.sessao.pedido_verificado if c else None, "protocolos": c.sessao.registros if c else []}

    def alertas() -> list[dict]:
        """Os alertas vêm do histórico (mesmo relógio das mensagens); a fila em arquivo segue para o vigia."""
        return [{**m.detalhes, "conversa": cid, "hora": m.hora, "id": m.detalhes.get("id") or m.id, "texto": m.texto,
                 "origem_rotulo": rotulo_origem(m.detalhes.get("origem"))} for cid, m in repo.alertas_recentes()]

    # ---------------------------------------------------------------- painel de atendimento (loja)
    @app.get("/")
    def inicio():
        return RedirectResponse("/atendimento", status_code=303)

    @app.get("/atendimento", response_class=HTMLResponse)
    def atendimento(request: Request):
        return pagina(request, "atendimento.html", ativo="atendimento", conversas=repo.listar(), alertas=alertas())

    @app.get("/atendimento/lista", response_class=HTMLResponse)
    def atendimento_lista(request: Request):
        return pagina(request, "_lista.html", conversas=repo.listar())

    @app.get("/atendimento/alertas", response_class=HTMLResponse)
    def atendimento_alertas(request: Request):
        return pagina(request, "_alertas.html", alertas=alertas())

    def conversa_ou_404(cid: str):
        conv = repo.conversa(cid)
        if conv is None:
            raise HTTPException(404, "conversa não encontrada")
        return conv

    @app.get("/atendimento/{cid}", response_class=HTMLResponse)
    def conversa(request: Request, cid: str):
        conv = conversa_ou_404(cid)
        return pagina(request, "conversa.html", ativo="atendimento", conv=conv, mensagens=repo.mensagens(cid),
                      lado="loja", **sessao_do_agente(cid))

    @app.get("/atendimento/{cid}/thread", response_class=HTMLResponse)
    def conversa_thread(request: Request, cid: str):
        conv = conversa_ou_404(cid)
        return pagina(request, "_thread.html", conv=conv, mensagens=repo.mensagens(cid), lado="loja",
                      url_thread=f"/atendimento/{cid}/thread")

    @app.post("/atendimento/{cid}/assumir")
    def assumir(request: Request, cid: str):
        conv = conversa_ou_404(cid)
        if conv.status != "vendedor":
            repo.atualizar(cid, status="vendedor", aguardando_vendedor=0)
            repo.adicionar(cid, "sistema", "Um vendedor assumiu a conversa. A Lia está pausada.",
                           {"por": request.state.usuario})
        return RedirectResponse(f"/atendimento/{cid}", status_code=303)

    @app.post("/atendimento/{cid}/devolver")
    def devolver(request: Request, cid: str):
        conv = conversa_ou_404(cid)
        if conv.status != "lia":
            repo.atualizar(cid, status="lia", aguardando_vendedor=0)
            repo.adicionar(cid, "sistema", "A Lia voltou ao atendimento.", {"por": request.state.usuario})
        return RedirectResponse(f"/atendimento/{cid}", status_code=303)

    @app.post("/atendimento/{cid}/responder")
    def responder(request: Request, cid: str, texto: str = Form("")):
        conv = conversa_ou_404(cid)
        texto = texto.strip()[:LIMITE_TEXTO]
        if conv.status != "vendedor":
            raise HTTPException(409, "assuma a conversa antes de responder")
        if texto:
            salva = repo.adicionar(cid, "vendedor", texto, {"por": request.state.usuario})
            with trava:
                conversa_do_agente(cid).historico.append({"role": "assistant",
                                                          "content": f"[{ROTULO_VENDEDOR}] {salva.texto}"})
        return RedirectResponse(f"/atendimento/{cid}", status_code=303)

    # ---------------------------------------------------------------- simulador de WhatsApp (cliente)
    def telefone_atual(request: Request) -> str:
        return request.cookies.get(COOKIE_TELEFONE) or TELEFONE_PADRAO

    def ctx_simulador(request: Request, telefone: str) -> dict:
        conv = repo.conversa_do_telefone(telefone, criar=False)       # só nasce na primeira mensagem
        msgs = repo.mensagens(conv.id) if conv else []
        return {"ativo": "simulador", "telefone": telefone, "conv": conv, "mensagens": msgs, "lado": "cliente",
                "perguntas": PERGUNTAS, "origens": origem_lead.ORIGENS, "mensagem_canal": origem_lead.MENSAGEM_PADRAO,
                "inicio": not any(m.autor == "cliente" for m in msgs), "url_thread": "/simulador/thread",
                "data_referencia": config.data_referencia, **sessao_do_agente(conv.id if conv else "")}

    def com_telefone(resposta, telefone: str):
        resposta.set_cookie(COOKIE_TELEFONE, telefone, httponly=True, samesite="lax")
        return resposta

    @app.get("/simulador", response_class=HTMLResponse)
    def simulador(request: Request, telefone: str | None = None):
        tel = (telefone or telefone_atual(request)).strip()
        try:
            ctx = ctx_simulador(request, tel)
        except ValueError as e:
            ctx = ctx_simulador(request, telefone_atual(request)) | {"erro": str(e)}
            tel = ctx["telefone"]
        return com_telefone(pagina(request, "simulador.html", **ctx), tel)

    @app.get("/simulador/thread", response_class=HTMLResponse)
    def simulador_thread(request: Request):
        return pagina(request, "_thread.html", **ctx_simulador(request, telefone_atual(request)))

    @app.post("/simulador/mensagem", response_class=HTMLResponse)
    def simulador_mensagem(request: Request, texto: str = Form("")):
        tel = telefone_atual(request)
        texto = " ".join(texto.split())[:LIMITE_TEXTO]
        if texto:
            receber_do_cliente(tel, texto)
        if request.headers.get("HX-Request"):
            return com_telefone(pagina(request, "_simulador.html", **ctx_simulador(request, tel)), tel)
        return com_telefone(RedirectResponse("/simulador", status_code=303), tel)

    @app.post("/simulador/apagar")
    def simulador_apagar(request: Request):
        conv = repo.conversa_do_telefone(telefone_atual(request), criar=False)
        if conv:
            repo.apagar(conv.id)
            memoria.pop(conv.id, None)
        return RedirectResponse("/simulador", status_code=303)

    return app
