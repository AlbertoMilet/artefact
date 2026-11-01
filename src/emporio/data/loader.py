"""Carga e validação dos CSVs (SPEC-001, Q 6.1 e 6.2; CA-10).

- Arquivo obrigatório ausente: `DadosIndisponiveis` (a aplicação não inicia).
- Linha inválida (tipo errado, JSON de specs inválido, referência quebrada): descartada e registrada
  no log; o resto continua disponível.
"""

from __future__ import annotations

import csv
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from emporio.data.models import Categoria, Cliente, ItemPedido, Pedido, Produto, Promocao

log = logging.getLogger(__name__)

PREFIXO = "desafio_tecnico_ai_eng - "
ARQUIVOS = {
    "categories": Categoria,
    "customers": Cliente,
    "products": Produto,
    "promotions": Promocao,
    "orders": Pedido,
    "order_items": ItemPedido,
}

M = TypeVar("M", bound=BaseModel)


class DadosIndisponiveis(RuntimeError):
    """Arquivo obrigatório ausente ou ilegível."""


@dataclass
class Catalogo:
    categorias: dict[int, Categoria]
    clientes: dict[int, Cliente]
    produtos: dict[int, Produto]
    promocoes: list[Promocao]
    pedidos: dict[int, Pedido]
    itens: dict[int, list[ItemPedido]]
    descartes: list[str] = field(default_factory=list)

    def promocoes_ativas(self, product_id: int) -> list[Promocao]:
        return [p for p in self.promocoes if p.product_id == product_id and p.is_active]

    def categoria_nome(self, category_id: int) -> str:
        c = self.categorias.get(category_id)
        return c.name if c else ""


def _ler(caminho: Path, modelo: type[M], descartes: list[str]) -> list[M]:
    if not caminho.is_file():
        raise DadosIndisponiveis(f"Arquivo obrigatório não encontrado: {caminho}")
    try:
        with open(caminho, encoding="utf-8", newline="") as f:
            linhas = list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError) as e:
        raise DadosIndisponiveis(f"Não foi possível ler {caminho}: {e}") from e
    validos = []
    for n, linha in enumerate(linhas, start=2):  # linha 1 é o cabeçalho
        try:
            validos.append(modelo.model_validate(linha))
        except (ValidationError, ValueError) as e:
            motivo = f"{caminho.name}:{n} descartada ({type(e).__name__}: {str(e).splitlines()[0]})"
            log.warning(motivo)
            descartes.append(motivo)
    return validos


def carregar(data_dir: Path | str) -> Catalogo:
    data_dir = Path(data_dir)
    descartes: list[str] = []
    lido = {nome: _ler(data_dir / f"{PREFIXO}{nome}.csv", modelo, descartes)
            for nome, modelo in ARQUIVOS.items()}

    def unicos(itens: list, chave: str, nome: str) -> list:
        """ID repetido: mantém o primeiro e registra o descarte (não sobrescreve em silêncio)."""
        vistos, out = set(), []
        for x in itens:
            k = getattr(x, chave)
            if k in vistos:
                motivo = f"{nome} {k} duplicado: mantido o primeiro registro"
                log.warning(motivo)
                descartes.append(motivo)
                continue
            vistos.add(k)
            out.append(x)
        return out

    lido["categories"] = unicos(lido["categories"], "category_id", "categoria")
    lido["customers"] = unicos(lido["customers"], "customer_id", "cliente")
    lido["products"] = unicos(lido["products"], "product_id", "produto")
    lido["promotions"] = unicos(lido["promotions"], "promotion_id", "promoção")
    lido["orders"] = unicos(lido["orders"], "order_id", "pedido")

    categorias = {c.category_id: c for c in lido["categories"]}
    clientes = {c.customer_id: c for c in lido["customers"]}

    def ref_ok(cond: bool, motivo: str) -> bool:
        if not cond:
            log.warning(motivo)
            descartes.append(motivo)
        return cond

    produtos = {p.product_id: p for p in lido["products"]
                if ref_ok(p.category_id in categorias, f"produto {p.product_id} descartado: categoria inexistente")}
    promocoes = [p for p in lido["promotions"]
                 if ref_ok(p.product_id in produtos, f"promoção {p.promotion_id} descartada: produto inexistente")]
    pedidos = {p.order_id: p for p in lido["orders"]
               if ref_ok(p.customer_id in clientes, f"pedido {p.order_id} descartado: cliente inexistente")}
    itens: dict[int, list[ItemPedido]] = defaultdict(list)
    for i in lido["order_items"]:
        if ref_ok(i.order_id in pedidos and i.product_id in produtos,
                  f"item do pedido {i.order_id} descartado: pedido ou produto inexistente"):
            itens[i.order_id].append(i)

    return Catalogo(categorias, clientes, produtos, promocoes, pedidos, dict(itens), descartes)
