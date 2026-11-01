"""Arrependimento, verificação do dono e máscara (CA-04, CA-05, RN-09)."""

from datetime import date

from emporio.rules.devolucao import elegivel_arrependimento
from emporio.rules.verificacao import mascarar_email, mascarar_telefone, mascarar_texto, verificar_dono

HOJE = date(2026, 3, 25)


def test_ca04_setimo_dia_online_e_elegivel():
    r = elegivel_arrependimento("delivered", date(2026, 3, 18), "online", HOJE)
    assert (r.elegivel, r.motivo, r.dias_desde_recebimento) == (True, "dentro_do_prazo", 7)
    assert r.condicoes


def test_ca04_oitavo_dia_nao_elegivel_com_alternativas():
    r = elegivel_arrependimento("delivered", date(2026, 3, 17), "online", HOJE, data_compra=date(2026, 3, 10))
    assert (r.elegivel, r.motivo) == (False, "fora_do_prazo")
    por_tipo = {a.tipo: a.dentro_do_prazo for a in r.alternativas}
    assert por_tipo["troca por preferência"] is False
    assert por_tipo["troca por defeito de fabricação"] is True     # compra há 15 dias
    assert por_tipo["garantia legal"] is True


def test_ca04_compra_na_loja_nao_tem_arrependimento():
    r = elegivel_arrependimento("delivered", date(2026, 3, 24), "loja", HOJE)
    assert (r.elegivel, r.motivo) == (False, "compra_na_loja")
    assert r.alternativas


def test_sem_data_ou_canal_resposta_condicional():
    r = elegivel_arrependimento("delivered", None, None, HOJE)
    assert (r.elegivel, r.motivo) == (None, "faltam_dados")
    assert r.condicoes


def test_pedido_nao_entregue():
    r = elegivel_arrependimento("shipped", None, "online", HOJE)
    assert (r.elegivel, r.motivo) == (None, "pedido_nao_entregue")


def test_data_de_recebimento_no_futuro():
    assert elegivel_arrependimento("delivered", date(2026, 4, 1), "online", HOJE).motivo == "data_invalida"


def test_ca05_verificacao_do_pedido_8(catalogo):
    pedido = catalogo.pedidos[8]
    cliente = catalogo.clientes[pedido.customer_id]
    assert cliente.customer_id == 2
    assert not verificar_dono(cliente, "(67) 98432-1098")        # telefone de outro cliente
    assert verificar_dono(cliente, "(67) 99654-7821")
    assert verificar_dono(cliente, "67996547821")
    assert verificar_dono(cliente, "+55 67 99654-7821")
    assert verificar_dono(cliente, "99654-7821")                  # sem DDD
    assert verificar_dono(cliente, "AnaCarol.Ferreira@coldmail.com")
    assert not verificar_dono(cliente, "7821")
    assert not verificar_dono(cliente, "")


def test_mascaras():
    assert mascarar_telefone("(67) 99654-7821") == "(67) 9****-7821"
    assert mascarar_email("anacarol.ferreira@coldmail.com") == "a***@coldmail.com"
    texto = mascarar_texto("ligue (67) 99654-7821 ou escreva para anacarol.ferreira@coldmail.com")
    assert "99654" not in texto and "anacarol" not in texto
