"""Interface web (SPEC-006 e SPEC-007): simulador de WhatsApp e painel de atendimento, sem rede."""

import sqlite3
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from emporio.agent import Agente
from emporio.alertas import CentralAlertas
from emporio.config import Config, montar_agente
from emporio.llm import FakeLLMClient
from emporio.llm.fake import chamar, responder
from emporio.policies import carregar_manual
from emporio.tools import Toolbox
from emporio.web import criar_app
from emporio.web.app import formatar
from emporio.web.repositorio import Repositorio, chave_do_telefone
from tests.unit.test_alertas import TocadorFalso

HX = {"HX-Request": "true"}


@pytest.fixture
def demo(tmp_path):
    config = replace(Config(), llm_provider="fake", tickets_path=tmp_path / "t.jsonl")
    repo = Repositorio(tmp_path / "atendimento.db")
    return TestClient(criar_app(montar_agente(config), config, repo)), repo


def test_inicio_vai_para_o_atendimento_e_simulador_tem_roteiro(demo):
    c, _ = demo
    r = c.get("/")
    assert r.status_code == 200 and "Atendimento" in r.text and "Nenhuma conversa ainda" in r.text
    s = c.get("/simulador")
    assert "Simulador de WhatsApp" in s.text and "Roteiro de ensaio" in s.text and "📸 Instagram" in s.text


def test_abrir_o_simulador_nao_cria_conversa(demo):
    c, repo = demo
    c.get("/simulador")
    assert repo.listar() == []


def test_mensagem_do_simulador_vira_conversa_no_painel(demo):
    c, repo = demo
    r = c.post("/simulador/mensagem", data={"texto": "Quanto custa o Takamine GD20?"}, headers=HX)
    assert 'id="painel"' in r.text and "R$ 2.089,05" in r.text and "buscar_produtos" in r.text
    [conv] = repo.listar()
    assert conv.telefone == "(67) 9****-0001" and conv.status == "lia" and conv.total == 2
    painel = c.get("/atendimento/lista").text
    assert "(67) 9****-0001" in painel and "com a Lia" in painel
    assert "R$ 2.089,05" in c.get(f"/atendimento/{conv.id}").text


def test_vendedor_assume_responde_e_devolve(demo):
    c, repo = demo
    c.post("/simulador/mensagem", data={"texto": "Quero falar com um vendedor"}, headers=HX)
    [conv] = repo.listar()
    assert conv.aguardando_vendedor
    assert c.post(f"/atendimento/{conv.id}/responder", data={"texto": "Oi"}).status_code == 409   # sem assumir
    c.post(f"/atendimento/{conv.id}/assumir")
    c.post(f"/atendimento/{conv.id}/responder", data={"texto": "Olá! Sou o Carlos, em que posso ajudar?"})
    r = c.post("/simulador/mensagem", data={"texto": "Quero ver um violão"}, headers=HX)
    assert "Sou o Carlos" in r.text and "Vendedor da loja" in r.text and "a Lia está pausada" in r.text
    autores = [m.autor for m in repo.mensagens(conv.id)]
    assert autores[-3:] == ["sistema", "vendedor", "cliente"]                      # a Lia não respondeu
    c.post(f"/atendimento/{conv.id}/devolver")
    c.post("/simulador/mensagem", data={"texto": "Estão abertos agora?"}, headers=HX)
    assert repo.mensagens(conv.id)[-1].autor == "lia" and repo.conversa(conv.id).status == "lia"


def test_alerta_e_origem_no_painel(catalogo, tmp_path):
    central = CentralAlertas(TocadorFalso(), tmp_path / "alertas.jsonl")
    llm = FakeLLMClient([chamar("info_loja"), responder("Claro, vou chamar alguém da equipe.")])
    agente = Agente(llm, Toolbox(catalogo, carregar_manual(), tickets_path=tmp_path / "t.jsonl"), alertas=central)
    c = TestClient(criar_app(agente, Config(), Repositorio(tmp_path / "a.db")))
    c.post("/simulador/mensagem", data={"texto": "Quero falar com um vendedor 📸"}, headers=HX)
    alertas = c.get("/atendimento/alertas").text
    assert "Pediu um vendedor" in alertas and "📸 Instagram" in alertas
    lista = c.get("/atendimento/lista").text
    assert "pediu vendedor" in lista and "📸 Instagram" in lista
    assert "Alerta para o vendedor" not in c.get("/simulador/thread").text           # o cliente não vê o alerta


def test_historico_sobrevive_ao_reinicio_e_telefone_nao_fica_em_claro(tmp_path):
    config = replace(Config(), llm_provider="fake", tickets_path=tmp_path / "t.jsonl")
    banco = tmp_path / "atendimento.db"
    c1 = TestClient(criar_app(montar_agente(config), config, Repositorio(banco)))
    c1.post("/simulador/mensagem", data={"texto": "pedido 8, telefone (67) 99654-7821"})
    c2 = TestClient(criar_app(montar_agente(config), config, Repositorio(banco)))     # "reiniciou"
    [conv] = Repositorio(banco).listar()
    pagina = c2.get(f"/atendimento/{conv.id}").text
    assert "pedido 8" in pagina and "99654-7821" not in pagina
    dump = "\n".join(sqlite3.connect(banco).iterdump())
    assert "98888-0001" not in dump and "99654-7821" not in dump and chave_do_telefone("(67) 98888-0001") in dump


def test_trocar_de_cliente_separa_conversas_e_apagar(demo):
    c, repo = demo
    c.post("/simulador/mensagem", data={"texto": "Estão abertos agora?"})
    c.get("/simulador", params={"telefone": "(81) 97777-0002"})
    c.post("/simulador/mensagem", data={"texto": "Qual o endereço?"})
    assert {x.telefone for x in repo.listar()} == {"(67) 9****-0001", "(81) 9****-0002"}
    c.post("/simulador/apagar")
    assert {x.telefone for x in repo.listar()} == {"(67) 9****-0001"}
    assert "inválido" in c.get("/simulador", params={"telefone": "123"}).text


def test_html_do_cliente_e_escapado(demo):
    c, _ = demo
    r = c.post("/simulador/mensagem", data={"texto": "<script>alert(1)</script>"}, headers=HX)
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text


def test_conversa_inexistente_404(demo):
    c, _ = demo
    assert c.get("/atendimento/naoexiste").status_code == 404


def test_formatar_markdown_minimo_e_seguro():
    assert formatar("**R$ 10** e _nota_ <b>") == "<strong>R$ 10</strong> e <em>nota</em> &lt;b&gt;"
    assert formatar("protocolo SIM_2026_0001") == "protocolo SIM_2026_0001"
