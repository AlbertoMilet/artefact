"""Interface web do atendimento (SPEC-006): sem rede, com o modo demonstração ou um LLM roteirizado."""

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
from tests.unit.test_alertas import TocadorFalso


@pytest.fixture
def cliente_demo(tmp_path):
    config = replace(Config(), llm_provider="fake", tickets_path=tmp_path / "t.jsonl")
    return TestClient(criar_app(montar_agente(config), config))


def test_pagina_inicial_com_roteiro_e_canais(cliente_demo):
    r = cliente_demo.get("/")
    assert r.status_code == 200 and "Atendimento com a Lia" in r.text
    assert "Roteiro de ensaio" in r.text and "📸 Instagram" in r.text and "modo demonstração" in r.text
    assert "emporio_conversa" in r.cookies


def test_mensagem_via_htmx_responde_com_rastro(cliente_demo):
    cliente_demo.get("/")
    r = cliente_demo.post("/mensagem", data={"texto": "Quanto custa o Takamine GD20?"}, headers={"HX-Request": "true"})
    assert r.status_code == 200 and 'id="painel"' in r.text and "R$ 2.089,05" in r.text and "buscar_produtos" in r.text
    assert "assistente virtual com IA" in r.text                                   # aviso na primeira resposta


def test_sem_htmx_redireciona_e_conversa_fica_na_sessao(cliente_demo):
    r = cliente_demo.post("/mensagem", data={"texto": "Estão abertos agora?"}, follow_redirects=False)
    assert r.status_code == 303
    assert "14 de Maio" in cliente_demo.get("/").text


def test_origem_aparece_no_painel(cliente_demo):
    cliente_demo.get("/")
    r = cliente_demo.post("/mensagem", data={"texto": "Olá! Quero mais informações 🎬"}, headers={"HX-Request": "true"})
    assert "🎬 TikTok" in r.text and "Chegar por um canal" not in r.text            # botões só no início


def test_conversas_separadas_por_navegador(cliente_demo, tmp_path):
    outro = TestClient(cliente_demo.app)
    cliente_demo.post("/mensagem", data={"texto": "Estão abertos agora?"})
    assert "14 de Maio" not in outro.get("/").text


def test_nova_conversa_limpa(cliente_demo):
    cliente_demo.post("/mensagem", data={"texto": "Estão abertos agora?"})
    cliente_demo.post("/nova")
    assert "Nenhuma mensagem ainda" in cliente_demo.get("/").text


def test_html_do_cliente_e_escapado(cliente_demo):
    r = cliente_demo.post("/mensagem", data={"texto": "<script>alert(1)</script>"}, headers={"HX-Request": "true"})
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text


def test_formatar_markdown_minimo_e_seguro():
    assert formatar("**R$ 10** e _nota_ <b>") == "<strong>R$ 10</strong> e <em>nota</em> &lt;b&gt;"
    assert formatar("protocolo SIM_2026_0001") == "protocolo SIM_2026_0001"


def test_alerta_vai_para_conversa_e_painel_do_vendedor(catalogo, tmp_path):
    central = CentralAlertas(TocadorFalso(), tmp_path / "alertas.jsonl")
    llm = FakeLLMClient([chamar("info_loja"), responder("Claro, vou chamar alguém da equipe.")])
    agente = Agente(llm, Toolbox(catalogo, carregar_manual(), tickets_path=tmp_path / "t.jsonl"), alertas=central)
    c = TestClient(criar_app(agente, Config()))
    r = c.post("/mensagem", data={"texto": "Olá! Quero falar com um vendedor 📸"}, headers={"HX-Request": "true"})
    assert "Alerta para o vendedor" in r.text
    painel = c.get("/vendedor/alertas").text
    assert "Cliente pediu um vendedor" in painel and "📸 Instagram" in painel
    assert "Ativar som" in c.get("/vendedor").text
