"""Cliente real da Graph API da Meta para conectar o número (SPEC-004 CW-07). Sem dependência extra (urllib).

Endpoints (Graph API v25.0, a versão do cliente do BaixaAI):
- login:            https://www.facebook.com/v25.0/dialog/oauth
- código -> token:  GET  /oauth/access_token (code)            e longa duração (grant_type=fb_exchange_token)
- validar token:    GET  /debug_token (input_token, access_token=APP_ID|APP_SECRET)
- números da WABA:  GET  /{waba_id}/phone_numbers (paginado)    cadastrar: POST /{waba_id}/phone_numbers
- código por SMS:   POST /{phone_number_id}/request_code        confirmar: POST /{phone_number_id}/verify_code
- registrar:        POST /{phone_number_id}/register            assinar:   POST /{waba_id}/subscribed_apps

Ressalvas (revisão do Codex): o token de usuário de longa duração expira (cerca de 60 dias); para produção a Meta
recomenda token de usuário do sistema. A descoberta da WABA pelas `granular_scopes` nem sempre está disponível:
há a alternativa META_WABA_ID. `subscribed_apps` direciona os eventos ao webhook configurado no app; não cria o
receptor.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from emporio.whatsapp.regras import ESCOPOS

GRAPH = "https://graph.facebook.com"
DIALOGO = "https://www.facebook.com"
CODIGOS_AUTENTICACAO = {102, 190}          # sessão inválida ou token expirado/revogado
_RE_SEGREDO = re.compile(r"(EAA[A-Za-z0-9]{10,}|access_token=[^&\s]+|\b\d{6}\b)")
PAGINAS_MAX = 20


def limpar_mensagem(texto: str) -> str:
    """Mensagem de erro da Meta sem token, sem código de 6 dígitos e curta (não ecoa segredo)."""
    return _RE_SEGREDO.sub("<omitido>", " ".join(str(texto).split()))[:200]


class ErroMeta(RuntimeError):
    def __init__(self, mensagem: str, codigo: int | None = None):
        mensagem = limpar_mensagem(mensagem)
        super().__init__(f"{mensagem}" + (f" (código {codigo} da Meta)" if codigo is not None else ""))
        self.codigo = codigo

    @property
    def autenticacao(self) -> bool:
        return self.codigo in CODIGOS_AUTENTICACAO

    @property
    def rede(self) -> bool:
        return self.codigo is None


@dataclass(frozen=True)
class Token:
    valor: str = field(repr=False)          # nunca aparece em repr, log ou traceback
    expira_em_s: int | None = None


@dataclass(frozen=True)
class Numero:
    id: str
    exibicao: str
    nome_verificado: str
    verificacao: str = ""        # code_verification_status: VERIFIED, NOT_VERIFIED, EXPIRED
    status: str = ""             # CONNECTED quando já registrado na Cloud API


class ProvedorMeta(Protocol):
    app_id: str

    def url_login(self, state: str) -> str: ...
    def trocar_codigo(self, code: str) -> Token: ...
    def longa_duracao(self, token: Token) -> Token: ...
    def validar(self, token: Token) -> dict: ...                       # {"valido", "app_id", "escopos", "wabas"}
    def listar_numeros(self, token: Token, waba_id: str) -> list[Numero]: ...
    def cadastrar_numero(self, token: Token, waba_id: str, cc: str, numero: str, nome: str) -> str: ...
    def pedir_codigo(self, token: Token, phone_id: str, metodo: str = "SMS", idioma: str = "pt_BR") -> None: ...
    def confirmar_codigo(self, token: Token, phone_id: str, codigo: str) -> None: ...
    def registrar(self, token: Token, phone_id: str, pin: str) -> None: ...
    def assinar_webhooks(self, token: Token, waba_id: str) -> None: ...


# transporte(metodo, url, params, token) -> dict (JSON da resposta). Injetável para testes sem rede.
Transporte = Callable[[str, str, dict, str | None], dict]


def transporte_http(metodo: str, url: str, params: dict, token: str | None) -> dict:
    cabecalhos = {"Authorization": f"Bearer {token}"} if token else {}
    if metodo == "GET":
        req = Request(f"{url}?{urlencode(params)}" if params else url, headers=cabecalhos)
    else:
        req = Request(url, data=urlencode(params).encode(), headers=cabecalhos, method=metodo)
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except HTTPError as e:
        try:
            erro = json.loads(e.read().decode()).get("error", {})
        except (ValueError, AttributeError):
            erro = {}
        raise ErroMeta(erro.get("error_user_msg") or erro.get("message") or f"HTTP {e.code}", erro.get("code")) from None
    except URLError as e:
        raise ErroMeta(f"sem conexão com a Meta: {e.reason}") from None


class GraphMeta:
    def __init__(self, app_id: str, app_secret: str, redirect_uri: str, versao: str = "v25.0",
                 transporte: Transporte = transporte_http):
        if not app_id or not app_secret:
            raise ErroMeta("defina META_APP_ID e META_APP_SECRET no .env (app da Meta com o produto WhatsApp)")
        self.app_id, self.redirect_uri, self.versao = app_id, redirect_uri, versao
        self._segredo = app_secret
        self._t = transporte

    def __repr__(self) -> str:                         # sem o segredo do app
        return f"GraphMeta(app_id={self.app_id!r}, versao={self.versao!r})"

    def _url(self, caminho: str) -> str:
        return f"{GRAPH}/{self.versao}/{caminho.lstrip('/')}"

    # ---------------------------------------------------------------- login
    def url_login(self, state: str) -> str:
        return f"{DIALOGO}/{self.versao}/dialog/oauth?" + urlencode({
            "client_id": self.app_id, "redirect_uri": self.redirect_uri, "state": state,
            "response_type": "code", "scope": ",".join(ESCOPOS)})

    def trocar_codigo(self, code: str) -> Token:
        r = self._t("GET", self._url("oauth/access_token"), {"client_id": self.app_id, "client_secret": self._segredo,
                                                            "redirect_uri": self.redirect_uri, "code": code}, None)
        return Token(r["access_token"], r.get("expires_in"))

    def longa_duracao(self, token: Token) -> Token:
        r = self._t("GET", self._url("oauth/access_token"), {"grant_type": "fb_exchange_token", "client_id": self.app_id,
                                                            "client_secret": self._segredo,
                                                            "fb_exchange_token": token.valor}, None)
        return Token(r["access_token"], r.get("expires_in"))

    def validar(self, token: Token) -> dict:
        r = self._t("GET", self._url("debug_token"),
                    {"input_token": token.valor, "access_token": f"{self.app_id}|{self._segredo}"}, None)
        d = r.get("data", {})
        wabas = []
        for g in d.get("granular_scopes", []):
            if g.get("scope") == "whatsapp_business_management":
                wabas.extend(g.get("target_ids", []))
        return {"valido": bool(d.get("is_valid")), "app_id": str(d.get("app_id", "")),
                "escopos": d.get("scopes", []), "wabas": wabas}

    # ---------------------------------------------------------------- número
    def listar_numeros(self, token: Token, waba_id: str) -> list[Numero]:
        r = self._t("GET", self._url(f"{waba_id}/phone_numbers"),
                    {"fields": "id,display_phone_number,verified_name,code_verification_status,status"}, token.valor)
        dados = list(r.get("data", []))
        for _ in range(PAGINAS_MAX):                     # paginação (revisão do Codex)
            proxima = (r.get("paging") or {}).get("next")
            if not proxima:
                break
            r = self._t("GET", proxima, {}, token.valor)
            dados.extend(r.get("data", []))
        return [Numero(n["id"], n.get("display_phone_number", ""), n.get("verified_name", ""),
                       n.get("code_verification_status", ""), n.get("status", "")) for n in dados]

    def cadastrar_numero(self, token: Token, waba_id: str, cc: str, numero: str, nome: str) -> str:
        r = self._t("POST", self._url(f"{waba_id}/phone_numbers"),
                    {"cc": cc, "phone_number": numero, "verified_name": nome}, token.valor)
        return r["id"]

    def pedir_codigo(self, token: Token, phone_id: str, metodo: str = "SMS", idioma: str = "pt_BR") -> None:
        self._t("POST", self._url(f"{phone_id}/request_code"), {"code_method": metodo, "language": idioma}, token.valor)

    def confirmar_codigo(self, token: Token, phone_id: str, codigo: str) -> None:
        self._t("POST", self._url(f"{phone_id}/verify_code"), {"code": codigo}, token.valor)

    def registrar(self, token: Token, phone_id: str, pin: str) -> None:
        self._t("POST", self._url(f"{phone_id}/register"), {"messaging_product": "whatsapp", "pin": pin}, token.valor)

    def assinar_webhooks(self, token: Token, waba_id: str) -> None:
        self._t("POST", self._url(f"{waba_id}/subscribed_apps"), {}, token.valor)
