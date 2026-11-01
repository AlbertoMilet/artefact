"""Direito de arrependimento e alternativas (RN-10, RN-11; §4.1–§4.3, §8).

A data de recebimento e o canal da compra NÃO existem nos dados (A15): vêm do cliente.
`estimated_delivery` nunca é usado para negar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

PRAZO_ARREPENDIMENTO = 7      # dias corridos após o recebimento, compra online (§4.1)
PRAZO_PREFERENCIA = 7         # troca por preferência (§4.3)
PRAZO_DEFEITO = 30            # dias corridos após a compra (§4.2)
GARANTIA_LEGAL = 90           # dias a partir do recebimento (§8.1)

Motivo = Literal["dentro_do_prazo", "fora_do_prazo", "compra_na_loja", "pedido_nao_entregue",
                 "faltam_dados", "data_invalida"]

CONDICOES_ARREPENDIMENTO = [
    "produto na embalagem original, sem sinais de uso, com todos os acessórios e manuais",
    "reembolso na mesma forma de pagamento em até 10 dias úteis",
    "frete de devolução por conta da loja",
]


@dataclass(frozen=True)
class Alternativa:
    tipo: str
    regra: str
    dentro_do_prazo: bool | None   # None: não dá para saber sem a data


@dataclass(frozen=True)
class ResultadoArrependimento:
    elegivel: bool | None          # None: depende de dado que o cliente não informou
    motivo: Motivo
    dias_desde_recebimento: int | None = None
    condicoes: list[str] = field(default_factory=list)
    alternativas: list[Alternativa] = field(default_factory=list)


def alternativas(hoje: date, data_recebimento: date | None, data_compra: date | None) -> list[Alternativa]:
    def dentro(base: date | None, dias: int) -> bool | None:
        return None if base is None else hoje <= base + timedelta(days=dias)

    return [
        Alternativa("troca por preferência", "até 7 dias, produto em perfeito estado e na embalagem original, "
                    "sujeito à disponibilidade do modelo desejado (§4.3)", dentro(data_recebimento, PRAZO_PREFERENCIA)),
        Alternativa("troca por defeito de fabricação", "até 30 dias corridos após a compra (§4.2)",
                    dentro(data_compra, PRAZO_DEFEITO)),
        Alternativa("garantia legal", "90 dias contra defeito de fabricação, a partir do recebimento (§8.1)",
                    dentro(data_recebimento, GARANTIA_LEGAL)),
        Alternativa("garantia do fabricante", "de 6 meses a 2 anos, conforme o certificado do produto (§8.2)", None),
    ]


def elegivel_arrependimento(status: str, data_recebimento: date | None,
                            canal: Literal["online", "loja"] | None, hoje: date,
                            data_compra: date | None = None) -> ResultadoArrependimento:
    alt = alternativas(hoje, data_recebimento, data_compra)
    if status != "delivered":
        return ResultadoArrependimento(None, "pedido_nao_entregue", alternativas=[])
    if data_recebimento is not None and data_recebimento > hoje:
        return ResultadoArrependimento(None, "data_invalida")
    if canal == "loja":
        return ResultadoArrependimento(False, "compra_na_loja", alternativas=alt)
    if data_recebimento is None or canal is None:
        return ResultadoArrependimento(None, "faltam_dados", condicoes=CONDICOES_ARREPENDIMENTO, alternativas=alt)
    dias = (hoje - data_recebimento).days
    if dias <= PRAZO_ARREPENDIMENTO:
        return ResultadoArrependimento(True, "dentro_do_prazo", dias, CONDICOES_ARREPENDIMENTO)
    return ResultadoArrependimento(False, "fora_do_prazo", dias, alternativas=alt)
