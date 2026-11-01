"""Carga, validação e normalização dos dados da loja (SPEC-001, Fase 1)."""

from emporio.data.loader import Catalogo, DadosIndisponiveis, carregar
from emporio.data.models import Categoria, Cliente, ItemPedido, Pedido, Produto, Promocao

__all__ = ["Catalogo", "Categoria", "Cliente", "DadosIndisponiveis", "ItemPedido", "Pedido", "Produto",
           "Promocao", "carregar"]
