"""Busca por seção no manual (D-04) e fidelidade da conversão."""

import pytest

from emporio.policies import carregar_manual


@pytest.fixture(scope="module")
def manual():
    return carregar_manual()


def test_manual_tem_as_dez_secoes(manual):
    assert [s.split()[0] for s in manual.secoes] == [f"§{i}" for i in range(1, 11)]


@pytest.mark.parametrize("pergunta, secao", [
    ("Me arrependi da minha compra, posso devolver meu pedido?", "§4.1"),
    ("em quantas vezes posso parcelar no cartão?", "§3.1"),
    ("qual o frete pra Dourados?", "§5.2"),
    ("vocês abrem sábado?", "§2"),
    ("meu violão quebrou, tem garantia?", "§8.1"),
    ("vendem cordas?", "§1"),
    ("o desconto do pix vale junto com promoção?", "§6.2"),
    ("quero excluir meus dados", "§9"),
    ("qual o endereço da loja?", "§1.2"),
    ("como rastrear meu pedido", "§5.3"),
    ("posso trocar por outra cor?", "§4.3"),
    ("quero fazer uma reclamação", "§7.3"),
])
def test_pergunta_cai_na_secao_certa(manual, pergunta, secao):
    assert manual.buscar(pergunta)[0].secao == secao


def test_fora_do_escopo_nao_retorna_trecho(manual):
    assert manual.buscar("qual a previsão do tempo amanhã?") == []
    assert manual.buscar("quem ganhou o jogo ontem?") == []


def test_notas_de_revisao_acompanham_o_trecho(manual):
    t = next(t for t in manual.trechos if t.secao == "§7")
    assert "3341-4444" in t.texto            # nota A1 junto do telefone da §7
