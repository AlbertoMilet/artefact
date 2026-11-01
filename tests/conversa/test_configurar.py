"""Configuração do agente pelo CLI: modelos com ZDR, preferências, precedência, /modelo e /config."""

import json
import os

import pytest

from emporio import cli, cli_config, modelos, preferencias
from emporio.config import Config
from emporio.llm import FakeLLMClient


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "RAIZ", tmp_path)
    monkeypatch.setattr("emporio.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("TICKETS_PATH", str(tmp_path / "tickets.jsonl"))
    for v in ("OPENROUTER_MODEL", "LLM_RACIOCINIO", "RETENCAO_ATIVA", "DATA_REFERENCIA", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(v, raising=False)


def test_tres_opcoes_com_zdr():
    assert [o.apelido for o in modelos.OPCOES] == ["deepseek", "haiku", "gpt-sol"]
    assert [o.slug for o in modelos.OPCOES] == ["deepseek/deepseek-v4.1-flash", "anthropic/claude-haiku-5.5",
                                                "openai/gpt-6.1-sol"]
    assert modelos.PADRAO.apelido == "deepseek"


def test_resolver():
    assert modelos.resolver("haiku") == "anthropic/claude-haiku-5.5"
    assert modelos.resolver("GPT-SOL") == "openai/gpt-6.1-sol"
    assert modelos.resolver("mistralai/mistral-small-2603") == "mistralai/mistral-small-2603"
    assert cli_config.escolher_modelo("3") == "openai/gpt-6.1-sol"
    with pytest.raises(ValueError, match="deepseek, haiku, gpt-sol"):
        modelos.resolver("gpt5")


def test_preferencias_salvar_carregar_e_arquivo_corrompido():
    preferencias.salvar({"modelo": "haiku", "raciocinio": False, "lixo": 1})
    assert preferencias.carregar() == {"modelo": "anthropic/claude-haiku-5.5", "raciocinio": False}
    preferencias.caminho().write_text("{quebrado", encoding="utf-8")
    assert preferencias.carregar() == {}
    assert preferencias.redefinir() is True and preferencias.carregar() == {}


def test_precedencia_env_preferencias(ambiente, monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-haiku-5.5")
    assert Config.do_ambiente().openrouter_model == "anthropic/claude-haiku-5.5"          # .env
    preferencias.salvar({"modelo": "gpt-sol", "retencao": True, "data_referencia": "2026-03-25T10:00"})
    c = Config.do_ambiente()
    assert c.openrouter_model == "openai/gpt-6.1-sol" and c.retencao.ativa                 # preferência vence
    assert c.data_referencia.isoformat().startswith("2026-03-25T10:00")
    assert Config.do_ambiente(usar_preferencias=False).openrouter_model == "anthropic/claude-haiku-5.5"   # evals


def test_configurar_por_flags(ambiente, capsys):
    assert cli.main(["configurar", "--modelo", "haiku", "--raciocinio", "desligado", "--retencao", "ligada",
                     "--data-referencia", "2026-03-25T10:00", "--sem-verificar"]) == 0
    salvo = json.loads(preferencias.caminho().read_text(encoding="utf-8"))
    assert salvo == {"modelo": "anthropic/claude-haiku-5.5", "raciocinio": False, "retencao": True,
                     "data_referencia": "2026-03-25T10:00"}
    out = capsys.readouterr().out
    assert "haiku (Claude Haiku 5.5) (preferência salva)" in out and "Retenção (inatividade): ligada" in out
    cli.main(["configurar", "--data-referencia", "nenhuma"])
    assert "data_referencia" not in json.loads(preferencias.caminho().read_text(encoding="utf-8"))


def test_configurar_valor_invalido(ambiente, capsys):
    assert cli.main(["configurar", "--raciocinio", "talvez"]) == 2
    assert "ligado ou desligado" in capsys.readouterr().out
    assert not preferencias.caminho().exists()


def test_configurar_mostrar_e_redefinir(ambiente, capsys):
    cli.main(["configurar", "--mostrar"])
    out = capsys.readouterr().out
    assert "deepseek (DeepSeek V4.1 Flash)" in out and "sempre com Zero Data Retention" in out
    cli.main(["configurar", "--modelo", "gpt-sol", "--sem-verificar"])
    cli.main(["configurar", "--redefinir"])
    assert "Preferências apagadas." in capsys.readouterr().out


def test_menu_interativo(ambiente, monkeypatch, capsys):
    entradas = iter(["1", "3", "3", "ligada", "9", "5"])
    monkeypatch.setattr("builtins.input", lambda _="": next(entradas))
    assert cli.main(["configurar", "--sem-verificar"]) == 0
    assert preferencias.carregar() == {"modelo": "openai/gpt-6.1-sol", "retencao": True}
    assert "Opção inválida" in capsys.readouterr().out


def test_menu_sair_sem_salvar(ambiente, monkeypatch):
    entradas = iter(["2", "desligado", "0"])
    monkeypatch.setattr("builtins.input", lambda _="": next(entradas))
    cli.main(["configurar"])
    assert not preferencias.caminho().exists()


def test_checar_zdr(monkeypatch):
    monkeypatch.setattr(cli_config, "parametros_zdr", lambda slug: {"tools", "max_tokens"})
    assert "disponível" in cli_config.checar_zdr("x/y")
    monkeypatch.setattr(cli_config, "parametros_zdr", lambda slug: set())
    assert "ATENÇÃO" in cli_config.checar_zdr("x/y")
    monkeypatch.setattr(cli_config, "parametros_zdr", lambda slug: None)
    assert "não foi possível" in cli_config.checar_zdr("x/y")


def test_chat_modelo_e_config_no_modo_demonstracao(ambiente, capsys):
    cli.main(["chat", "--fake", "-m", "/modelo", "-m", "/modelo haiku", "-m", "/config"])
    out = capsys.readouterr().out
    assert "1) deepseek" in out and "3) gpt-sol" in out
    assert "modo demonstração" in out
    assert "Configuração desta conversa" in out


def test_trocar_modelo_durante_a_conversa(catalogo, tmp_path, monkeypatch):
    from emporio.agent import Agente
    from emporio.policies import carregar_manual
    from emporio.retencao import ConfigRetencao, Retencao
    from emporio.tools import Toolbox
    novo = FakeLLMClient([])
    novo.modelo = "anthropic/claude-haiku-5.5"
    novo.suportados = {"tools"}
    monkeypatch.setattr(cli_config, "montar_llm", lambda cfg: novo)
    llm = FakeLLMClient([])
    ag = Agente(llm, Toolbox(catalogo, carregar_manual()), retencao=Retencao(llm, ConfigRetencao()))
    msg = cli_config.comando_modelo(ag, Config(llm_provider="openrouter", openrouter_api_key="sk-teste"), "haiku")
    assert "haiku" in msg and ag.llm is novo and ag.retencao.llm is novo
    cfg = Config(llm_provider="openrouter", openrouter_api_key="sk-teste", openrouter_model="openai/gpt-6.1-sol")
    assert "trocado nesta conversa" in cli_config.comando_config(ag, cfg)


def test_chat_modelo_invalido(ambiente, capsys):
    assert cli.main(["chat", "--fake", "--modelo", "gpt5", "-m", "oi"]) == 2
    assert "deepseek, haiku, gpt-sol" in capsys.readouterr().err
