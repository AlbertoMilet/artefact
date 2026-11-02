"""Interface web (SPEC-006 e SPEC-007), no estilo do painel do projeto ALJ: FastAPI + Jinja2 +
Bootstrap 5 + HTMX, sem build de front-end.

- `/atendimento`            painel da loja: conversas, alertas e o histórico de cada conversa; o vendedor
                            assume a conversa (a Lia pausa), responde e devolve à Lia;
- `/simulador`              simulador de WhatsApp: você é o cliente, identificado pelo telefone.

O agente é o mesmo do CLI e dos evals; a camada web só guarda o histórico (mascarado) e mostra.
"""

from __future__ import annotations

import hmac
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from emporio.agent import Agente, Conversa
from emporio.agent.prompt import AVISO_PRIVACIDADE
from emporio import privacidade
from emporio.rules import midia
from emporio.rules.limites import passou_do_limite
from emporio.rules.privacidade import INTERVALO_EXPURGO_S
from emporio.tools.toolbox import LOJA
from emporio.config import Config, montar_agente
from emporio.rules import origem as origem_lead
from emporio.web.auth import Limitador, Sessoes, carregar_usuarios, conferir_senha, hash_senha, segredo_da_sessao
from emporio.web.configuracoes import registrar_configuracoes
from emporio.web.repositorio import Repositorio, caminho_banco_demo

PASTA = Path(__file__).resolve().parent
COOKIE_SIMULADOR = "emporio_simulador"   # identificador aleatório do cliente simulado (SPEC-012)
LIMITE_NOME = 60
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
RESPOSTA_LIMITE = ("Recebi muitas mensagens em pouco tempo e preciso pausar por alguns instantes. Se for urgente, "
                   f"fale com a equipe pelo telefone/WhatsApp {LOJA['telefone_whatsapp']} ou pelo e-mail "
                   f"{LOJA['email']}.")                                        # SPEC-013 RS-05
LIMITE_CLIENTES_SIMULADOS = 500


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
              sessoes: Sessoes | None = None, cookies_seguros: bool = False) -> FastAPI:
    """`cookies_seguros`: atrás de um proxy HTTPS (SPEC-013 RS-02), os cookies saem sempre com `Secure`."""
    config = config or Config.do_ambiente()
    agente = agente or montar_agente(config)
    demo = agente.llm.modelo.startswith("demo/")
    usuarios = carregar_usuarios() if usuarios is None else usuarios
    login_demo = not usuarios and demo           # só no modo demonstração e só sem usuários no .env
    # SPEC-013 RS-01: com o login de demonstração (senha na tela), nunca o banco real de conversas
    repo = repositorio or (Repositorio(caminho_banco_demo()) if login_demo else Repositorio())
    privacidade.expurgar(repo)                     # SPEC-012 RL-01: o que passou do prazo sai ao iniciar
    ultimo_expurgo = {"t": time.monotonic()}
    if login_demo:
        usuarios = {USUARIO_DEMO: hash_senha(SENHA_DEMO)}
    sessoes = sessoes or Sessoes(segredo_da_sessao()[0])
    sessoes.hash_de = usuarios.get                 # SPEC-013 RS-04: senha trocada derruba a sessão
    sessoes.revogada = repo.sessao_revogada        # "Sair" revoga
    limitador = Limitador()
    modelo_hash = next(iter(usuarios.values()), "")
    iteracoes = int(modelo_hash.split("$")[1]) if modelo_hash.count("$") == 3 else 600_000
    hash_falso = hash_senha(secrets.token_hex(16), iteracoes=iteracoes)   # RS-07: mesmo custo sem usuário

    def cookie_seguro(request: Request) -> bool:
        return cookies_seguros or request.url.scheme == "https"
    estado = {"agente": agente, "config": config}   # trocados juntos quando a loja muda a configuração

    def preparar(novo: Agente) -> Agente:
        if novo.alertas is not None:
            novo.alertas.avisar = None            # na web o alerta vai para a conversa e para o painel
        return novo

    preparar(agente)

    def trocar_agente(nova: Config) -> None:
        """Aplica a configuração na hora: monta outro agente; as conversas em andamento continuam."""
        novo = preparar(montar_agente(nova))
        with trava:
            estado["agente"], estado["config"] = novo, nova

    memoria: dict[str, Conversa] = {}             # estado do agente por conversa (o histórico fica no banco)
    trava = threading.Lock()                       # protótipo de um processo: um turno por vez

    async def verificar_csrf(request: Request) -> None:
        """SPEC-013 RS-03: POST de outra origem é recusado; POST com sessão exige o token da sessão."""
        if request.method != "POST":
            return
        origem = request.headers.get("origin")
        if origem is not None and (origem == "null" or urlsplit(origem).netloc != request.url.netloc):
            raise HTTPException(403, "origem não permitida")
        if request.url.path == "/login":
            return
        esperado = sessoes.csrf(request.cookies.get(COOKIE_SESSAO))
        recebido = request.headers.get("x-csrf-token") or (await request.form()).get("csrf") or ""
        if not esperado or not hmac.compare_digest(str(recebido), esperado):
            raise HTTPException(403, "token CSRF ausente ou inválido; recarregue a página")

    app = FastAPI(title="Empório da Música · atendimento", docs_url=None, redoc_url=None,
                  dependencies=[Depends(verificar_csrf)])
    app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")
    tpl = Jinja2Templates(directory=PASTA / "templates")
    tpl.env.filters["formatar"] = formatar
    tpl.env.filters["origem"] = rotulo_origem
    def pagina(request: Request, arquivo: str, **ctx):
        usuario = getattr(request.state, "usuario", None)
        ag = estado["agente"]
        base = {"csrf": sessoes.csrf(request.cookies.get(COOKIE_SESSAO)) or "",
                "nonce": getattr(request.state, "nonce", ""), "modelo": ag.llm.modelo, "demo": ag.llm.modelo.startswith("demo/"),
                "assistente": (ag.persona.nome if ag.persona else "Lia"),
                "artigo": (ag.persona.artigo if ag.persona else "a")}
        return tpl.TemplateResponse(request, arquivo, {"request": request, "usuario": usuario, **base, **ctx})

    # ---------------------------------------------------------------- login (SPEC-008)
    def expurgo_periodico() -> None:
        """SPEC-012 RL-12: com o painel no ar, o expurgo roda de novo a cada hora e descarta o cache afetado."""
        if time.monotonic() - ultimo_expurgo["t"] < INTERVALO_EXPURGO_S:
            return
        ultimo_expurgo["t"] = time.monotonic()
        with trava:
            for cid in privacidade.expurgar(repo)["afetadas"]:
                memoria.pop(cid, None)

    def cabecalhos_de_seguranca(resposta, nonce: str):
        """SPEC-013: CSP com nonce (nada de fora), sem enquadramento, sem farejar tipo, sem cache de dados."""
        resposta.headers["Content-Security-Policy"] = (
            f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; object-src 'none'")
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["Referrer-Policy"] = "same-origin"
        if "cache-control" not in resposta.headers:
            resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.middleware("http")
    async def exigir_login(request: Request, chamar):
        expurgo_periodico()
        request.state.usuario = sessoes.validar(request.cookies.get(COOKIE_SESSAO))
        if request.state.usuario not in usuarios:
            request.state.usuario = None
        if request.state.usuario is None and not request.url.path.startswith(LIVRES):
            if request.headers.get("HX-Request"):
                return HTMLResponse("", status_code=401, headers={"HX-Redirect": "/login"})
            proximo = request.url.path if request.method == "GET" else "/"
            return RedirectResponse(f"/login?proximo={quote(proximo)}", status_code=303)
        return await chamar(request)

    @app.middleware("http")          # registrado por último: é o mais externo e vale para toda resposta
    async def seguranca(request: Request, chamar):
        request.state.nonce = secrets.token_urlsafe(16)
        return cabecalhos_de_seguranca(await chamar(request), request.state.nonce)

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
        chaves = (origem, f"usuario:{usuario.strip()[:64]}")      # RS-07: por endereço e por usuário
        espera = max(limitador.bloqueado(k) for k in chaves)
        if espera:
            return pagina(request, "login.html", erro=f"Muitas tentativas. Tente de novo em {espera} s.", **ctx)
        guardado = usuarios.get(usuario.strip())
        senha_ok = conferir_senha(senha, guardado or hash_falso)     # mesmo custo com ou sem usuário
        if guardado is None or not senha_ok:
            for k in chaves:
                limitador.falhou(k)
            return pagina(request, "login.html", erro="Usuário ou senha incorretos.", **ctx)
        for k in chaves:
            limitador.acertou(k)
        resposta = RedirectResponse(ctx["proximo"], status_code=303)
        resposta.set_cookie(COOKIE_SESSAO, sessoes.emitir(usuario.strip(), guardado), httponly=True, samesite="lax",
                            secure=cookie_seguro(request), max_age=sessoes.duracao_s)
        return resposta

    @app.post("/sair")
    def sair(request: Request):
        sessao = sessoes.id_e_expiracao(request.cookies.get(COOKIE_SESSAO))
        if sessao:
            repo.revogar_sessao(*sessao)                            # RS-04: o cookie não vale mais
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
            c.sessao.nome_cliente = salva.nome if salva else None
            for m in repo.mensagens(cid)[-40:]:
                if m.autor == "cliente":
                    c.historico.append({"role": "user", "content": m.texto})
                    c.turnos += 1
                elif m.autor in ("lia", "vendedor"):
                    prefixo = f"[{ROTULO_VENDEDOR}] " if m.autor == "vendedor" else ""
                    c.historico.append({"role": "assistant", "content": prefixo + m.texto})
            memoria[cid] = c
        return memoria[cid]

    def receber_do_cliente(telefone: str, texto: str, nome_perfil: str | None = None,
                           tipo_midia: str | None = None) -> str:
        """`tipo_midia` (SPEC-014): foto, audio, video ou documento; `texto` é ignorado e vira o marcador."""
        if tipo_midia is not None:
            texto = midia.marcador(tipo_midia)
        conv = repo.conversa_do_telefone(telefone)
        with trava:
            agente_conv = conversa_do_agente(conv.id)
            # SPEC-010 e SPEC-011: número e nome do perfil chegam com cada mensagem, como no webhook
            estado["agente"].identificar(agente_conv, nome_perfil, telefone)
            if agente_conv.sessao.nome_cliente != conv.nome:
                repo.atualizar(conv.id, nome=agente_conv.sessao.nome_cliente)
            anteriores = [m.criada_em for m in repo.mensagens(conv.id) if m.autor == "cliente"]
            repo.adicionar(conv.id, "cliente", texto, {"midia": tipo_midia} if tipo_midia else None)
            if conv.status != "vendedor" and passou_do_limite(anteriores, repo.relogio()):
                # SPEC-013 RS-05: acima do limite, resposta fixa sem chamar o LLM (custo e abuso)
                repo.adicionar(conv.id, "lia", RESPOSTA_LIMITE, {"limite": True})
                return conv.id
            if conv.status == "vendedor":
                # Um vendedor assumiu: a Lia não responde, mas guarda o contexto para quando voltar
                agente_conv.historico.append({"role": "user", "content": repo.mensagens(conv.id)[-1].texto})
                agente_conv.turnos += 1
                return conv.id
            if tipo_midia is not None:
                resp = estado["agente"].receber_midia(agente_conv, tipo_midia)   # SPEC-014: sem LLM
            else:
                resp = estado["agente"].responder(agente_conv, texto)     # identificado acima
        if resp.origem:
            repo.atualizar(conv.id, origem=resp.origem)
        for a in resp.alertas:
            repo.adicionar(conv.id, "alerta", a.aviso(), {"id": a.id, "tipo": a.tipo, "motivo": a.motivo,
                                                          "protocolo": a.protocolo, "tocar": a.tocar,
                                                          "origem": a.origem, "trecho": a.trecho})
            if a.tipo in ("pedido_vendedor", "midia") or "atendimento humano" in a.motivo:
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
        repo.auditar_leitura(request.state.usuario, cid)          # SPEC-012 RL-09, SPEC-013 RS-08
        return pagina(request, "conversa.html", ativo="atendimento", conv=conv, mensagens=repo.mensagens(cid),
                      lado="loja", **sessao_do_agente(cid))

    @app.get("/atendimento/{cid}/thread", response_class=HTMLResponse)
    def conversa_thread(request: Request, cid: str):
        conv = conversa_ou_404(cid)
        repo.auditar_leitura(request.state.usuario, cid)          # RS-08: deduplicado no servidor, sem cabeçalho
        return pagina(request, "_thread.html", conv=conv, mensagens=repo.mensagens(cid), lado="loja",
                      url_thread=f"/atendimento/{cid}/thread")

    @app.get("/atendimento/{cid}/exportar")
    def exportar(request: Request, cid: str):
        conversa_ou_404(cid)
        repo.auditar(request.state.usuario, "exportou", cid)       # SPEC-012 RL-06, RL-09
        return JSONResponse(repo.exportar(cid), headers={
            "Content-Disposition": f'attachment; filename="dados-conversa-{cid}.json"'})

    @app.post("/atendimento/{cid}/apagar")
    def apagar_dados(request: Request, cid: str, confirmar: str = Form("")):
        conversa_ou_404(cid)
        if confirmar != "sim":
            raise HTTPException(400, "marque a confirmação para apagar os dados")
        with trava:
            privacidade.apagar_conversa(repo, cid, request.state.usuario)   # SPEC-012 RL-05
            memoria.pop(cid, None)
        return RedirectResponse("/atendimento", status_code=303)

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
    # SPEC-012: telefone e nome do cliente simulado ficam no servidor; o navegador guarda só um identificador
    # aleatório (nada de telefone em URL ou cookie). Reiniciar o servidor volta ao cliente padrão.
    clientes_simulados: dict[str, dict[str, str]] = {}

    def cliente_atual(request: Request) -> dict[str, str]:
        return clientes_simulados.get(request.cookies.get(COOKIE_SIMULADOR, ""), {"telefone": TELEFONE_PADRAO, "nome": ""})

    def ctx_simulador(request: Request, cliente: dict[str, str] | None = None) -> dict:
        cliente = cliente or cliente_atual(request)
        conv = repo.conversa_do_telefone(cliente["telefone"], criar=False)       # só nasce na primeira mensagem
        msgs = repo.mensagens(conv.id) if conv else []
        return {"ativo": "simulador", "telefone": cliente["telefone"], "nome_perfil": cliente["nome"], "conv": conv,
                "mensagens": msgs, "lado": "cliente", "perguntas": PERGUNTAS, "origens": origem_lead.ORIGENS,
                "mensagem_canal": origem_lead.MENSAGEM_PADRAO,
                "inicio": not any(m.autor == "cliente" for m in msgs), "url_thread": "/simulador/thread",
                "data_referencia": estado["config"].data_referencia, **sessao_do_agente(conv.id if conv else "")}

    @app.get("/simulador", response_class=HTMLResponse)
    def simulador(request: Request):
        return pagina(request, "simulador.html", **ctx_simulador(request))

    @app.post("/simulador/cliente", response_class=HTMLResponse)
    def simulador_cliente(request: Request, telefone: str = Form(""), nome: str = Form("")):
        cliente = {"telefone": telefone.strip(), "nome": " ".join(nome.split())[:LIMITE_NOME]}
        try:
            ctx_simulador(request, cliente)                        # valida o telefone
        except ValueError as e:
            return pagina(request, "simulador.html", **(ctx_simulador(request) | {"erro": str(e)}))
        token = request.cookies.get(COOKIE_SIMULADOR) or secrets.token_urlsafe(16)
        clientes_simulados.pop(token, None)
        clientes_simulados[token] = cliente
        while len(clientes_simulados) > LIMITE_CLIENTES_SIMULADOS:           # SPEC-013: tamanho máximo
            clientes_simulados.pop(next(iter(clientes_simulados)))
        resposta = RedirectResponse("/simulador", status_code=303)
        resposta.set_cookie(COOKIE_SIMULADOR, token, httponly=True, samesite="lax")
        return resposta

    @app.get("/simulador/thread", response_class=HTMLResponse)
    def simulador_thread(request: Request):
        return pagina(request, "_thread.html", **ctx_simulador(request))

    @app.post("/simulador/mensagem", response_class=HTMLResponse)
    def simulador_mensagem(request: Request, texto: str = Form("")):
        cliente = cliente_atual(request)
        texto = " ".join(texto.split())[:LIMITE_TEXTO]
        if texto:
            receber_do_cliente(cliente["telefone"], texto, cliente["nome"])
        if request.headers.get("HX-Request"):
            return pagina(request, "_simulador.html", **ctx_simulador(request))
        return RedirectResponse("/simulador", status_code=303)

    @app.post("/simulador/midia", response_class=HTMLResponse)
    def simulador_midia(request: Request, tipo: str = Form("")):
        cliente = cliente_atual(request)
        try:
            midia.validar(tipo)
        except ValueError as e:
            raise HTTPException(400, str(e))
        receber_do_cliente(cliente["telefone"], "", cliente["nome"], tipo_midia=tipo)
        if request.headers.get("HX-Request"):
            return pagina(request, "_simulador.html", **ctx_simulador(request))
        return RedirectResponse("/simulador", status_code=303)

    @app.post("/simulador/apagar")
    def simulador_apagar(request: Request):
        conv = repo.conversa_do_telefone(cliente_atual(request)["telefone"], criar=False)
        if conv:
            with trava:
                privacidade.apagar_conversa(repo, conv.id, request.state.usuario)    # banco, logs e auditoria
                memoria.pop(conv.id, None)
        return RedirectResponse("/simulador", status_code=303)

    registrar_configuracoes(app, pagina, estado, repo, trocar_agente)
    return app
