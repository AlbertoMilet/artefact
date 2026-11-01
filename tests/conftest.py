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
