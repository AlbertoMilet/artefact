"""Provedor simulado da Meta (SPEC-004): demonstração e testes sem app da Meta e sem SMS de verdade.

O "SMS" é o código guardado em `ultimo_codigo`, que o CLI mostra no modo simulado.
"""

from __future__ import annotations

import secrets

from emporio.whatsapp.meta import ErroMeta, Numero, Token
from emporio.whatsapp.regras import ESCOPOS


class ProvedorSimulado:
    APP_ID = "app-simulado"

    def __init__(self, numeros: list[Numero] | None = None, codigo_fixo: str | None = None):
        self.numeros: dict[str, Numero] = {n.id: n for n in (numeros or [
            Numero("1001", "+55 67 3341-4444", "Empório da Música", "NOT_VERIFIED", "PENDING")])}
        self.codigo_fixo = codigo_fixo
        self.app_id = self.APP_ID
        self.ultimo_codigo: str | None = None
        self.verificados: set[str] = set()
        self.registrados: dict[str, str] = {}
        self.webhooks: set[str] = set()
        self.chamadas: list[str] = []

    def url_login(self, state: str) -> str:
        return f"https://www.facebook.com/simulado/dialog/oauth?state={state}"

    def trocar_codigo(self, code: str) -> Token:
        self.chamadas.append("trocar_codigo")
        if code != "codigo-oauth-simulado":
            raise ErroMeta("código de autorização inválido", 100)
        return Token("token-curto-simulado", 3600)

    def longa_duracao(self, token: Token) -> Token:
        return Token("token-longo-simulado-" + secrets.token_hex(4), 60 * 24 * 3600)

    def validar(self, token: Token) -> dict:
        return {"valido": token.valor.startswith("token-"), "app_id": self.APP_ID, "escopos": list(ESCOPOS),
                "wabas": ["2001"]}

    def listar_numeros(self, token: Token, waba_id: str) -> list[Numero]:
        return list(self.numeros.values())

    def cadastrar_numero(self, token: Token, waba_id: str, cc: str, numero: str, nome: str) -> str:
        novo = str(1001 + len(self.numeros))
        self.numeros[novo] = Numero(novo, f"+{cc} {numero}", nome, "NOT_VERIFIED", "PENDING")
        return novo

    def pedir_codigo(self, token: Token, phone_id: str, metodo: str = "SMS", idioma: str = "pt_BR") -> None:
        self.chamadas.append(f"pedir_codigo:{metodo}")
        self.ultimo_codigo = self.codigo_fixo or f"{secrets.randbelow(10 ** 6):06d}"

    def confirmar_codigo(self, token: Token, phone_id: str, codigo: str) -> None:
        if codigo != self.ultimo_codigo:
            raise ErroMeta("código de verificação incorreto", 136025)
        self.verificados.add(phone_id)

    def registrar(self, token: Token, phone_id: str, pin: str) -> None:
        if phone_id not in self.verificados:
            raise ErroMeta("número ainda não verificado", 133010)
        self.registrados[phone_id] = pin

    def assinar_webhooks(self, token: Token, waba_id: str) -> None:
        self.webhooks.add(waba_id)
