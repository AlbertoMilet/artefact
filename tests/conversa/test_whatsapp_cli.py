"""CLI `python -m emporio whatsapp` no modo simulado (SPEC-004)."""

import pytest

from emporio import cli, cli_whatsapp
from emporio.whatsapp import conexao as arq
from emporio.whatsapp.meta import ErroMeta
from emporio.whatsapp.simulado import ProvedorSimulado


@pytest.fixture
def sem_env(monkeypatch):
    monkeypatch.setattr(cli_whatsapp, "load_dotenv", lambda *a, **k: None)


def entradas(monkeypatch, valores, pin="123456"):
    it = iter(valores)

    def entrada(_=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr("builtins.input", entrada)
    monkeypatch.setattr("getpass.getpass", lambda _="": pin)


def test_conectar_simulado_completo(sem_env, monkeypatch, capsys):
    entradas(monkeypatch, ["n", "(67) 99999-0000", "Empório da Música", "000000", "123456"])
    assert cli.main(["whatsapp", "conectar", "--simulado"]) == 0
    out = capsys.readouterr().out
    assert "Código de confirmação enviado por SMS para +55 67999990000" in out
    assert "(simulado: o SMS diria 123456)" in out
    assert "código de verificação incorreto" in out                       # primeira tentativa errada
    assert "Número registrado e app assinado" in out and "falta o webhook HTTPS" in out
    assert arq.carregar(True).etapa.value == "app_assinado"
    assert not arq.caminho(False).exists()                                # não toca a conexão real


def test_interrompido_e_retomado_em_outra_execucao(sem_env, monkeypatch, capsys):
    entradas(monkeypatch, ["1"])
    assert cli.main(["whatsapp", "conectar", "--simulado"]) == 1
    assert "Etapa salva: codigo_enviado" in capsys.readouterr().out
    cli.main(["whatsapp", "status", "--simulado"])
    assert "Etapa: codigo_enviado (simulado)" in capsys.readouterr().out
    entradas(monkeypatch, ["123456"])                                      # nova execução, provedor novo
    monkeypatch.setenv("WHATSAPP_CHAVE_CIFRA", arq.gerar_chave())
    # sem chave na primeira execução o token não foi salvo: a retomada refaz o login sem perder a etapa
    assert cli.main(["whatsapp", "conectar", "--simulado"]) == 0
    out = capsys.readouterr().out
    assert "Login com Facebook (simulado)" in out and "Número confirmado." in out


def test_erro_em_etapa_automatica_para_em_vez_de_repetir(sem_env, monkeypatch, capsys):
    chamadas = []
    prov = ProvedorSimulado(codigo_fixo="123456", estrito=False)

    def falha(*a):
        chamadas.append(1)
        raise ErroMeta("número bloqueado para verificação", 136024)

    prov.pedir_codigo = falha
    monkeypatch.setattr(cli_whatsapp, "provedor", lambda simulado: prov)
    entradas(monkeypatch, ["1"])
    assert cli.main(["whatsapp", "conectar", "--simulado"]) == 2
    assert len(chamadas) == 1                                              # uma chamada só, sem loop
    assert "Parado na etapa numero_escolhido" in capsys.readouterr().out


def test_gerar_chave_e_desconectar(sem_env, capsys):
    cli.main(["whatsapp", "gerar-chave"])
    assert "WHATSAPP_CHAVE_CIFRA=" in capsys.readouterr().out
    cli.main(["whatsapp", "desconectar", "--simulado"])
    assert "Não havia conexão salva." in capsys.readouterr().out


def test_modo_real_sem_credenciais_explica(sem_env, monkeypatch, capsys):
    monkeypatch.delenv("META_APP_ID", raising=False)
    monkeypatch.delenv("META_APP_SECRET", raising=False)
    assert cli.main(["whatsapp", "conectar"]) == 2
    assert "META_APP_ID" in capsys.readouterr().out


def test_redirect_fora_do_loopback_recusado(sem_env, monkeypatch, capsys):
    monkeypatch.setenv("META_REDIRECT_URI", "http://0.0.0.0:8765/callback")
    assert cli.main(["whatsapp", "conectar"]) == 2
    assert "localhost" in capsys.readouterr().out
