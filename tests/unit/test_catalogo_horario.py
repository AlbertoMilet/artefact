"""Busca, disponibilidade e horário (CA-07, CA-08, CA-09, RN-17)."""

from datetime import date, datetime
from decimal import Decimal

from emporio.rules.catalogo import buscar, disponibilidade
from emporio.rules.horario import FUSO, Calendario, aberto_agora, pascoa, proxima_abertura


def test_ca07_nome_abreviado_e_espacado(catalogo):
    r = buscar(catalogo, "takamine gd 20")
    assert r[0].produto.product_id == 95


def test_ca07_nome_generico_traz_os_quatro_takamine(catalogo):
    ids = {r.produto.product_id for r in buscar(catalogo, "takamine", limite=10)}
    assert ids == {95, 100, 105, 115}


def test_busca_tolera_erro_de_digitacao(catalogo):
    assert buscar(catalogo, "takamini gd20")[0].produto.product_id == 95


def test_ca08_violoes_ate_1000_so_disponiveis(catalogo):
    res = buscar(catalogo, categoria="Violões", preco_max=Decimal("1000"), limite=10)
    assert res
    for r in res:
        assert r.disponibilidade == "disponivel"
        assert r.produto.status == "active" and r.produto.stock_quantity > 0
        assert r.preco.melhor_a_vista <= Decimal("1000")


def test_filtro_de_preco_usa_melhor_preco_a_vista(catalogo):
    # produto 82 custa R$ 849,00; no PIX R$ 806,55: entra em "até R$ 810"
    ids = {r.produto.product_id for r in buscar(catalogo, categoria="Violões", preco_max=Decimal("810"), limite=10)}
    assert 82 in ids


def test_ca09_descontinuado_vale_mais_que_estoque(catalogo):
    assert disponibilidade(catalogo.produtos[136]) == "descontinuado"   # estoque 13
    assert disponibilidade(catalogo.produtos[96]) == "sem_estoque"
    assert disponibilidade(catalogo.produtos[130]) == "em_breve"
    assert disponibilidade(catalogo.produtos[95]) == "disponivel"


def test_busca_sem_resultado_para_saxofone(catalogo):
    assert buscar(catalogo, "saxofone") == []


def test_so_disponiveis_falso_mostra_descontinuado(catalogo):
    nome = catalogo.produtos[136].name
    padrao = buscar(catalogo, nome, limite=10)
    assert 136 not in {r.produto.product_id for r in padrao}           # escondido por padrão
    assert all(r.disponibilidade == "disponivel" for r in padrao)      # equivalentes disponíveis (§7.3)
    assert buscar(catalogo, nome, so_disponiveis=False)[0].produto.product_id == 136


def _dt(*a):
    return datetime(*a, tzinfo=FUSO)


def test_horario_dias_uteis_e_sabado():
    assert aberto_agora(_dt(2026, 11, 3, 9, 0))           # terça 09:00
    assert not aberto_agora(_dt(2026, 11, 3, 18, 0))      # terça 18:00 já fechou
    assert aberto_agora(_dt(2026, 11, 7, 12, 59))         # sábado
    assert not aberto_agora(_dt(2026, 11, 7, 13, 0))
    assert not aberto_agora(_dt(2026, 11, 8, 10, 0))      # domingo


def test_feriados():
    assert not aberto_agora(_dt(2026, 11, 2, 10, 0))      # Finados (segunda)
    assert pascoa(2026) == date(2026, 4, 5)
    assert Calendario().feriado(date(2026, 4, 3)) == "Sexta-feira Santa"
    extra = Calendario(extras={date(2026, 11, 27): "Black Friday (fechado para inventário)"})
    assert not aberto_agora(_dt(2026, 11, 27, 10, 0), extra)


def test_relogio_fixo_converte_para_campo_grande():
    from datetime import timezone
    from emporio.rules.horario import relogio_fixo
    agora = relogio_fixo(datetime(2026, 3, 25, 2, 0, tzinfo=timezone.utc))()
    assert agora.date() == date(2026, 3, 24) and agora.hour == 22


def test_proxima_abertura():
    assert proxima_abertura(_dt(2026, 11, 6, 20, 0)) == _dt(2026, 11, 7, 9, 0)     # sexta 20h -> sábado 9h
    assert proxima_abertura(_dt(2026, 11, 7, 14, 0)) == _dt(2026, 11, 9, 9, 0)     # sábado 14h -> segunda
    assert proxima_abertura(_dt(2026, 11, 1, 10, 0)) == _dt(2026, 11, 3, 9, 0)     # domingo; segunda é Finados


def test_so_promocao_acha_promocoes_parecidas_na_categoria(catalogo):
    """'Tem promoção que combine com o Taylor 214ce?': os violões com promoção ativa, de qualquer marca."""
    r = buscar(catalogo, categoria="Violões", so_promocao=True)
    assert [(x.produto.product_id, str(x.preco.final)) for x in r] == [(90, "1967.18"), (94, "5519.08")]
    assert buscar(catalogo, texto="Taylor 214ce", so_promocao=True) == []      # o 214ce não tem promoção ativa
