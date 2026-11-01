"""Tools do agente (SPEC-001 §4.2, Fase 2): saídas, autorização, erros estruturados."""

import json
from datetime import datetime

import pytest

from emporio.policies import carregar_manual
from emporio.rules.horario import FUSO, relogio_fixo
from emporio.tools import Sessao, Toolbox

TEL_CLIENTE_2 = "(67) 99654-7821"     # pedido 8 (enviado), cliente 2
TEL_CLIENTE_5 = "(67) 98765-4321"     # pedido 5 (entregue), cliente 5


@pytest.fixture
def tb(catalogo, tmp_path):
    return Toolbox(catalogo, carregar_manual(), relogio_fixo(datetime(2026, 3, 25, 10, 0, tzinfo=FUSO)),
                   tickets_path=tmp_path / "tickets.jsonl")


@pytest.fixture
def s():
    return Sessao()


def test_schemas_openai_validos(tb):
    nomes = [t["function"]["name"] for t in tb.schemas_openai()]
    assert nomes == ["buscar_produtos", "detalhar_produto", "consultar_pedido", "verificar_arrependimento",
                     "consultar_politicas", "info_loja", "calcular_frete", "consultar_promocoes",
                     "registrar_solicitacao"]
    for t in tb.schemas_openai():
        assert t["function"]["parameters"]["type"] == "object"
        json.dumps(t)


def test_tool_desconhecida_e_argumento_invalido_viram_erro(tb, s):
    assert tb.executar("listar_clientes", "{}", s)["erro"] == "tool_desconhecida"
    assert tb.executar("buscar_produtos", '{"limite": 500}', s)["erro"] == "argumentos_invalidos"
    assert tb.executar("buscar_produtos", "{json quebrado", s)["erro"] == "argumentos_invalidos"
    assert tb.executar("buscar_produtos", '{"categoria": "Saxofones"}', s)["erro"] == "argumentos_invalidos"


def test_categoria_com_acento_corrompido_e_aceita(tb, s):
    # DeepSeek mandou "Violཞs" no lugar de "Violões" (Fase 5)
    r = tb.executar("buscar_produtos", {"categoria": "Violཞs", "limite": 3}, s)
    assert "erro" not in r and r["resultados"][0]["categoria"] == "Violões"
    assert tb.executar("buscar_produtos", {"categoria": "violoes"}, s)["resultados"]
    erro = tb.executar("buscar_produtos", {"categoria": "Saxofones"}, s)
    assert "Violões" in " ".join(erro["detalhes"])        # o erro lista as categorias válidas


def test_buscar_gd20_valores_formatados(tb, s):
    r = tb.executar("buscar_produtos", {"texto": "Takamine GD20"}, s)["resultados"][0]
    assert (r["produto_id"], r["preco_tabela"], r["preco_pix"], r["estoque"]) == (95, "R$ 2.199,00", "R$ 2.089,05", 5)


def test_buscar_produto_com_promocao_sem_pix(tb, s):
    r = tb.executar("buscar_produtos", {"texto": "Ohana CK-20"}, s)["resultados"][0]
    assert r["produto_id"] == 121
    assert r["promocao"] == {"descricao": "Desconto Exclusivo", "percentual": "20%", "preco_promocional": "R$ 439,20"}
    assert r["preco_pix"] is None


def test_buscar_sem_resultado_orienta_e_nao_inventa(tb, s):
    r = tb.executar("buscar_produtos", {"texto": "saxofone alto", "categoria": "Instrumentos de Sopro (Madeiras)"}, s)
    assert r["total"] == 0 and "orientacao" in r
    assert "alternativas_na_categoria" not in r          # categoria vazia (A12)


def test_buscar_modelo_descontinuado_aparece_como_indisponivel(tb, s):
    r = tb.executar("buscar_produtos", {"texto": "Shelby SN-7C"}, s)
    assert r["total"] == 0
    ind = r["indisponiveis_com_esse_nome"][0]
    assert ind["produto_id"] == 113 and "descontinuado" in ind["disponibilidade"]
    assert "preco_pix" not in ind                        # não oferta preço de produto fora do catálogo
    alternativas = {x["produto_id"] for x in r["alternativas_semelhantes"]}
    assert alternativas and 113 not in alternativas      # outros Shelby, como alternativa e não como o pedido


def test_erro_de_digitacao_ainda_e_correspondencia_forte(tb, s):
    r = tb.executar("buscar_produtos", {"texto": "takamini gd20"}, s)
    assert r["resultados"][0]["produto_id"] == 95


def test_detalhar_parcelamento_e_descricao(tb, s):
    d = tb.executar("detalhar_produto", {"produto_id": 95}, s)
    assert d["parcelamento_cartao"]["parcelas_max"] == 12
    assert d["parcelamento_cartao"]["valor_parcela"] == "R$ 183,25"
    assert d["descricao"]
    d135 = tb.executar("detalhar_produto", {"produto_id": 135}, s)
    assert d135["descricao"] is None and "aviso" in d135
    d121 = tb.executar("detalhar_produto", {"produto_id": 121}, s)
    assert d121["parcelamento_cartao"]["total_no_cartao"] == "R$ 439,20"     # parcela sobre o promocional


def test_consultar_pedido_exige_verificacao(tb, s):
    r = tb.executar("consultar_pedido", {"pedido_id": 8}, s)
    assert r == {"autorizado": False, "mensagem": r["mensagem"]}
    r = tb.executar("consultar_pedido", {"pedido_id": 8, "verificacao": "(67) 98432-1098"}, s)
    assert r["autorizado"] is False
    r = tb.executar("consultar_pedido", {"pedido_id": 8, "verificacao": TEL_CLIENTE_2}, s)
    assert r["autorizado"] and r["status"] == "enviado" and r["codigo_rastreio"] == "BRJL5544332BR"
    assert s.pedido_verificado == 8


def test_pedido_inexistente_tem_a_mesma_resposta_que_nao_autorizado(tb, s):
    a = tb.executar("consultar_pedido", {"pedido_id": 9999, "verificacao": TEL_CLIENTE_2}, s)
    b = tb.executar("consultar_pedido", {"pedido_id": 8, "verificacao": "000000000"}, s)
    assert a == b


def test_saida_do_pedido_nao_tem_telefone_nem_email(tb, s):
    r = tb.executar("consultar_pedido", {"pedido_id": 8, "verificacao": TEL_CLIENTE_2}, s)
    texto = json.dumps(r, ensure_ascii=False)
    assert "99654" not in texto and "@" not in texto
    assert r["cliente_primeiro_nome"] == "Ana"


def test_ca11_trocar_de_pedido_exige_nova_verificacao(tb, s):
    tb.executar("consultar_pedido", {"pedido_id": 8, "verificacao": TEL_CLIENTE_2}, s)
    assert tb.executar("consultar_pedido", {"pedido_id": 8}, s)["autorizado"]          # já verificado
    assert tb.executar("consultar_pedido", {"pedido_id": 5}, s)["autorizado"] is False
    assert tb.executar("consultar_pedido", {"pedido_id": 8}, s)["autorizado"] is False  # verificação caiu


def test_arrependimento_fluxo(tb, s):
    assert tb.executar("verificar_arrependimento", {"pedido_id": 5}, s)["autorizado"] is False
    tb.executar("consultar_pedido", {"pedido_id": 5, "verificacao": TEL_CLIENTE_5}, s)
    r = tb.executar("verificar_arrependimento", {"pedido_id": 5}, s)
    assert r["motivo"] == "faltam_dados" and r["elegivel"] is None
    r = tb.executar("verificar_arrependimento", {"pedido_id": 5, "data_recebimento": "2026-03-20", "canal": "online"}, s)
    assert (r["elegivel"], r["dias_desde_recebimento"]) == (True, 5)
    r = tb.executar("verificar_arrependimento", {"pedido_id": 5, "data_recebimento": "2026-03-10", "canal": "online"}, s)
    assert r["elegivel"] is False and r["alternativas"]


def test_consultar_politicas_cita_secao(tb, s):
    r = tb.executar("consultar_politicas", {"pergunta": "me arrependi, posso devolver?"}, s)
    assert r["trechos"][0]["secao"] == "§4.1"
    assert "7 (sete) dias" in r["trechos"][0]["texto"]
    r = tb.executar("consultar_politicas", {"pergunta": "qual a previsão do tempo amanhã?"}, s)
    assert r["trechos"] == [] and r["indice"]


def test_info_loja_quarta_10h_aberta(tb, s):
    r = tb.executar("info_loja", {}, s)
    assert r["aberto_agora"] is True and r["telefone_whatsapp"] == "(67) 3341-4444"
    assert r["email"] == "contato@emporiodamusica.com.br"


def test_info_loja_fechada_informa_proxima_abertura(catalogo, s):
    tb = Toolbox(catalogo, carregar_manual(), relogio_fixo(datetime(2026, 11, 6, 20, 0, tzinfo=FUSO)))
    r = tb.executar("info_loja", {}, s)
    assert r["aberto_agora"] is False
    assert r["proxima_abertura"] == "sábado, 07/11 às 09:00"


def test_ca13_registro_so_com_confirmacao(tb, s):
    s.turno = 1
    # confirmar sem proposta anterior é recusado
    r = tb.executar("registrar_solicitacao", {"tipo": "reclamacao", "resumo": "Chegou riscado", "confirmado": True}, s)
    assert r["gravado"] is False
    r = tb.executar("registrar_solicitacao", {"tipo": "reclamacao", "resumo": "Instrumento chegou riscado",
                                              "confirmado": False}, s)
    assert r["gravado"] is False and r["resumo_para_confirmar"] and not tb.tickets_path.exists()
    # mesma mensagem do cliente: ainda não houve confirmação
    r = tb.executar("registrar_solicitacao", {"tipo": "reclamacao", "resumo": "x" * 10, "confirmado": True}, s)
    assert r["gravado"] is False and not tb.tickets_path.exists()
    s.turno = 2                                           # o cliente respondeu
    r = tb.executar("registrar_solicitacao", {"tipo": "troca", "resumo": "outro tipo", "confirmado": True}, s)
    assert r["gravado"] is False                          # tipo diferente do proposto
    r = tb.executar("registrar_solicitacao", {"tipo": "reclamacao", "confirmado": True,
                                              "resumo": "Instrumento chegou riscado, contato (67) 99654-7821"}, s)
    assert r["gravado"] and r["protocolo_simulado"] == "SIM-20260325-0001"
    assert "SIM-20260325-0001" in json.dumps(r)            # protocolo não é corrompido pela máscara
    assert s.registro_proposto is None                    # autorização consumida
    linha = json.loads(tb.tickets_path.read_text(encoding="utf-8"))
    assert "99654" not in linha["resumo"] and linha["simulado"] is True


def test_calcular_frete(tb, s):
    r = tb.executar("calcular_frete", {"cidade": "Campo Grande", "valor": 500}, s)
    assert r["frete"] == "R$ 35,00"
    assert tb.executar("calcular_frete", {"cidade": "campo grande", "valor": 500.01}, s)["frete"] == "grátis"
    r = tb.executar("calcular_frete", {"cidade": "Dourados", "valor": 700}, s)
    assert r["frete"] is None and len(r["modalidades"]) == 3


def test_consultar_promocoes(tb, s):
    r = tb.executar("consultar_promocoes", {"nome": "Black Friday"}, s)
    assert r["ativas_com_esse_nome"] == [] and "orientacao" in r
    r = tb.executar("consultar_promocoes", {}, s)
    assert r["total"] == 4
    ohana = next(p for p in r["promocoes_ativas"] if "Ohana CK-20" in p["produto"])
    assert (ohana["preco_original"], ohana["preco_promocional"], ohana["percentual"]) == ("R$ 549,00", "R$ 439,20", "20%")


def test_erro_de_argumento_nao_ecoa_o_valor_recebido(tb, s):
    r = tb.executar("consultar_pedido", {"pedido_id": "fulano@jmail.com"}, s)
    assert r["erro"] == "argumentos_invalidos"
    assert "fulano" not in json.dumps(r, ensure_ascii=False)


def test_registro_com_pedido_nao_verificado_e_recusado(tb, s):
    r = tb.executar("registrar_solicitacao", {"tipo": "devolucao", "resumo": "Quero devolver o pedido 5",
                                              "pedido_id": 5, "confirmado": True}, s)
    assert r["gravado"] is False
