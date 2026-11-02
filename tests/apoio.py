"""Auxiliares dos testes do painel."""

import re


def com_csrf(cliente, pagina: str = "/atendimento"):
    """Depois do login, lê o token CSRF da página (como o navegador) e o manda em todo pedido (SPEC-013)."""
    m = re.search(r'<meta name="csrf-token" content="([^"]*)">', cliente.get(pagina).text)
    assert m and m.group(1), "token CSRF não encontrado na página"
    cliente.headers["X-CSRF-Token"] = m.group(1)
    return cliente
