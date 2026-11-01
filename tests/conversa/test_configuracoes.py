"""Configurações no painel (SPEC-009): modelo, persona, WhatsApp simulado, origem e retenção. Sem rede."""

import json
from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from emporio import preferencias
from emporio.agent.persona import Persona
from emporio.agent.prompt import montar_prompt
from emporio.config import Config, montar_agente
from emporio.rules.horario import FUSO
from emporio.web import criar_app
from emporio.web.auth import hash_senha
from emporio.web.repositorio import Repositorio
from emporio.whatsapp import conexao as arq

USUARIOS = {"carlos": hash_senha("senha-forte-1", iteracoes=1000)}


@pytest.fixture
def painel(tmp_path):
    config = replace(Config(), llm_provider="fake", tickets_path=tmp_path / "t.jsonl")
    app = criar_app(montar_agente(config), config, Repositorio(tmp_path / "a.db"), usuarios=USUARIOS)
    c = TestClient(app)
    c.post("/login", data={"usuario": "carlos", "senha": "senha-forte-1"})
    return c


# ---------------------------------------------------------------- persona no prompt

def test_persona_padrao_reproduz_o_prompt_avaliado():
    agora = datetime(2026, 3, 25, 10, 0, tzinfo=FUSO)
    p = montar_prompt(agora)
    assert "Você é a Lia, assistente virtual" in p and "como uma amiga que entende de música" in p
    assert "No máximo um emoji por mensagem" in p and "Preferências da loja" not in p
    assert montar_prompt(agora, Persona()) == p


def test_persona_personalizada_muda_so_identidade_e_tom():
    p = montar_prompt(datetime(2026, 3, 25, 10, 0, tzinfo=FUSO), Persona.de_dict(
        {"nome": "Rafa", "tratamento": "masculino", "tom": "profissional", "emojis": False,
         "instrucoes": "Pergunte se o cliente é iniciante."}))
    assert "Você é o Rafa" in p and "cordial e profissional" in p and "Não use emojis." in p
    assert p.index("# Regras invioláveis") < p.index("# Preferências da loja")      # regras vêm antes
    assert "Nunca calcule, estime ou arredonde valores" in p                        # regras intactas


@pytest.mark.parametrize("dados", [{"nome": ""}, {"nome": "x" * 31}, {"nome": "Lia<script>"}, {"tom": "agressivo"},
                                   {"tratamento": "outro"}, {"instrucoes": "a" * 601}, {"emojis": "sim"}])
def test_persona_invalida(dados):
    with pytest.raises(ValueError):
        Persona.de_dict(dados)


# ---------------------------------------------------------------- telas

def test_abas_e_navegacao(painel):
    assert painel.get("/configuracoes", follow_redirects=False).headers["location"] == "/configuracoes/modelo"
    for aba, texto in [("modelo", "DeepSeek V4.1 Flash"), ("persona", "Nome do agente"), ("whatsapp", "Login com Facebook"),
                       ("origem", "Copiar link"), ("retencao", "Horário silencioso")]:
        r = painel.get(f"/configuracoes/{aba}")
        assert r.status_code == 200 and texto in r.text, aba
    assert "sk-or" not in painel.get("/configuracoes/modelo").text


def test_configuracoes_exigem_login(tmp_path):
    config = replace(Config(), llm_provider="fake", tickets_path=tmp_path / "t.jsonl")
    c = TestClient(criar_app(montar_agente(config), config, Repositorio(tmp_path / "a.db"), usuarios=USUARIOS))
    assert c.get("/configuracoes/persona", follow_redirects=False).status_code == 303


def test_salvar_modelo_grava_preferencias_e_aplica(painel):
    r = painel.post("/configuracoes/modelo", data={"modelo": "haiku", "raciocinio": "on",
                                                   "data_referencia": "2026-03-25T10:00"})
    assert "Configuração salva" in r.text
    prefs = json.loads(preferencias.caminho().read_text(encoding="utf-8"))
    assert prefs["modelo"] == "anthropic/claude-haiku-5.5" and prefs["raciocinio"] is True
    assert "25/03/2026 10:00" in painel.get("/simulador").text
    erro = painel.post("/configuracoes/modelo", data={"modelo": "outro", "outro": "sem-barra"})
    assert "modelo desconhecido" in erro.text
    assert json.loads(preferencias.caminho().read_text(encoding="utf-8"))["modelo"] == "anthropic/claude-haiku-5.5"


def test_salvar_persona_vale_na_proxima_mensagem(painel):
    r = painel.post("/configuracoes/persona", data={"nome": "Rafa", "tratamento": "masculino", "tom": "profissional",
                                                    "instrucoes": "Seja breve."})
    assert "Persona salva" in r.text and "Você é o Rafa" in r.text
    t = painel.post("/simulador/mensagem", data={"texto": "Estão abertos agora?"}, headers={"HX-Request": "true"}).text
    assert "Rafa" in t                                                                # rótulo do agente nas telas
    assert "nome da persona" in painel.post("/configuracoes/persona", data={"nome": "1abc"}).text
    painel.post("/configuracoes/persona", data={"acao": "padrao"})
    assert json.loads(preferencias.caminho().read_text(encoding="utf-8"))["persona"]["nome"] == "Lia"


def test_whatsapp_simulado_passo_a_passo(painel):
    passos = [("login", {}, "Login com Facebook concluído"),
              ("numero", {"numero": "(67) 99999-0000", "nome": "Empório da Música"}, "Número definido"),
              ("enviar-codigo", {"metodo": "SMS"}, "o SMS diria"),
              ("confirmar-codigo", {"codigo": "000000"}, "incorreto"),
              ("confirmar-codigo", {"codigo": "123456"}, "Número confirmado"),
              ("registrar", {"pin": "654321"}, "Número registrado"),
              ("assinar", {}, "Número registrado e app assinado")]
    for acao, dados, esperado in passos:
        r = painel.post(f"/configuracoes/whatsapp/{acao}", data={"modo": "simulado", **dados})
        assert esperado in r.text, acao
    salvo = arq.caminho(simulado=True).read_text(encoding="utf-8")
    assert "654321" not in salvo                                                      # PIN não é guardado
    assert "Conexão apagada" in painel.post("/configuracoes/whatsapp/desconectar", data={"modo": "simulado"}).text
    assert not arq.caminho(simulado=True).exists()


def test_whatsapp_real_sem_credenciais_cai_no_simulado(painel, monkeypatch):
    monkeypatch.delenv("META_APP_ID", raising=False)
    r = painel.get("/configuracoes/whatsapp", params={"modo": "real"})
    assert "META_APP_ID" in r.text and "(simulado)" in r.text


def test_origem_links_e_contagem(painel):
    painel.post("/simulador/mensagem", data={"texto": "Olá! Quero mais informações 📸"})
    r = painel.get("/configuracoes/origem")
    assert r.text.count('data-copiar="https://wa.me/556733414444?text=') == 4 and "Conversas por origem (1)" in r.text
    assert "inválido" in painel.get("/configuracoes/origem", params={"numero": "12"}).text
