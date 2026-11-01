"""Origem do lead integrada ao agente, ao registro, aos alertas e ao CLI (SPEC-005)."""

import json
from datetime import datetime, timedelta

from emporio import cli
from emporio.agent import Agente
from emporio.alertas import CentralAlertas
from emporio.alertas.central import ler_fila
from emporio.llm import FakeLLMClient
from emporio.llm.fake import chamar, responder
from emporio.policies import carregar_manual
from emporio.rules.horario import FUSO, RelogioAjustavel, relogio_fixo
from emporio.tools import Toolbox
from tests.unit.test_alertas import TocadorFalso

T0 = datetime(2026, 3, 25, 10, 0, tzinfo=FUSO)


def _ultima_msg_do_cliente(llm):
    return [m for m in llm.chamadas[-1]["mensagens"] if m["role"] == "user"][-1]["content"]


def test_marcador_sai_antes_do_modelo_e_vai_para_registro_e_alerta(catalogo, tmp_path):
    central = CentralAlertas(TocadorFalso(), tmp_path / "alertas.jsonl")
    llm = FakeLLMClient([
        responder("Oi! Como posso ajudar?"),
        responder("Claro, chamo um vendedor."),
        chamar("registrar_solicitacao", tipo="reclamacao", resumo="Produto com defeito", confirmado=False),
        responder("Posso registrar?"),
        chamar("registrar_solicitacao", tipo="reclamacao", resumo="Produto com defeito", confirmado=True),
        responder("Registrei."),
    ])
    tickets = tmp_path / "t.jsonl"
    ag = Agente(llm, Toolbox(catalogo, carregar_manual(), relogio_fixo(T0), tickets_path=tickets), alertas=central)
    c = ag.nova_conversa()
    r1 = ag.responder(c, "Olá! Quero mais informações 📸")
    assert r1.origem == "instagram" and c.sessao.origem == "instagram"
    assert _ultima_msg_do_cliente(llm) == "Olá! Quero mais informações"          # o modelo não vê o emoji
    assert "📸" not in json.dumps(c.historico, ensure_ascii=False)
    r2 = ag.responder(c, "quero falar com um vendedor 🎬")                       # não é a 1.ª mensagem: não muda
    assert r2.origem is None and c.sessao.origem == "instagram"
    assert r2.alertas[0].origem == "instagram" and "Origem: 📸 Instagram." in r2.alertas[0].aviso()
    ag.responder(c, "chegou com defeito")
    ag.responder(c, "sim")
    assert json.loads(tickets.read_text(encoding="utf-8").splitlines()[-1])["origem"] == "instagram"
    assert {l["origem"] for l in ler_fila(central.fila)} == {"instagram"}


def test_sem_marcador_origem_desconhecida(catalogo, tmp_path):
    llm = FakeLLMClient([responder("Oi!")])
    ag = Agente(llm, Toolbox(catalogo, carregar_manual(), relogio_fixo(T0), tickets_path=tmp_path / "t.jsonl"))
    c = ag.nova_conversa()
    assert ag.responder(c, "Oi, tudo bem?").origem is None and c.sessao.origem is None


def test_janela_nova_aceita_novo_canal(catalogo, tmp_path):
    relogio = RelogioAjustavel(relogio_fixo(T0))
    llm = FakeLLMClient([responder("Oi!"), responder("Oi de novo!")])
    ag = Agente(llm, Toolbox(catalogo, carregar_manual(), relogio, tickets_path=tmp_path / "t.jsonl"))
    c = ag.nova_conversa()
    ag.responder(c, "Olá! Quero mais informações 📸")
    relogio.avancar(timedelta(hours=25))                                          # janela de 24 h fechou
    assert ag.responder(c, "Olá! Quero mais informações ▶️").origem == "youtube"
    assert c.sessao.origem == "youtube"


def test_cli_links_e_relatorio(capsys, tmp_path):
    assert cli.main(["origem", "links"]) == 0
    out = capsys.readouterr().out
    assert out.count("https://wa.me/556733414444?text=") == 4 and "TikTok" in out
    log = tmp_path / "emporio.jsonl"
    linhas = [{"evento": "turno", "conversa": "a", "origem": "instagram"},
              {"evento": "turno", "conversa": "a", "origem": "instagram"},
              {"evento": "turno", "conversa": "b", "origem": None},
              {"evento": "turno", "conversa": "c", "origem": "google"}]
    log.write_text("\n".join(json.dumps(l) for l in linhas) + "\nlixo\n", encoding="utf-8")
    assert cli.main(["origem", "relatorio", "--log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "3 no total" in out and "Instagram" in out and "1  (33%)" in out


def test_cli_numero_invalido(capsys):
    assert cli.main(["origem", "links", "--numero", "123"]) == 2
    assert "inválido" in capsys.readouterr().out
