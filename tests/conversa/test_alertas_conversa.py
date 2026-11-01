"""Alertas integrados ao agente e ao CLI (SPEC-003)."""

import json

import pytest

from emporio import cli
from emporio.agent import Agente
from emporio.alertas import CentralAlertas
from emporio.alertas.central import ler_fila
from emporio.llm import FakeLLMClient
from emporio.llm.fake import chamar, responder
from emporio.policies import carregar_manual
from emporio.tools import Toolbox
from tests.unit.test_alertas import TocadorFalso


def test_agente_emite_alerta_de_pedido_e_de_encaminhamento(catalogo, tmp_path):
    central = CentralAlertas(TocadorFalso(), tmp_path / "alertas.jsonl")
    llm = FakeLLMClient([
        responder("Claro! Posso registrar seu pedido de atendimento humano. Confirma?"),
        chamar("registrar_solicitacao", tipo="atendimento_humano", resumo="Cliente quer falar com vendedor",
               confirmado=False),
        responder("Resumo: cliente quer falar com vendedor. Posso registrar?"),
        chamar("registrar_solicitacao", tipo="atendimento_humano", resumo="Cliente quer falar com vendedor",
               confirmado=True),
        responder("Registrei sua solicitação (protótipo)."),
    ])
    ag = Agente(llm, Toolbox(catalogo, carregar_manual(), tickets_path=tmp_path / "t.jsonl"), alertas=central)
    c = ag.nova_conversa()
    r1 = ag.responder(c, "quero falar com um vendedor")
    assert [a.tipo for a in r1.alertas] == ["pedido_vendedor"]
    ag.responder(c, "pode preparar o registro")
    r3 = ag.responder(c, "sim, confirmo")
    assert [a.tipo for a in r3.alertas] == ["encaminhamento"] and r3.alertas[0].tocar is False
    assert central.tocador.tocados == ["vendedor"]
    assert [l["tipo"] for l in ler_fila(central.fila)] == ["pedido_vendedor", "encaminhamento"]


def test_conversa_comum_nao_alerta(catalogo, tmp_path):
    central = CentralAlertas(TocadorFalso(), tmp_path / "alertas.jsonl")
    ag = Agente(FakeLLMClient([chamar("info_loja"), responder("Rua 14 de Maio.")]),
                Toolbox(catalogo, carregar_manual()), alertas=central)
    assert ag.responder(ag.nova_conversa(), "qual o endereço?").alertas == []
    assert not central.fila.exists()


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "RAIZ", tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("TICKETS_PATH", str(tmp_path / "tickets.jsonl"))


def test_cli_mostra_aviso_e_grava_a_fila(ambiente, capsys, tmp_path):
    cli.main(["chat", "--fake", "-m", "quero falar com um vendedor", "-m", "/som", "-m", "/som"])
    out = capsys.readouterr().out
    assert "▲ vendedor 🙋 Cliente pediu um vendedor" in out
    assert "Som dos alertas neste chat: " in out
    assert ler_fila(tmp_path / "alertas.jsonl")[0]["tipo"] == "pedido_vendedor"


def test_vendedor_testar_sem_som(ambiente, capsys):
    assert cli.main(["vendedor", "--testar", "--sem-som"]) == 0
    out = capsys.readouterr().out
    assert "pedido de vendedor (tríade x2) (som desligado)" in out


def test_configurar_som(ambiente, capsys):
    from emporio import preferencias
    cli.main(["configurar", "--som", "desligado"])
    assert preferencias.carregar()["alerta_sonoro"] is False
    assert "Som dos alertas:        desligado (preferência salva)" in capsys.readouterr().out


def test_pedido_alerta_antes_do_modelo_responder(catalogo, tmp_path):
    from emporio.llm import LLMIndisponivel
    central = CentralAlertas(TocadorFalso(), tmp_path / "alertas.jsonl")
    ag = Agente(FakeLLMClient([LLMIndisponivel("fora do ar")]), Toolbox(catalogo, carregar_manual()), alertas=central)
    r = ag.responder(ag.nova_conversa(), "quero falar com um vendedor")
    assert r.segura and [a.tipo for a in r.alertas] == ["pedido_vendedor"]      # alertou mesmo com o LLM fora


def test_som_no_chat_desligado_por_padrao(monkeypatch, tmp_path):
    from emporio.config import Config, montar_agente
    monkeypatch.setenv("ALERTA_SONORO", "true")
    monkeypatch.setattr("emporio.config.load_dotenv", lambda *a, **k: None)
    ag = montar_agente(Config(llm_provider="fake", tickets_path=tmp_path / "t.jsonl"))
    assert ag.alertas.tocador.ligado is False                                    # só o vigia toca
    ag2 = montar_agente(Config(llm_provider="fake", som_no_chat=True, tickets_path=tmp_path / "t.jsonl"))
    assert ag2.alertas.tocador.ligado is True
