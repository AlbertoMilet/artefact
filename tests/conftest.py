from pathlib import Path

import pytest

from emporio.data import carregar

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def catalogo():
    return carregar(RAIZ / "data")


@pytest.fixture(autouse=True)
def preferencias_isoladas(monkeypatch, tmp_path):
    """Nenhum teste lê ou grava o .emporio.json real do usuário."""
    monkeypatch.setenv("EMPORIO_PREFERENCIAS", str(tmp_path / "prefs.json"))


@pytest.fixture(autouse=True)
def alertas_isolados(monkeypatch, tmp_path):
    """Testes não tocam som nem escrevem na fila real do vendedor."""
    monkeypatch.setenv("ALERTAS_FILA", str(tmp_path / "alertas.jsonl"))
    monkeypatch.setenv("ALERTA_SONORO", "false")


@pytest.fixture(autouse=True)
def whatsapp_isolado(monkeypatch, tmp_path):
    """Testes não leem nem gravam a conexão real do WhatsApp nem usam a chave real."""
    monkeypatch.setenv("WHATSAPP_CONEXAO", str(tmp_path / "whatsapp.json"))
    monkeypatch.delenv("WHATSAPP_CHAVE_CIFRA", raising=False)
