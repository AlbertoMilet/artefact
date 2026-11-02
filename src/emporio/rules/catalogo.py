"""Disponibilidade e busca no catálogo (RN-05, RN-13, RN-14; §7.3; A9, A18).

Busca aproximada: texto sem acento e sem caixa; "Takamine GD 20" acha "Takamine GD20"; erros
pequenos de digitação são tolerados. Resultado ordenado por relevância e, no empate, por id.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Literal

from emporio.data.loader import Catalogo
from emporio.data.models import Produto
from emporio.data.normalize import compactar, normalizar
from emporio.rules.precos import Preco, preco_final

Disponibilidade = Literal["disponivel", "sem_estoque", "descontinuado", "em_breve"]

# Palavras que não ajudam a achar produto
PALAVRAS_VAZIAS = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "e", "com", "para",
                   "pra", "quero", "tem", "voces", "vcs", "modelo", "instrumento", "preco", "quanto", "custa"}

# Termo do cliente -> categoria
SINONIMOS_CATEGORIA = {
    "violao": "Violões", "violoes": "Violões", "guitarra": "Guitarras", "guitarras": "Guitarras",
    "baixo": "Baixos", "baixos": "Baixos", "contrabaixo": "Baixos", "bateria": "Baterias e Percussão",
    "baterias": "Baterias e Percussão", "teclado": "Teclados e Pianos", "teclados": "Teclados e Pianos",
    "piano": "Teclados e Pianos", "sintetizador": "Teclados e Pianos", "ukulele": "Ukuleles",
    "ukuleles": "Ukuleles", "uke": "Ukuleles",
}

LIMIAR_RELEVANCIA = 0.6
LIMITE_MAXIMO = 10


def disponibilidade(produto: Produto) -> Disponibilidade:
    """§7.3: descontinuado vale mais que o estoque (produto 136 tem 13 unidades, A9)."""
    if produto.status == "discontinued":
        return "descontinuado"
    if produto.status == "coming_soon":
        return "em_breve"
    return "disponivel" if produto.stock_quantity > 0 else "sem_estoque"


@dataclass(frozen=True)
class Resultado:
    produto: Produto
    preco: Preco
    disponibilidade: Disponibilidade
    relevancia: float


def _relevancia(produto: Produto, categoria_nome: str, termos: list[str], texto_compacto: str) -> float:
    nome_c = compactar(produto.name)
    if texto_compacto and texto_compacto in nome_c:
        return 1.0
    if not termos:
        return 1.0
    palavras_nome = normalizar(produto.name).split()
    acertos = 0.0
    for t in termos:
        if SINONIMOS_CATEGORIA.get(t) == categoria_nome:
            acertos += 1
        elif t in nome_c:
            acertos += 1
        else:
            melhor = max((SequenceMatcher(None, t, p).ratio() for p in palavras_nome), default=0)
            acertos += melhor if melhor >= 0.8 else 0
    return acertos / len(termos)


def buscar(catalogo: Catalogo, texto: str | None = None, categoria: str | None = None,
           preco_max: Decimal | None = None, marca: str | None = None, so_disponiveis: bool = True,
           limite: int = 5, so_promocao: bool = False) -> list[Resultado]:
    limite = max(1, min(limite, LIMITE_MAXIMO))
    termos = [t for t in normalizar(texto or "").split() if t not in PALAVRAS_VAZIAS]
    texto_compacto = "".join(termos)
    categoria_n = normalizar(categoria) if categoria else None
    marca_n = normalizar(marca) if marca else None

    resultados = []
    for p in catalogo.produtos.values():
        cat_nome = catalogo.categoria_nome(p.category_id)
        if categoria_n and normalizar(cat_nome) != categoria_n:
            continue
        if marca_n and normalizar(p.marca or "") != marca_n:
            continue
        disp = disponibilidade(p)
        if so_disponiveis and disp != "disponivel":
            continue
        preco = preco_final(p, catalogo.promocoes_ativas(p.product_id))
        if so_promocao and preco.promocao is None:
            continue
        if preco_max is not None and preco.melhor_a_vista > Decimal(str(preco_max)):
            continue
        rel = _relevancia(p, cat_nome, termos, texto_compacto)
        if rel >= LIMIAR_RELEVANCIA:
            resultados.append(Resultado(p, preco, disp, rel))

    resultados.sort(key=lambda r: (-r.relevancia, r.preco.melhor_a_vista, r.produto.product_id))
    return resultados[:limite]
