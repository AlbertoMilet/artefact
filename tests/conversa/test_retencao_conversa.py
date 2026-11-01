"""Retenção integrada ao agente e ao CLI (SPEC-002 CI-08, CI-09)."""

import json
from datetime import datetime, timedelta

import pytest

from emporio import cli
from emporio.agent import Agente
from emporio.llm import FakeLLMClient
from emporio.llm.fake import chamar, responder
from emporio.policies import carregar_manual
from emporio.retencao import ConfigRetencao, Retencao, Status
from emporio.rules.horario import FUSO, RelogioAjustavel, relogio_fixo
from emporio.tools import Toolbox

T0 = datetime(2026, 3, 25, 10, 0, tzinfo=FUSO)
TEL_5 = "(67) 98765-4321"


@pytest.fixture
def relogio():
    return RelogioAjustavel(relogio_fixo(T0))


def montar(catalogo, relogio, tmp_path, roteiro, ativa=True):
    llm = FakeLLMClient(roteiro)
    tb = Toolbox(catalogo, carregar_manual(), relogio, tickets_path=tmp_path / "t.jsonl")
    return Agente(llm, tb, retencao=Retencao(llm, ConfigRetencao(ativa=ativa))), llm


def test_ci08_voltar_depois_de_24h_exige_nova_verificacao(catalogo, relogio, tmp_path):
    ag, _ = montar(catalogo, relogio, tmp_path, [
        chamar("consultar_pedido", pedido_id=5, verificacao=TEL_5), responder("Pedido 5 entregue."),
        chamar("consultar_pedido", pedido_id=5), responder("Preciso confirmar seus dados de novo."),
    ], ativa=False)
    c = ag.nova_conversa()
    ag.responder(c, f"pedido 5, telefone {TEL_5}")
    assert c.sessao.pedido_verificado == 5
    relogio.avancar(timedelta(hours=25))
    r = ag.responder(c, "e o pedido 5?")
    assert json.loads(r.rastro[0].completo)["autorizado"] is False


def test_dentro_da_janela_a_verificacao_continua(catalogo, relogio, tmp_path):
    ag, _ = montar(catalogo, relogio, tmp_path, [
        chamar("consultar_pedido", pedido_id=5, verificacao=TEL_5), responder("ok"),
        chamar("consultar_pedido", pedido_id=5), responder("ok"),
    ], ativa=False)
    c = ag.nova_conversa()
    ag.responder(c, f"pedido 5, telefone {TEL_5}")
    relogio.avancar(timedelta(hours=23))
    r = ag.responder(c, "e o pedido 5?")
    assert json.loads(r.rastro[0].completo)["autorizado"] is True


def test_silencio_gera_lembrete_e_resposta_reinicia(catalogo, relogio, tmp_path):
    ag, llm = montar(catalogo, relogio, tmp_path, [
        chamar("buscar_produtos", texto="violão", preco_max=1000), responder("Tenho 5 violões. Quer detalhes?"),
        responder(json.dumps({"acao": "ENVIAR", "mensagem": "Ficou alguma dúvida sobre os violões?", "motivo": "t"})),
        responder("Claro! O Yamaha C40 é ótimo para começar."),
    ])
    c = ag.nova_conversa()
    ag.responder(c, "violões até 1000?")
    ac = c.acompanhamento
    assert ac.status == Status.ATIVO and ac.proxima_avaliacao == T0 + timedelta(minutes=30)
    relogio.avancar(timedelta(minutes=30))
    av = ag.retencao.avaliar(ac, c.historico, relogio())
    assert av.acao == "ENVIAR" and c.historico[-1]["content"] == "Ficou alguma dúvida sobre os violões?"
    ag.responder(c, "qual é melhor para iniciante?")
    assert ac.status == Status.ATIVO and ac.lembretes == []
    # o modelo principal vê o lembrete no histórico
    assert any(m.get("content") == "Ficou alguma dúvida sobre os violões?" for m in llm.chamadas[-1]["mensagens"])


def test_cliente_pede_para_parar_durante_a_conversa(catalogo, relogio, tmp_path):
    ag, _ = montar(catalogo, relogio, tmp_path, [responder("Tudo bem, não envio mais mensagens.")])
    c = ag.nova_conversa()
    ag.responder(c, "pare de me mandar mensagem")
    assert c.acompanhamento.optou_sair and c.acompanhamento.proxima_avaliacao is None


@pytest.fixture
def ambiente_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "RAIZ", tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("TICKETS_PATH", str(tmp_path / "tickets.jsonl"))
    monkeypatch.setenv("DATA_REFERENCIA", "2026-03-25T10:00:00")
    monkeypatch.setenv("RETENCAO_ATIVA", "false")


def test_ci09_esperar_no_cli_com_retencao(ambiente_cli, capsys):
    assert cli.main(["chat", "--fake", "--retencao", "-m", "Quanto custa o Takamine GD20?",
                     "-m", "/esperar 30m", "-m", "/janela"]) == 0
    out = capsys.readouterr().out
    assert "♪ Lia (lembrete, qua 25/03 10:30) ›" in out
    assert "Janela aberta até 26/03 10:00" in out and "lembrete_enviado" in out


def test_ci09_esperar_sem_retencao_nao_envia(ambiente_cli, capsys):
    cli.main(["chat", "--fake", "-m", "oi", "-m", "/esperar 30m"])
    out = capsys.readouterr().out
    assert "retenção desligada" in out and "Lia (lembrete" not in out


def test_esperar_um_dia_fecha_a_janela(ambiente_cli, capsys):
    cli.main(["chat", "--fake", "--retencao", "-m", "oi", "-m", "/esperar 1d"])
    out = capsys.readouterr().out
    assert out.count("Lia (lembrete") == 2                  # modo demonstração: 2 lembretes e depois para
    assert "Janela encerrada" in out


def test_atendimento_humano_vale_so_para_aquela_janela(catalogo, relogio, tmp_path):
    ag, _ = montar(catalogo, relogio, tmp_path, [responder("ok"), responder("oi de novo")])
    c = ag.nova_conversa()
    ag.responder(c, "oi")
    c.sessao.atendimento_humano = True
    relogio.avancar(timedelta(hours=25))
    ag.responder(c, "voltei")
    assert c.sessao.atendimento_humano is False and c.acompanhamento.status == Status.ATIVO
