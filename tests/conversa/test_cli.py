"""CLI em modo demonstração (Fase 4): roda sem chave e sem rede."""

import pytest

from emporio import cli


@pytest.fixture(autouse=True)
def sem_ambiente(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "RAIZ", tmp_path)                     # logs em pasta temporária
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("TICKETS_PATH", str(tmp_path / "tickets.jsonl"))


def test_mensagens_nao_interativas_com_debug(capsys):
    assert cli.main(["chat", "--fake", "--debug", "-m", "Quanto custa o Takamine GD20?"]) == 0
    out = capsys.readouterr().out
    assert "│ tool    buscar_produtos" in out
    assert "R$ 2.089,05" in out
    assert "♪ Lia ›" in out


def test_debug_mascara_telefone(capsys):
    cli.main(["chat", "--fake", "--debug", "-m", "pedido 8, telefone (67) 99654-7821"])
    out = capsys.readouterr().out
    assert "│ tool    consultar_pedido" in out and "BRJL5544332BR" in out
    linhas_rastro = [l for l in out.splitlines() if "│" in l]
    assert all("99654-7821" not in l for l in linhas_rastro)


def test_interativo_novo_e_sair(monkeypatch, capsys):
    entradas = iter(["qual o endereço?", "/novo", "", "/sair"])
    monkeypatch.setattr("builtins.input", lambda _: next(entradas))
    assert cli.main(["chat", "--fake"]) == 0
    out = capsys.readouterr().out
    assert "14 de Maio" in out and "(nova conversa)" in out


def test_fim_de_entrada_encerra(monkeypatch):
    def eof(_):
        raise EOFError
    monkeypatch.setattr("builtins.input", eof)
    assert cli.main(["chat", "--fake"]) == 0


def test_sem_chave_orienta_o_modo_demonstracao(monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setattr("emporio.config.load_dotenv", lambda *a, **k: None)
    assert cli.main(["chat", "-m", "oi"]) == 2
    assert "--fake" in capsys.readouterr().err


def test_demo_entende_pergunta_com_palavras_de_pergunta(capsys):
    cli.main(["chat", "--fake", "-m", "Quais opções de violões disponíveis custando até R$1000?"])
    out = capsys.readouterr().out
    assert "Encontrei:" in out and "Yamaha C40" in out and "Takamine GD20" not in out


def test_recuo_deixa_uma_coluna_livre():
    from emporio.visual import RECUO, recuar
    linhas = recuar("palavra " * 40, largura=60).split("\n")
    assert all(len(l) <= 59 for l in linhas) and all(l.startswith(RECUO) for l in linhas[1:])
