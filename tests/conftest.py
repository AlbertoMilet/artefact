from pathlib import Path

import pytest

from emporio.data import carregar

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def catalogo():
    return carregar(RAIZ / "data")


@pytest.fixture(autouse=True)
def sem_env_real(request, monkeypatch):
    """Testes padrão não leem o .env do usuário (resultado não depende dele); só os @llm precisam da chave."""
    if request.node.get_closest_marker("llm") is None:
        monkeypatch.setattr("emporio.config.load_dotenv", lambda *a, **k: None)
        monkeypatch.setattr("emporio.cli_whatsapp.load_dotenv", lambda *a, **k: None)


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
def atendimento_isolado(monkeypatch, tmp_path):
    """Testes não leem nem gravam o histórico real do painel de atendimento."""
    monkeypatch.setenv("EMPORIO_DB", str(tmp_path / "atendimento.db"))
    monkeypatch.setenv("EMPORIO_DB_DEMO", str(tmp_path / "demo.db"))
    monkeypatch.setenv("EMPORIO_LOG_TURNOS", str(tmp_path / "emporio.jsonl"))
    monkeypatch.setenv("EMPORIO_LOG_AVISOS", str(tmp_path / "avisos.log"))
    monkeypatch.delenv("EMPORIO_CHAVE_TELEFONE", raising=False)
    monkeypatch.delenv("EMPORIO_USUARIOS", raising=False)
    monkeypatch.delenv("EMPORIO_SEGREDO_SESSAO", raising=False)


@pytest.fixture(autouse=True)
def whatsapp_isolado(monkeypatch, tmp_path):
    """Testes não leem nem gravam a conexão real do WhatsApp nem usam a chave real."""
    monkeypatch.setenv("WHATSAPP_CONEXAO", str(tmp_path / "whatsapp.json"))
    monkeypatch.delenv("WHATSAPP_CHAVE_CIFRA", raising=False)
