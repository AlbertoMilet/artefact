"""Preço, PIX, promoção, parcelamento e frete (CA-01, CA-02, CA-03, CA-06, CA-19)."""

from decimal import Decimal

import pytest

from emporio.rules.dinheiro import brl
from emporio.rules.frete import frete, frete_metropolitano
from emporio.rules.parcelamento import parcela_permitida, parcelamento_maximo, parcelar
from emporio.rules.precos import preco_final, promocao_vigente

D = Decimal


def test_ca01_produto_95_sem_promocao(catalogo):
    p = preco_final(catalogo.produtos[95], catalogo.promocoes_ativas(95))
    assert (p.tabela, p.final, p.pix, p.promocao) == (D("2199.00"), D("2199.00"), D("2089.05"), None)
    assert brl(p.pix) == "R$ 2.089,05"


def test_ca02_produto_121_promocao_ativa_sem_pix(catalogo):
    p = preco_final(catalogo.produtos[121], catalogo.promocoes_ativas(121))
    assert p.tabela == D("549.00")
    assert p.final == D("439.20")
    assert p.pix is None                        # §6.2: PIX não se acumula com promoção
    assert p.promocao.promotion_id == 14
    assert p.melhor_a_vista == D("439.20")


def test_promocao_inativa_nao_vale(catalogo):
    # produto 95 tem a promoção 4 (12%, Oferta Especial) inativa
    assert any(pr.product_id == 95 and not pr.is_active for pr in catalogo.promocoes)
    assert preco_final(catalogo.produtos[95], catalogo.promocoes).promocao is None


def test_duas_promocoes_ativas_vale_a_maior(catalogo):
    base = catalogo.promocoes_ativas(121)[0]
    maior = base.model_copy(update={"promotion_id": 900, "discount_percent": D("30")})
    assert promocao_vigente([base, maior]).promotion_id == 900


def test_ca03_frete_limite_de_500():
    assert frete_metropolitano(D("500.00")) == D("35.00")
    assert frete_metropolitano(D("500.01")) == D("0.00")
    assert frete_metropolitano(D("499.99")) == D("35.00")


def test_frete_outras_cidades_sem_valor():
    f = frete("Dourados", D("1000"))
    assert f.tipo == "outras_cidades" and f.valor is None
    assert {m["modalidade"] for m in f.modalidades} == {"PAC (Correios)", "SEDEX (Correios)", "Jadlog (.package)"}
    assert frete("campo grande", D("600")).valor == D("0.00")


def test_ca06_parcela_minima_por_faixa():
    assert not parcela_permitida(D("349.90"), 6)       # 58,32 < 80 (pedido 9, A4)
    assert parcela_permitida(D("159.90"), 3)           # 53,30 >= 50 (pedido 7)
    assert not parcela_permitida(D("429.90"), 6)       # pedido 16
    assert not parcela_permitida(D("459.90"), 12)      # pedido 18
    assert parcela_permitida(D("1200.00"), 12)         # 100 exatos
    assert not parcela_permitida(D("1199.99"), 12)


def test_ca19_parcelamento_maximo():
    p = parcelamento_maximo(D("2199.00"))
    assert (p.parcelas, p.valor_parcela, p.primeira_parcela) == (12, D("183.25"), D("183.25"))
    p = parcelamento_maximo(D("159.90"))
    assert (p.parcelas, p.valor_parcela) == (3, D("53.30"))
    assert parcelamento_maximo(D("45.00")).parcelas == 1


def test_diferenca_de_centavos_vai_na_primeira_parcela():
    p = parcelar(D("200.00"), 3)
    assert (p.primeira_parcela, p.valor_parcela) == (D("66.68"), D("66.66"))
    assert p.primeira_parcela + p.valor_parcela * 2 == D("200.00")


def test_parcelas_fora_do_intervalo():
    with pytest.raises(ValueError):
        parcelar(D("5000"), 13)
    with pytest.raises(ValueError):
        parcelar(D("349.90"), 6)
