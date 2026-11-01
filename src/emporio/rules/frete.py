"""Frete (RN-07; §5.1 e §5.2).

O manual não lista os municípios da "região metropolitana de Campo Grande" (A14). Suposição
documentada: só Campo Grande conta como região metropolitana.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from emporio.data.normalize import normalizar

LIMITE_FRETE_GRATIS = Decimal("500.00")
TAXA_METROPOLITANA = Decimal("35.00")
MUNICIPIOS_METROPOLITANOS = {"campo grande"}

MODALIDADES_OUTRAS_CIDADES = [
    {"modalidade": "PAC (Correios)", "prazo": "5 a 12 dias úteis"},
    {"modalidade": "SEDEX (Correios)", "prazo": "2 a 5 dias úteis"},
    {"modalidade": "Jadlog (.package)", "prazo": "3 a 8 dias úteis"},
]


@dataclass(frozen=True)
class Frete:
    tipo: Literal["metropolitano", "outras_cidades"]
    valor: Decimal | None                # None: calculado por CEP, peso e dimensões (§5.2)
    prazo: str
    modalidades: list[dict] = field(default_factory=list)
    observacao: str = ""


def frete_metropolitano(valor_pedido: Decimal) -> Decimal:
    """Grátis só ACIMA de R$ 500,00; R$ 500,00 exatos pagam a taxa (A14)."""
    return Decimal("0.00") if valor_pedido > LIMITE_FRETE_GRATIS else TAXA_METROPOLITANA


def frete(cidade: str, valor_pedido: Decimal) -> Frete:
    if normalizar(cidade) in MUNICIPIOS_METROPOLITANOS:
        return Frete(tipo="metropolitano", valor=frete_metropolitano(valor_pedido), prazo="1 a 3 dias úteis",
                     observacao="Entrega por motoboy próprio; a loja liga antes de entregar.")
    return Frete(tipo="outras_cidades", valor=None, prazo="conforme a modalidade",
                 modalidades=MODALIDADES_OUTRAS_CIDADES,
                 observacao="Valor calculado pelo CEP, peso e dimensões; instrumentos grandes podem exigir "
                            "cotação especial. Todos os envios têm rastreamento e seguro.")
