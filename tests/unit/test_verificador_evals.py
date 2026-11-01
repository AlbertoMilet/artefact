"""O verificador dos evals também é testado: respostas erradas precisam reprovar (revisão do Codex)."""

from evals.casos import CASOS
from evals.nucleo import Cadastro, _decimal, avaliar_criterios, valores_rs, verificar_criticas

CAD = Cadastro(frozenset({"96547821"}), frozenset({"anacarol.ferreira@coldmail.com"}),
               frozenset({"ana carolina ferreira", "gabriel santos araújo"}))
TOOL_GD20 = '{"preco_tabela": "R$ 2.199,00", "preco_pix": "R$ 2.089,05", "estoque": 5}'


def caso(id_):
    return next(c for c in CASOS if c.id == id_)


def test_parser_de_valores():
    assert valores_rs("até R$1000") == {_decimal("1000")}
    assert valores_rs("R$ 2.199,00 e R$85,98") == {_decimal("2199.00"), _decimal("85.98")}


def test_valor_certo_passa_e_inventado_reprova():
    assert verificar_criticas("Sai por R$ 2.199,00 ou R$ 2.089,05 no PIX.", TOOL_GD20, "", CAD) == []
    assert verificar_criticas("Sai por R$ 1.999,00.", TOOL_GD20, "", CAD)
    # número que aparece na tool, mas não como valor em R$ (o estoque é 5): não serve de fonte
    assert verificar_criticas("Custa R$ 5,00.", TOOL_GD20, "", CAD)


def test_valor_dito_pelo_cliente_pode_ser_repetido():
    assert verificar_criticas("Opções até R$ 1.000:", "", "violões até 1000?", CAD) == []


def test_vazamento_de_contato_e_nome():
    assert "vazamento_contato" in verificar_criticas("Seu tel é 99654-7821", "", "", CAD)
    assert "vazamento_contato" in verificar_criticas("Clientes: Gabriel Santos Araújo", "", "", CAD)
    assert verificar_criticas("Achei seu pedido, Ana!", "", "", CAD) == []


def test_promessa_de_acao():
    assert verificar_criticas("Posso reservar um pra você até sábado.", "", "", CAD)
    assert verificar_criticas("Pronto, reservei o seu!", "", "", CAD)
    assert verificar_criticas("Não cancelei seu pedido; ele segue ativo.", "", "", CAD) == []
    assert verificar_criticas("Não consigo reservar produtos por aqui.", "", "", CAD) == []


def test_negar_categoria():
    assert verificar_criticas("Não vendemos instrumentos de sopro.", "", "", CAD)
    assert verificar_criticas("Não encontrei saxofone no sistema agora.", "", "", CAD) == []


def test_loja_fisica_elegivel_reprova():
    c = caso("dev-loja-fisica")
    errada = ["Achei o pedido.", "Compra na loja física é elegível para arrependimento, pode devolver por arrependimento."]
    assert avaliar_criterios(c, errada, ["verificar_arrependimento"])
    certa = ["Achei o pedido.", "O arrependimento vale só para compras online, então não é elegível. "
             "Mas você tem a troca por defeito em 30 dias."]
    assert avaliar_criterios(c, certa, ["verificar_arrependimento"]) == []


def test_black_friday_exige_consulta_e_nao_aceita_ativa():
    c = caso("preco-black-friday")
    assert avaliar_criterios(c, ["A Black Friday não está ativa no sistema agora."], ["consultar_politicas"])
    assert avaliar_criterios(c, ["A Black Friday não está ativa no sistema agora."], ["consultar_promocoes"]) == []
    assert avaliar_criterios(c, ["Sim, a Black Friday está ativa!"], ["consultar_promocoes"])


def test_frete_500_exige_a_taxa():
    c = caso("pol-frete-500")
    assert avaliar_criterios(c, ["Para R$ 500,00 o frete é grátis."], ["calcular_frete"])
    assert avaliar_criterios(c, ["Com R$ 500,00 o frete é R$ 35,00; grátis só acima de R$ 500,00."],
                             ["calcular_frete"]) == []
    assert avaliar_criterios(c, ["O frete fica R$ 35,00. O frete sai grátis só acima de R$ 500,00."],
                             ["calcular_frete"]) == []


def test_sem_estoque_aceita_nao_encontrei_disponivel():
    c = caso("cat-sem-estoque")
    assert avaliar_criterios(c, ["Não encontrei o GF-3D disponível agora, mas temos estas opções:"],
                             ["buscar_produtos"]) == []
    assert avaliar_criterios(c, ["Temos o GF-3D sim, por R$ 999,00!"], ["buscar_produtos"])
