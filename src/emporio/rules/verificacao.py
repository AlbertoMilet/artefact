"""Verificação do dono do pedido e máscara de dados pessoais (RN-08, RN-09, RN-24; §9).

A verificação confere o cadastro; não prova que quem conversa é o dono (simulação, README).
"""

from __future__ import annotations

import re

from emporio.data.models import Cliente


def _digitos(texto: str) -> str:
    d = re.sub(r"\D", "", texto)
    if d.startswith("55") and len(d) in (12, 13):   # +55 DDD número
        d = d[2:]
    return d


def verificar_dono(cliente: Cliente, informado: str) -> bool:
    """Telefone (com ou sem DDD, com ou sem +55) ou e-mail que confere com o cadastro."""
    informado = (informado or "").strip()
    if not informado:
        return False
    if "@" in informado:
        return informado.casefold() == cliente.email.strip().casefold()
    dig, cad = _digitos(informado), _digitos(cliente.phone)
    if len(dig) < 8:
        return False
    return dig == cad or (len(dig) in (8, 9) and cad.endswith(dig))


def mascarar_telefone(telefone: str) -> str:
    """'(67) 99654-7821' -> '(67) 9****-7821'."""
    d = _digitos(telefone)
    if len(d) < 8:
        return "<telefone>"
    ddd, numero = (d[:2], d[2:]) if len(d) >= 10 else ("", d)
    mascarado = numero[0] + "*" * (len(numero) - 5) + "-" + numero[-4:]
    return f"({ddd}) {mascarado}" if ddd else mascarado


def mascarar_email(email: str) -> str:
    """'anacarol.ferreira@coldmail.com' -> 'a***@coldmail.com'."""
    if "@" not in email:
        return "<e-mail>"
    usuario, dominio = email.split("@", 1)
    return f"{usuario[:1]}***@{dominio}"


_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
# Telefone com DDD (com ou sem +55, parênteses e separadores) ou só o número local (8 ou 9 dígitos,
# formatos aceitos por verificar_dono). Os limites (?<![\w-]) e (?![\w-]) impedem casar dentro de
# identificadores como o protocolo "SIM-20260325-0001" ou o rastreio "BRJL5544332BR".
_RE_TELEFONE = re.compile(
    r"(?<![\w-])(?:"
    r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}"     # com DDD
    r"|9?\d{4}[-\s]\d{4}"                               # local com separador
    r"|9\d{8}"                                          # celular local sem separador
    r")(?![\w-])")


# Contatos públicos da loja: não são dado pessoal e não são mascarados (só os exatos)
CONTATOS_PUBLICOS_DIGITOS = {"6733414444", "6733214500"}
EMAILS_PUBLICOS = {"contato@emporiodamusica.com.br", "contato@empóriodamusica.com.br"}


def mascarar_texto(texto: str) -> str:
    """Mascara e-mails e telefones de clientes em texto livre (logs, --debug, histórico, exportações)."""
    def email(m):
        e = m.group()
        return e if e.lower() in EMAILS_PUBLICOS else mascarar_email(e)

    def tel(m):
        return m.group() if _digitos(m.group()) in CONTATOS_PUBLICOS_DIGITOS else mascarar_telefone(m.group())

    return _RE_TELEFONE.sub(tel, _RE_EMAIL.sub(email, texto))
