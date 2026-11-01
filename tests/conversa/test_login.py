"""Login do painel (SPEC-008): usuários do .env com hash, cookie assinado, limite de tentativas."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from emporio import cli
from emporio.config import Config, montar_agente
from emporio.web import criar_app
from emporio.web.auth import Limitador, Sessoes, carregar_usuarios, conferir_senha, hash_senha
from emporio.web.repositorio import Repositorio

HASH = hash_senha("senha-forte-1", iteracoes=1000)


def app(tmp_path, usuarios=None, sessoes=None):
    config = replace(Config(), llm_provider="fake", tickets_path=tmp_path / "t.jsonl")
    return criar_app(montar_agente(config), config, Repositorio(tmp_path / "a.db"),
                     usuarios={"carlos": HASH} if usuarios is None else usuarios, sessoes=sessoes)


def test_hash_e_conferencia():
    assert HASH.startswith("pbkdf2_sha256$1000$") and "senha-forte-1" not in HASH
    assert conferir_senha("senha-forte-1", HASH) and not conferir_senha("senha-errada", HASH)
    assert hash_senha("senha-forte-1", iteracoes=1000) != HASH                    # sal aleatório
    assert not conferir_senha("x", "lixo")
    with pytest.raises(ValueError, match="8 caracteres"):
        hash_senha("curta")


def test_usuarios_do_env():
    assert carregar_usuarios(f"carlos:{HASH}, ana@loja:{HASH}") == {"carlos": HASH, "ana@loja": HASH}
    assert carregar_usuarios("") == {}
    for ruim in ("carlos:senha-em-claro", "x:" + HASH, f"carlos{HASH}"):
        with pytest.raises(ValueError, match="EMPORIO_USUARIOS"):
            carregar_usuarios(ruim)


def test_sessao_assinada_e_com_validade():
    agora = [1000.0]
    s = Sessoes(b"s" * 32, duracao_s=60, relogio=lambda: agora[0])
    token = s.emitir("carlos")
    assert s.validar(token) == "carlos"
    _, exp, ass = token.split(".")
    assert s.validar(f"YW5h.{exp}.{ass}") is None                                  # trocar o usuário invalida
    assert Sessoes(b"o" * 32).validar(token) is None                               # outro segredo
    assert s.validar("lixo") is None
    agora[0] += 61
    assert s.validar(token) is None                                                # expirou


def test_tudo_exige_login_menos_login_e_estaticos(tmp_path):
    c = TestClient(app(tmp_path))
    for caminho in ("/", "/atendimento", "/simulador", "/atendimento/lista"):
        r = c.get(caminho, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/login")
    assert c.post("/simulador/mensagem", data={"texto": "oi"}, follow_redirects=False).status_code == 303
    hx = c.get("/atendimento/lista", headers={"HX-Request": "true"})
    assert hx.status_code == 401 and hx.headers["HX-Redirect"] == "/login"
    assert c.get("/login").status_code == 200 and c.get("/static/app.css").status_code == 200


def test_entrar_sair_e_voltar_para_a_pagina_pedida(tmp_path):
    c = TestClient(app(tmp_path))
    r = c.post("/login", data={"usuario": "carlos", "senha": "senha-forte-1", "proximo": "/simulador"},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/simulador"
    assert "carlos" in c.get("/atendimento").text
    c.post("/sair")
    assert c.get("/atendimento", follow_redirects=False).status_code == 303


def test_redirecionamento_aberto_bloqueado(tmp_path):
    c = TestClient(app(tmp_path))
    r = c.post("/login", data={"usuario": "carlos", "senha": "senha-forte-1", "proximo": "//malicioso.com"},
               follow_redirects=False)
    assert r.headers["location"] == "/atendimento"


def test_senha_errada_e_limite_de_tentativas(tmp_path):
    c = TestClient(app(tmp_path))
    for _ in range(5):
        assert "incorretos" in c.post("/login", data={"usuario": "carlos", "senha": "errada"}).text
    r = c.post("/login", data={"usuario": "carlos", "senha": "senha-forte-1"})
    assert "Muitas tentativas" in r.text and "Sair" not in r.text


def test_limitador_libera_depois_do_bloqueio():
    agora = [0.0]
    lim = Limitador(relogio=lambda: agora[0])
    for _ in range(5):
        lim.falhou("ip")
    assert lim.bloqueado("ip") > 0
    agora[0] += 61
    assert lim.bloqueado("ip") == 0


def test_usuario_removido_do_env_perde_a_sessao(tmp_path):
    sessoes = Sessoes(b"s" * 32)
    c = TestClient(app(tmp_path, sessoes=sessoes))
    c.post("/login", data={"usuario": "carlos", "senha": "senha-forte-1"})
    c2 = TestClient(app(tmp_path, usuarios={"ana": HASH}, sessoes=sessoes))
    c2.cookies = c.cookies
    assert c2.get("/atendimento", follow_redirects=False).status_code == 303


def test_modo_demo_sem_usuarios_mostra_o_acesso_demo(tmp_path):
    c = TestClient(app(tmp_path, usuarios={}))
    assert "demo1234" in c.get("/login").text
    r = c.post("/login", data={"usuario": "demo", "senha": "demo1234"})
    assert r.status_code == 200 and "Sair" in r.text


def test_cli_segredo_e_criar(monkeypatch, capsys):
    assert cli.main(["usuario", "segredo"]) == 0
    assert len(capsys.readouterr().out.split("EMPORIO_SEGREDO_SESSAO=")[1].strip()) == 64
    senhas = iter(["senha-forte-1", "senha-forte-1"])
    monkeypatch.setattr("getpass.getpass", lambda _="": next(senhas))
    assert cli.main(["usuario", "criar", "carlos"]) == 0
    linha = [x for x in capsys.readouterr().out.splitlines() if x.startswith("EMPORIO_USUARIOS=")][0]
    nome, guardado = linha.split("=", 1)[1].split(":", 1)
    assert nome == "carlos" and conferir_senha("senha-forte-1", guardado) and "senha-forte-1" not in linha
