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
_RE_TELEFONE = re.compile(r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}")


def mascarar_texto(texto: str) -> str:
    """Mascara e-mails e telefones em texto livre (logs e --debug)."""
    texto = _RE_EMAIL.sub(lambda m: mascarar_email(m.group()), texto)
    return _RE_TELEFONE.sub(lambda m: mascarar_telefone(m.group()), texto)
