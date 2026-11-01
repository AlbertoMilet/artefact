"""Preço final, PIX e promoção (RN-02, RN-03, RN-05; §3 e §6.2)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from emporio.data.models import Produto, Promocao
from emporio.rules.dinheiro import arredondar

DESCONTO_PIX = Decimal("0.05")


@dataclass(frozen=True)
class Preco:
    tabela: Decimal
    final: Decimal                 # preço no cartão/débito/boleto: promocional ou de tabela
    pix: Decimal | None            # None quando há promoção: o PIX não se acumula (§6.2)
    promocao: Promocao | None

    @property
    def melhor_a_vista(self) -> Decimal:
        """Menor preço à vista válido (RN-05): promocional ou PIX."""
        return min(self.final, self.pix) if self.pix is not None else self.final


def promocao_vigente(promocoes_ativas: list[Promocao]) -> Promocao | None:
    """Com mais de uma ativa, vale a de maior percentual (RN-03); empate: menor id."""
    ativas = [p for p in promocoes_ativas if p.is_active]
    if not ativas:
        return None
    return max(ativas, key=lambda p: (p.discount_percent, -p.promotion_id))


def preco_final(produto: Produto, promocoes_ativas: list[Promocao]) -> Preco:
    tabela = arredondar(produto.price_brl)
    promo = promocao_vigente([p for p in promocoes_ativas if p.product_id == produto.product_id])
    if promo:
        final = arredondar(tabela * (1 - promo.discount_percent / 100))
        return Preco(tabela=tabela, final=final, pix=None, promocao=promo)
    return Preco(tabela=tabela, final=tabela, pix=arredondar(tabela * (1 - DESCONTO_PIX)), promocao=None)
