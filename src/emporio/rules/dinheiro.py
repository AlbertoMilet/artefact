"""Dinheiro em Decimal, com arredondamento explícito e formatação brasileira."""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")


def arredondar(valor: Decimal) -> Decimal:
    """Para centavos, meio para cima (RN-02)."""
    return valor.quantize(CENTAVO, ROUND_HALF_UP)


def truncar(valor: Decimal) -> Decimal:
    """Para centavos, para baixo (valor de parcela, RN-06)."""
    return valor.quantize(CENTAVO, ROUND_DOWN)


def brl(valor: Decimal) -> str:
    """Decimal('2089.05') -> 'R$ 2.089,05'."""
    inteiro, centavos = f"{arredondar(valor):.2f}".split(".")
    return f"R$ {int(inteiro):,}".replace(",", ".") + f",{centavos}"
