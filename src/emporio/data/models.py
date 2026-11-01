"""Modelos tipados das tabelas da loja. Dinheiro em Decimal (SPEC-001, AGENTS.md)."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator

from emporio.data.normalize import descricao_confiavel, marca_do_nome, normalizar_specs

StatusProduto = Literal["active", "discontinued", "coming_soon"]
StatusPedido = Literal["pending", "confirmed", "shipped", "delivered", "cancelled"]


def _vazio_para_none(v):
    return None if v == "" else v


class Categoria(BaseModel):
    category_id: int
    name: str
    description: str = ""


class Cliente(BaseModel):
    customer_id: int
    name: str
    phone: str
    email: str
    city: str


class Produto(BaseModel):
    product_id: int
    name: str
    price_brl: Decimal = Field(ge=0)
    category_id: int
    description: str = ""
    stock_quantity: int = Field(ge=0)
    status: StatusProduto
    specs: dict = Field(default_factory=dict)

    @field_validator("specs", mode="before")
    @classmethod
    def _specs_json(cls, v):
        if isinstance(v, str):
            return json.loads(v) if v.strip() else {}
        return v

    @computed_field
    @property
    def marca(self) -> str | None:
        return marca_do_nome(self.name)

    @computed_field
    @property
    def descricao_confiavel(self) -> bool:
        return descricao_confiavel(self.name, self.description)

    @computed_field
    @property
    def specs_normalizadas(self) -> dict:
        return normalizar_specs(self.specs)


class Promocao(BaseModel):
    promotion_id: int
    product_id: int
    discount_percent: Decimal = Field(gt=0, lt=100)
    description: str
    is_active: bool


class Pedido(BaseModel):
    order_id: int
    customer_id: int
    order_date: date
    status: StatusPedido
    total_brl: Decimal = Field(ge=0)
    payment_method: str
    tracking_code: str | None = None
    estimated_delivery: date | None = None
    notes: str | None = None

    _v = field_validator("tracking_code", "estimated_delivery", "notes", mode="before")(_vazio_para_none)


class ItemPedido(BaseModel):
    order_id: int
    product_id: int
    quantity: int = Field(gt=0)
