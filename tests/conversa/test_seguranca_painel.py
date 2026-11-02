"""Segurança do painel (SPEC-013): CSRF e origem, cabeçalhos, sessão, limites, modo demonstração. Sem rede."""

from dataclasses import replace

from fastapi.testclient import TestClient

import emporio.web.app as modulo_app
from emporio import cli_web
from emporio.config import Config, montar_agente
from emporio.web import criar_app
from emporio.web.app import RESPOSTA_LIMITE
from emporio.web.auth import Sessoes, hash_senha
from emporio.web.repositorio import Repositorio
from tests.apoio import com_csrf

HASH = hash_senha("senha-forte-1", iteracoes=1000)


def app(tmp_path, usuarios=None, sessoes=None):
    config = replace(Config(), llm_provider="fake", tickets_path=tmp_path / "t.jsonl")
    return criar_app(montar_agente(config), config, Repositorio(tmp_path / "a.db"),
                     usuarios={"carlos": HASH} if usuarios is None else usuarios, sessoes=sessoes)


def logado(tmp_path, **kw):
    c = TestClient(app(tmp_path, **kw))
    c.post("/login", data={"usuario": "carlos", "senha": "senha-forte-1"})
    return c


def test_post_sem_token_ou_de_outra_origem_e_recusado(tmp_path):              # CS-02, RS-03
    c = logado(tmp_path)
    assert c.post("/simulador/mensagem", data={"texto": "oi"}).status_code == 403          # sem token
    com_csrf(c)
    assert c.post("/simulador/mensagem", data={"texto": "oi"}).status_code == 200
    outra = {"Origin": "http://localhost:3000"}
    assert c.post("/simulador/mensagem", data={"texto": "oi"}, headers=outra).status_code == 403
    assert c.post("/simulador/mensagem", data={"texto": "oi"}, headers={"Origin": "null"}).status_code == 403
    assert c.post("/simulador/mensagem", data={"texto": "oi"},
                  headers={"Origin": "http://testserver"}).status_code == 200
    token = c.headers.pop("X-CSRF-Token")
    assert c.post("/simulador/mensagem", data={"texto": "oi", "csrf": token}).status_code == 200   # campo do form
    login_de_fora = TestClient(app(tmp_path)).post("/login", headers=outra,
                                                   data={"usuario": "carlos", "senha": "senha-forte-1"})
    assert login_de_fora.status_code == 403


def test_cabecalhos_de_seguranca_e_nada_de_fora(tmp_path):                   # CS-03
    c = logado(tmp_path)
    for caminho in ("/login", "/atendimento", "/simulador"):
        r = c.get(caminho)
        csp = r.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in csp and "script-src 'self' 'nonce-" in csp
        assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"
        assert "https://" not in r.text.split("<main")[0]                         # nada de CDN no <head>
        nonce = csp.split("'nonce-")[1].split("'")[0]
        assert r.text.count("<script") == r.text.count(f'nonce="{nonce}"')        # todo script com o nonce
    assert c.get("/atendimento", follow_redirects=False).headers["cache-control"] == "no-store"
    anonimo = TestClient(app(tmp_path)).get("/atendimento", follow_redirects=False)
    assert anonimo.status_code == 303 and anonimo.headers["x-frame-options"] == "DENY"


def test_trocar_a_senha_derruba_a_sessao(tmp_path):                          # CS-04, RS-04
    c = logado(tmp_path, sessoes=Sessoes(b"s" * 32))
    assert c.get("/atendimento", follow_redirects=False).status_code == 200
    nova = TestClient(app(tmp_path, usuarios={"carlos": hash_senha("outra-senha-9", iteracoes=1000)},
                          sessoes=Sessoes(b"s" * 32)))
    nova.cookies = c.cookies
    assert nova.get("/atendimento", follow_redirects=False).status_code == 303


def test_login_com_usuario_inexistente_gasta_o_mesmo_pbkdf2(tmp_path, monkeypatch):   # RS-07
    chamadas = []
    original = modulo_app.conferir_senha
    monkeypatch.setattr(modulo_app, "conferir_senha", lambda s, g: chamadas.append(g) or original(s, g))
    c = TestClient(app(tmp_path))
    c.post("/login", data={"usuario": "ninguem", "senha": "qualquer-coisa"})
    c.post("/login", data={"usuario": "carlos", "senha": "errada-123"})
    assert len(chamadas) == 2 and chamadas[0].startswith("pbkdf2_sha256$1000$")     # hash falso, mesmo custo
    assert chamadas[0] != HASH


def test_bloqueio_de_login_tambem_por_usuario(tmp_path):                     # RS-07
    painel = app(tmp_path)
    c = TestClient(painel)
    for _ in range(5):
        c.post("/login", data={"usuario": "carlos", "senha": "errada-123"})
    de_outro_endereco = TestClient(painel, client=("10.0.0.9", 50000))
    r = de_outro_endereco.post("/login", data={"usuario": "carlos", "senha": "senha-forte-1"})
    assert "Muitas tentativas" in r.text                                            # o usuário está bloqueado
    r = de_outro_endereco.post("/login", data={"usuario": "ana", "senha": "senha-forte-1"})
    assert "Muitas tentativas" not in r.text                                        # o endereço novo não


def test_limite_de_mensagens_por_conversa(tmp_path):                          # CS-05, RS-05
    c = com_csrf(logado(tmp_path))
    for i in range(10):
        c.post("/simulador/mensagem", data={"texto": f"oi {i}"})
    c.post("/simulador/mensagem", data={"texto": "a de número 11"})
    repo = Repositorio(tmp_path / "a.db")
    [conv] = repo.listar()
    ultima = repo.mensagens(conv.id)[-1]
    assert ultima.autor == "lia" and ultima.texto == RESPOSTA_LIMITE and ultima.detalhes == {"limite": True}
    assert sum(1 for m in repo.mensagens(conv.id) if m.autor == "cliente") == 11       # a mensagem fica guardada


def test_modo_demonstracao_usa_banco_proprio(tmp_path):                       # CS-01, RS-01
    config = replace(Config(), llm_provider="fake", tickets_path=tmp_path / "t.jsonl")
    c = TestClient(criar_app(montar_agente(config), config, usuarios={}))
    c.post("/login", data={"usuario": "demo", "senha": "demo1234"})
    com_csrf(c).post("/simulador/mensagem", data={"texto": "oi"})
    assert Repositorio(tmp_path / "demo.db").listar() and not (tmp_path / "atendimento.db").exists()


def test_ui_recusa_rede_sem_https_e_demo_fora_do_loopback(capsys):          # RS-02
    assert cli_web.main(["--host", "0.0.0.0", "--sem-navegador"]) == 2
    assert "--https-proxy" in capsys.readouterr().err
    assert cli_web.main(["--fake", "--host", "0.0.0.0", "--https-proxy", "--sem-navegador"]) == 2
    assert "só vale neste computador" in capsys.readouterr().err
