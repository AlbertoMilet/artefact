"""Parcelamento no cartão pela §3.1 (RN-06, D-08, D-09).

A tabela da §3 diz "parcela mínima de R$ 100,00"; a §3.1 detalha por faixa. Vale a §3.1 (A3):
- até 3x: parcela não pode ficar abaixo de R$ 50,00;
- de 4x a 6x: parcela mínima de R$ 80,00;
- de 7x a 12x: parcela mínima de R$ 100,00.
1x (à vista no crédito) é sempre permitido. O valor da parcela é truncado em centavos e a diferença
vai na primeira parcela.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from emporio.rules.dinheiro import arredondar, truncar

MAX_PARCELAS = 12


def parcela_minima(n: int) -> Decimal:
    if not 1 <= n <= MAX_PARCELAS:
        raise ValueError(f"número de parcelas fora de 1..{MAX_PARCELAS}: {n}")
    if n <= 3:
        return Decimal("50")
    if n <= 6:
        return Decimal("80")
    return Decimal("100")


def parcela_permitida(valor: Decimal, n: int) -> bool:
    if n == 1:
        return True
    return valor / n >= parcela_minima(n)


@dataclass(frozen=True)
class Parcelamento:
    parcelas: int
    valor_parcela: Decimal       # parcelas 2..n
    primeira_parcela: Decimal    # recebe a diferença de centavos
    total: Decimal


def parcelar(valor: Decimal, n: int) -> Parcelamento:
    if not parcela_permitida(valor, n):
        raise ValueError(f"{n}x não permitido para {valor} (parcela mínima {parcela_minima(n)})")
    total = arredondar(valor)
    base = truncar(total / n)
    return Parcelamento(parcelas=n, valor_parcela=base, primeira_parcela=total - base * (n - 1), total=total)


def parcelamento_maximo(valor: Decimal) -> Parcelamento:
    """Maior número de parcelas permitido para o valor (CA-19)."""
    n = max(k for k in range(1, MAX_PARCELAS + 1) if parcela_permitida(valor, k))
    return parcelar(valor, n)
