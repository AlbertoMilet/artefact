"""Configurações no painel (SPEC-009): modelo, persona, WhatsApp, origem dos leads e retenção.

As escolhas vão para `.emporio.json` (o mesmo arquivo do `python -m emporio configurar`) e valem na hora:
o painel monta outro agente com a nova configuração. Segredos (chave do OpenRouter, segredo do app da
Meta, chave de cifra) ficam só no .env e nunca aparecem na tela; o PIN do WhatsApp nunca é guardado.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from emporio import modelos, preferencias
from emporio.agent.persona import TONS, TRATAMENTOS, Persona
from emporio.agent.prompt import montar_prompt
from emporio.llm import LLMIndisponivel
from emporio.rules import origem as origem_lead
from emporio.tools.toolbox import LOJA
from emporio.whatsapp import conexao as arq_whatsapp
from emporio.whatsapp import regras as regras_whatsapp
from emporio.whatsapp.conexao import ConexaoCorrompida, Etapa
from emporio.whatsapp.fluxo import EtapaInvalida, Onboarding, PrecisaLogin
from emporio.whatsapp.meta import ErroMeta, GraphMeta
from emporio.whatsapp.simulado import ProvedorSimulado

COOKIE_STATE = "emporio_oauth_state"
ETAPAS = [(Etapa.NAO_CONECTADO, "Login com Facebook"), (Etapa.AUTENTICADO, "Número"),
          (Etapa.NUMERO_ESCOLHIDO, "Código por SMS"), (Etapa.CODIGO_ENVIADO, "Confirmar código"),
          (Etapa.VERIFICADO, "Registro com PIN"), (Etapa.REGISTRADO, "Assinar o app"),
          (Etapa.ASSINADO, "Concluído")]
ERROS_WHATSAPP = (ErroMeta, EtapaInvalida, ValueError, ConexaoCorrompida)


def registrar_configuracoes(app: FastAPI, pagina, estado: dict, repo, trocar_agente) -> None:
    onboardings: dict[str, Onboarding] = {}       # um por modo; o token fica em memória enquanto o servidor roda

    def aplicar(prefs: dict) -> str | None:
        """Monta o agente com as preferências; só grava o arquivo se deu certo. Devolve o erro, se houver."""
        try:
            nova = estado["config"].com_preferencias(preferencias.validar(prefs))
            trocar_agente(nova)
        except (ValueError, LLMIndisponivel) as e:
            return str(e)
        preferencias.salvar(prefs)
        return None

    @app.get("/configuracoes")
    def configuracoes():
        return RedirectResponse("/configuracoes/modelo", status_code=303)

    # ---------------------------------------------------------------- modelo e comportamento
    def ctx_modelo(**extra) -> dict:
        c = estado["config"]
        ref = c.data_referencia.strftime("%Y-%m-%dT%H:%M") if c.data_referencia else ""
        return {"ativo": "configuracoes", "aba": "modelo", "opcoes": modelos.OPCOES, "atual": c.openrouter_model,
                "outro": "" if modelos.por_slug(c.openrouter_model) else c.openrouter_model,
                "raciocinio": c.raciocinio, "data_referencia": ref, "chave": bool(c.openrouter_api_key),
                "provedor": c.llm_provider, **extra}

    @app.get("/configuracoes/modelo", response_class=HTMLResponse)
    def modelo(request: Request):
        return pagina(request, "config_modelo.html", **ctx_modelo())

    @app.post("/configuracoes/modelo", response_class=HTMLResponse)
    def salvar_modelo(request: Request, modelo: str = Form("deepseek"), outro: str = Form(""),
                      raciocinio: str = Form(""), data_referencia: str = Form("")):
        prefs = preferencias.carregar()
        prefs["modelo"] = outro.strip() if modelo == "outro" else modelo
        prefs["raciocinio"] = raciocinio == "on"
        if data_referencia.strip():
            prefs["data_referencia"] = data_referencia.strip()
        else:
            prefs.pop("data_referencia", None)
        erro = aplicar(prefs)
        return pagina(request, "config_modelo.html", **ctx_modelo(erro=erro, ok=None if erro else "Configuração salva e aplicada."))

    # ---------------------------------------------------------------- persona
    def ctx_persona(persona: Persona | None = None, **extra) -> dict:
        p = persona or estado["config"].persona
        agora = estado["agente"].toolbox.relogio()                     # o mesmo relógio do agente
        amostra = montar_prompt(agora, p).split("# Regras invioláveis")[0].strip()
        return {"ativo": "configuracoes", "aba": "persona", "p": p, "tons": TONS, "tratamentos": TRATAMENTOS,
                "amostra": amostra, **extra}

    @app.get("/configuracoes/persona", response_class=HTMLResponse)
    def persona(request: Request):
        return pagina(request, "config_persona.html", **ctx_persona())

    @app.post("/configuracoes/persona", response_class=HTMLResponse)
    def salvar_persona(request: Request, nome: str = Form("Lia"), tratamento: str = Form("feminino"),
                       tom: str = Form("amigavel"), emojis: str = Form(""), instrucoes: str = Form(""),
                       acao: str = Form("salvar")):
        dados = {"nome": nome, "tratamento": tratamento, "tom": tom, "emojis": emojis == "on", "instrucoes": instrucoes}
        if acao == "padrao":
            dados = Persona().como_dict()
        try:
            p = Persona.de_dict(dados)
        except ValueError as e:
            return pagina(request, "config_persona.html", **ctx_persona(erro=str(e)))
        prefs = preferencias.carregar()
        prefs["persona"] = p.como_dict()
        erro = aplicar(prefs)
        return pagina(request, "config_persona.html",
                      **ctx_persona(p, erro=erro, ok=None if erro else "Persona salva. Vale a partir da próxima mensagem."))

    # ---------------------------------------------------------------- WhatsApp (SPEC-004 no painel)
    def modo_real_disponivel() -> bool:
        return bool(os.getenv("META_APP_ID", "").strip() and os.getenv("META_APP_SECRET", "").strip())

    def onboarding(modo: str) -> Onboarding:
        if modo not in onboardings:
            if modo == "real":
                redirect = os.getenv("META_REDIRECT_URI", "").strip()
                regras_whatsapp.validar_redirect(redirect)
                provedor = GraphMeta(os.getenv("META_APP_ID", "").strip(), os.getenv("META_APP_SECRET", "").strip(),
                                     redirect, os.getenv("META_GRAPH_VERSION", "v25.0").strip())
            else:
                provedor = ProvedorSimulado(codigo_fixo="123456", estrito=False)
            onboardings[modo] = Onboarding(provedor, simulado=modo != "real")
        return onboardings[modo]

    def ctx_whatsapp(request: Request, modo: str, **extra) -> dict:
        ctx = {"ativo": "configuracoes", "aba": "whatsapp", "modo": modo, "real_disponivel": modo_real_disponivel(),
               "redirect_sugerido": f"http://localhost:{request.url.port or 80}/configuracoes/whatsapp/callback",
               "etapas": ETAPAS, **extra}
        try:
            ob = onboarding(modo)
        except ERROS_WHATSAPP as e:
            return ctx | {"erro": extra.get("erro") or str(e), "ob": None}
        numeros = []
        if ob.c.etapa == Etapa.AUTENTICADO and not ob.precisa_login():
            try:
                numeros = ob.numeros()
            except ERROS_WHATSAPP as e:
                ctx["erro"] = ctx.get("erro") or str(e)
        ordem = [e for e, _ in ETAPAS]
        return ctx | {"ob": ob, "c": ob.c, "numeros": numeros, "proxima": ob.proxima_acao(),
                      "indice": ordem.index(ob.c.etapa), "precisa_login": ob.precisa_login(),
                      "codigo_simulado": getattr(ob.p, "ultimo_codigo", None) if modo != "real" else None,
                      "historico": ob.c.historico[-8:]}

    def modo_de(request: Request) -> str:
        return "real" if request.query_params.get("modo") == "real" and modo_real_disponivel() else "simulado"

    @app.get("/configuracoes/whatsapp", response_class=HTMLResponse)
    def whatsapp(request: Request):
        return pagina(request, "config_whatsapp.html", **ctx_whatsapp(request, modo_de(request)))

    @app.post("/configuracoes/whatsapp/{acao}", response_class=HTMLResponse)
    def whatsapp_acao(request: Request, acao: str, modo: str = Form("simulado"), numero_id: str = Form(""),
                      numero: str = Form(""), nome: str = Form(""), metodo: str = Form("SMS"),
                      codigo: str = Form(""), pin: str = Form("")):
        modo = "real" if modo == "real" and modo_real_disponivel() else "simulado"
        ok = erro = None
        try:
            if acao == "desconectar":
                arq_whatsapp.apagar(modo != "real")
                onboardings.pop(modo, None)
                ok = "Conexão apagada."
            else:
                ob = onboarding(modo)
                if acao == "login":
                    state = regras_whatsapp.novo_state()
                    if modo == "real":
                        resposta = RedirectResponse(ob.p.url_login(state), status_code=303)
                        resposta.set_cookie(COOKIE_STATE, state, httponly=True, samesite="lax", max_age=600,
                                            secure=request.url.scheme == "https")
                        return resposta
                    ob.autenticar("codigo-oauth-simulado", state, state, escolher_waba=lambda ws: ws[0])
                    ok = "Login com Facebook concluído (simulado)."
                elif acao == "numero":
                    if numero.strip():
                        ob.cadastrar_numero(numero, nome)
                    else:
                        escolhido = next((n for n in ob.numeros() if n.id == numero_id), None)
                        if escolhido is None:
                            raise ValueError("escolha um número da lista ou cadastre um novo")
                        ob.escolher_numero(escolhido)
                    ok = "Número definido."
                elif acao == "enviar-codigo":
                    ob.pedir_codigo(metodo)
                    ok = f"Código enviado por {'SMS' if metodo.upper() == 'SMS' else 'ligação'} para {ob.c.numero_exibicao}."
                elif acao == "confirmar-codigo":
                    ob.confirmar_codigo(codigo)
                    ok = "Número confirmado."
                elif acao == "registrar":
                    ob.registrar(pin)                    # o PIN só passa para a Meta; não é guardado
                    ok = "Número registrado na Cloud API."
                elif acao == "assinar":
                    ob.assinar_webhooks()
                    ok = "App assinado na conta do WhatsApp Business."
                else:
                    raise ValueError("ação desconhecida")
        except PrecisaLogin as e:
            erro = f"{e} Faça o login com Facebook de novo."
        except ERROS_WHATSAPP as e:
            erro = str(e)
        return pagina(request, "config_whatsapp.html", **ctx_whatsapp(request, modo, ok=ok, erro=erro))

    @app.get("/configuracoes/whatsapp/callback", response_class=HTMLResponse)
    def whatsapp_callback(request: Request, code: str = "", state: str = "", error_description: str = ""):
        erro = ok = None
        try:
            if error_description or not code:
                raise EtapaInvalida(f"login não concluído: {error_description or 'sem código de autorização'}")
            ob = onboarding("real")
            ob.autenticar(code, state, request.cookies.get(COOKIE_STATE, ""), escolher_waba=lambda ws: ws[0],
                          waba_reserva=os.getenv("META_WABA_ID", "").strip() or None)
            ok = "Login com Facebook concluído."
        except ERROS_WHATSAPP as e:
            erro = str(e)
        resposta = pagina(request, "config_whatsapp.html", **ctx_whatsapp(request, "real", ok=ok, erro=erro))
        resposta.delete_cookie(COOKIE_STATE)
        return resposta

    # ---------------------------------------------------------------- origem dos leads (SPEC-005)
    @app.get("/configuracoes/origem", response_class=HTMLResponse)
    def origem(request: Request, numero: str = LOJA["telefone_whatsapp"], mensagem: str = origem_lead.MENSAGEM_PADRAO):
        erro = None
        try:
            links = [(o, origem_lead.link_whatsapp(numero, o, mensagem)) for o in origem_lead.ORIGENS]
        except ValueError as e:
            erro, links = str(e), []
        conversas = repo.listar(limite=10_000)
        contagem = origem_lead.resumir([c.origem for c in conversas])
        total = len(conversas)
        linhas = [(origem_lead.POR_CHAVE.get(k), n, (n / total if total else 0)) for k, n in contagem.items()]
        return pagina(request, "config_origem.html", ativo="configuracoes", aba="origem", links=links, numero=numero,
                      mensagem=mensagem, erro=erro, linhas=linhas, total=total)

    # ---------------------------------------------------------------- retenção (SPEC-002)
    @app.get("/configuracoes/retencao", response_class=HTMLResponse)
    def retencao(request: Request):
        return pagina(request, "config_retencao.html", ativo="configuracoes", aba="retencao", r=estado["config"].retencao)

