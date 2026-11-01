"""CLI `python -m emporio whatsapp` no modo simulado (SPEC-004)."""

import pytest

from emporio import cli, cli_whatsapp
from emporio.whatsapp import conexao as arq
from emporio.whatsapp.simulado import ProvedorSimulado


@pytest.fixture
def sem_env(monkeypatch):
    monkeypatch.setattr(cli_whatsapp, "load_dotenv", lambda *a, **k: None)


def test_conectar_simulado_completo(sem_env, monkeypatch, capsys):
    prov = ProvedorSimulado(codigo_fixo="482913")
    monkeypatch.setattr(cli_whatsapp, "provedor", lambda simulado: prov)
    entradas = iter(["n", "(67) 99999-0000", "Empório da Música", "000000", "482913"])
    monkeypatch.setattr("builtins.input", lambda _="": next(entradas))
    monkeypatch.setattr("getpass.getpass", lambda _="": "123456")
    assert cli.main(["whatsapp", "conectar", "--simulado"]) == 0
    out = capsys.readouterr().out
    assert "Código de confirmação enviado por SMS para +55 67999990000" in out
    assert "(simulado: o SMS diria 482913)" in out
    assert "código de verificação incorreto" in out                       # primeira tentativa errada
    assert "WhatsApp da loja conectado." in out and "Etapa: conectado" in out
    assert arq.carregar().etapa.value == "conectado"


def test_interrompido_salva_a_etapa(sem_env, monkeypatch, capsys):
    prov = ProvedorSimulado(codigo_fixo="482913")
    monkeypatch.setattr(cli_whatsapp, "provedor", lambda simulado: prov)
    entradas = iter(["1"])

    def entrada(_=""):
        try:
            return next(entradas)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr("builtins.input", entrada)
    assert cli.main(["whatsapp", "conectar", "--simulado"]) == 1
    assert "Etapa salva: codigo_enviado" in capsys.readouterr().out
    cli.main(["whatsapp", "status"])
    out = capsys.readouterr().out
    assert "Etapa: codigo_enviado" in out and "digitar o código" in out


def test_gerar_chave_e_desconectar(sem_env, capsys):
    cli.main(["whatsapp", "gerar-chave"])
    assert "WHATSAPP_CHAVE_CIFRA=" in capsys.readouterr().out
    cli.main(["whatsapp", "desconectar"])
    assert "Não havia conexão salva." in capsys.readouterr().out


def test_modo_real_sem_credenciais_explica(sem_env, monkeypatch, capsys):
    monkeypatch.delenv("META_APP_ID", raising=False)
    monkeypatch.delenv("META_APP_SECRET", raising=False)
    assert cli.main(["whatsapp", "conectar"]) == 2
    assert "META_APP_ID" in capsys.readouterr().out
