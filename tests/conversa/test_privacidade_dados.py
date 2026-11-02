"""LGPD no atendimento (SPEC-012): expurgo por prazo, exclusão e exportação de uma conversa, auditoria. Sem rede."""

import json
import sqlite3
from datetime import datetime

from emporio import privacidade
from emporio.cli import main as cli_main
from emporio.rules.horario import FUSO
from emporio.web.repositorio import Repositorio

AGORA = datetime(2026, 11, 2, 10, 0, tzinfo=FUSO)


def repo_com_relogio(caminho, momento):
    return Repositorio(caminho, relogio=lambda: momento)


def _jsonl(arquivo, itens):
    arquivo.write_text("".join(json.dumps(i) + "\n" for i in itens), encoding="utf-8")


def _conversas(arquivo):
    return [json.loads(x)["conversa"] for x in arquivo.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_expurgo_apaga_conversas_e_logs_vencidos(tmp_path):                  # CL-01, RL-01, RL-02
    banco = tmp_path / "atendimento.db"
    velha = repo_com_relogio(banco, datetime(2026, 8, 3, 9, 0, tzinfo=FUSO))     # 91 dias antes de AGORA
    cid_velha = velha.conversa_do_telefone("(67) 98888-0001").id
    velha.adicionar(cid_velha, "cliente", "oi")
    recente = repo_com_relogio(banco, datetime(2026, 8, 5, 9, 0, tzinfo=FUSO))   # 89 dias
    cid_recente = recente.conversa_do_telefone("(67) 98888-0002").id
    log, fila = tmp_path / "emporio.jsonl", tmp_path / "alertas.jsonl"
    _jsonl(log, [{"conversa": cid_velha, "registrado_em": "2026-08-03T09:00:00-04:00"},
                 {"conversa": cid_recente, "registrado_em": "2026-08-05T09:00:00-04:00"},
                 {"conversa": "antiga"}])                                       # sem data: gravada antes da spec
    _jsonl(fila, [{"conversa": cid_recente, "registrado_em": "2026-10-30T09:00:00-04:00"}])

    (tmp_path / "avisos.log").write_text(
        "2026-07-01 10:00:00,123 ERROR emporio.tools: falha antiga\nTraceback (most recent call last):\n  x\n"
        "2026-10-30 10:00:00,001 ERROR emporio.tools: falha recente\n", encoding="utf-8")
    velha.auditar("carlos", "abriu", cid_velha)                                  # 91 dias: dentro dos 365

    r = privacidade.expurgar(Repositorio(banco), AGORA)

    assert {k: r[k] for k in ("mensagens", "conversas", "linhas_de_log", "auditoria")} == \
        {"mensagens": 1, "conversas": 1, "linhas_de_log": 5, "auditoria": 0}
    assert r["afetadas"] == [cid_velha]
    assert [c.id for c in Repositorio(banco).listar()] == [cid_recente]
    assert _conversas(log) == [cid_recente] and _conversas(fila) == [cid_recente]
    assert (tmp_path / "avisos.log").read_text(encoding="utf-8") == "2026-10-30 10:00:00,001 ERROR emporio.tools: falha recente\n"
    assert "oi" not in "\n".join(sqlite3.connect(banco).iterdump())
    assert len(Repositorio(banco).auditoria()) == 1


def test_prazo_vale_por_mensagem_numa_conversa_ativa(tmp_path):               # RL-01
    banco = tmp_path / "atendimento.db"
    antes = repo_com_relogio(banco, datetime(2026, 7, 1, 9, 0, tzinfo=FUSO))
    cid = antes.conversa_do_telefone("(67) 98888-0001").id
    antes.adicionar(cid, "cliente", "mensagem antiga")
    repo_com_relogio(banco, datetime(2026, 11, 1, 9, 0, tzinfo=FUSO)).adicionar(cid, "cliente", "mensagem nova")
    r = privacidade.expurgar(Repositorio(banco), AGORA)
    assert (r["mensagens"], r["conversas"], r["afetadas"]) == (1, 0, [cid])
    assert [m.texto for m in Repositorio(banco).mensagens(cid)] == ["mensagem nova"]


def test_auditoria_expira_em_365_dias(tmp_path):                              # RL-11
    banco = tmp_path / "atendimento.db"
    repo_com_relogio(banco, datetime(2025, 10, 1, 9, 0, tzinfo=FUSO)).auditar("carlos", "abriu", "x")
    repo_com_relogio(banco, datetime(2026, 1, 1, 9, 0, tzinfo=FUSO)).auditar("carlos", "abriu", "y")
    assert privacidade.expurgar(Repositorio(banco), AGORA)["auditoria"] == 1
    assert [a["conversa_id"] for a in Repositorio(banco).auditoria()] == ["y"]


def test_avisos_log_grava_mascarado(tmp_path):
    import logging
    registro = logging.LogRecord("emporio.tools", logging.ERROR, __file__, 1,
                                 "falha com %s", ("telefone (67) 99654-7821 e CPF 123.456.789-09",), None)
    texto = privacidade.FormatoMascarado("%(message)s").format(registro)
    assert texto == "falha com telefone (67) 9****-7821 e CPF ***.***.***-09"


def test_apagar_conversa_remove_banco_e_logs_e_audita(tmp_path):             # CL-04, RL-05, RL-09
    banco = tmp_path / "atendimento.db"
    repo = Repositorio(banco)
    a = repo.conversa_do_telefone("(67) 98888-0001").id
    b = repo.conversa_do_telefone("(67) 98888-0002").id
    repo.adicionar(a, "cliente", "meu CEP é 79002-100")
    agora = datetime.now(FUSO).isoformat(timespec="seconds")
    _jsonl(tmp_path / "emporio.jsonl", [{"conversa": a, "registrado_em": agora}, {"conversa": b, "registrado_em": agora}])

    privacidade.apagar_conversa(repo, a, "carlos")

    assert repo.conversa(a) is None and repo.conversa(b) is not None and repo.mensagens(a) == []
    assert _conversas(tmp_path / "emporio.jsonl") == [b]
    assert [(x["usuario"], x["acao"], x["conversa_id"]) for x in repo.auditoria()] == [("carlos", "apagou", a)]


def test_exportar_sem_hmac_do_telefone(tmp_path):                            # CL-04, RL-06
    repo = Repositorio(tmp_path / "atendimento.db")
    conv = repo.conversa_do_telefone("(67) 98888-0001")
    repo.adicionar(conv.id, "cliente", "meu CPF é 123.456.789-09")
    dados = repo.exportar(conv.id)
    texto = json.dumps(dados, ensure_ascii=False)
    assert dados["conversa"]["telefone"] == "(67) 9****-0001"
    assert [m["texto"] for m in dados["mensagens"]] == ["meu CPF é ***.***.***-09"]    # gravado já mascarado
    assert "chave" not in texto and "98888-0001" not in texto
    assert repo.exportar("nao-existe") is None


def test_comando_expurgar(tmp_path, capsys):
    assert cli_main(["privacidade", "expurgar"]) == 0
    assert "Expurgo (90 dias): 0 mensagem(ns), 0 conversa(s)" in capsys.readouterr().out
