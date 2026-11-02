"""Interface web (SPEC-006 e SPEC-007): simulador de WhatsApp e painel de atendimento, sem rede."""

import sqlite3
from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from emporio.agent import Agente
from emporio.alertas import CentralAlertas
from emporio.config import Config, montar_agente
from emporio.llm import FakeLLMClient
from emporio.llm.fake import chamar, responder
from emporio.policies import carregar_manual
from emporio.rules.horario import FUSO, relogio_fixo
from emporio.tools import Toolbox
from emporio.web import criar_app
from emporio.web.app import formatar
from emporio.web.auth import hash_senha
from emporio.web.repositorio import Repositorio, chave_do_telefone, hash_antigo
from tests.apoio import com_csrf
from tests.unit.test_alertas import TocadorFalso

HX = {"HX-Request": "true"}
USUARIOS = {"carlos": hash_senha("senha-forte-1", iteracoes=1000)}


def entrar(app) -> TestClient:
    c = TestClient(app)
    assert c.post("/login", data={"usuario": "carlos", "senha": "senha-forte-1"}).status_code == 200
    return com_csrf(c)


@pytest.fixture
def demo(tmp_path):
    config = replace(Config(), llm_provider="fake", tickets_path=tmp_path / "t.jsonl")
    repo = Repositorio(tmp_path / "atendimento.db")
    return entrar(criar_app(montar_agente(config), config, repo, usuarios=USUARIOS)), repo


def test_inicio_vai_para_o_atendimento_e_simulador_tem_roteiro(demo):
    c, _ = demo
    r = c.get("/")
    assert r.status_code == 200 and "Atendimento" in r.text and "Nenhuma conversa ainda" in r.text
    s = c.get("/simulador")
    assert "Simulador de WhatsApp" in s.text and "Roteiro de ensaio" in s.text and "📸 Instagram" in s.text


def test_abrir_o_simulador_nao_cria_conversa(demo):
    c, repo = demo
    c.get("/simulador")
    assert repo.listar() == []


def test_mensagem_do_simulador_vira_conversa_no_painel(demo):
    c, repo = demo
    r = c.post("/simulador/mensagem", data={"texto": "Quanto custa o Takamine GD20?"}, headers=HX)
    assert 'id="painel"' in r.text and "R$ 2.089,05" in r.text and "buscar_produtos" in r.text
    [conv] = repo.listar()
    assert conv.telefone == "(67) 9****-0001" and conv.status == "lia" and conv.total == 2
    painel = c.get("/atendimento/lista").text
    assert "(67) 9****-0001" in painel and "com a Lia" in painel
    assert "R$ 2.089,05" in c.get(f"/atendimento/{conv.id}").text


def test_vendedor_assume_responde_e_devolve(demo):
    c, repo = demo
    c.post("/simulador/mensagem", data={"texto": "Quero falar com um vendedor"}, headers=HX)
    [conv] = repo.listar()
    assert conv.aguardando_vendedor
    assert c.post(f"/atendimento/{conv.id}/responder", data={"texto": "Oi"}).status_code == 409   # sem assumir
    c.post(f"/atendimento/{conv.id}/assumir")
    c.post(f"/atendimento/{conv.id}/responder", data={"texto": "Olá! Sou o Carlos, em que posso ajudar?"})
    r = c.post("/simulador/mensagem", data={"texto": "Quero ver um violão"}, headers=HX)
    assert "Sou o Carlos" in r.text and "Vendedor da loja" in r.text and "está em pausa" in r.text
    autores = [m.autor for m in repo.mensagens(conv.id)]
    assert autores[-3:] == ["sistema", "vendedor", "cliente"]                      # a Lia não respondeu
    c.post(f"/atendimento/{conv.id}/devolver")
    c.post("/simulador/mensagem", data={"texto": "Estão abertos agora?"}, headers=HX)
    assert repo.mensagens(conv.id)[-1].autor == "lia" and repo.conversa(conv.id).status == "lia"


def test_alerta_e_origem_no_painel(catalogo, tmp_path):
    central = CentralAlertas(TocadorFalso(), tmp_path / "alertas.jsonl")
    llm = FakeLLMClient([chamar("info_loja"), responder("Claro, vou chamar alguém da equipe.")])
    agente = Agente(llm, Toolbox(catalogo, carregar_manual(), tickets_path=tmp_path / "t.jsonl"), alertas=central)
    c = entrar(criar_app(agente, Config(), Repositorio(tmp_path / "a.db"), usuarios=USUARIOS))
    c.post("/simulador/mensagem", data={"texto": "Quero falar com um vendedor 📸"}, headers=HX)
    alertas = c.get("/atendimento/alertas").text
    assert "Pediu um vendedor" in alertas and "📸 Instagram" in alertas
    lista = c.get("/atendimento/lista").text
    assert "pediu vendedor" in lista and "📸 Instagram" in lista
    assert "Alerta para o vendedor" not in c.get("/simulador/thread").text           # o cliente não vê o alerta


def test_historico_sobrevive_ao_reinicio_e_telefone_nao_fica_em_claro(tmp_path):
    config = replace(Config(), llm_provider="fake", tickets_path=tmp_path / "t.jsonl")
    banco = tmp_path / "atendimento.db"
    c1 = entrar(criar_app(montar_agente(config), config, Repositorio(banco), usuarios=USUARIOS))
    c1.post("/simulador/mensagem", data={"texto": "pedido 8, telefone (67) 99654-7821"})
    c2 = entrar(criar_app(montar_agente(config), config, Repositorio(banco), usuarios=USUARIOS))  # reiniciou
    [conv] = Repositorio(banco).listar()
    pagina = c2.get(f"/atendimento/{conv.id}").text
    assert "pedido 8" in pagina and "99654-7821" not in pagina
    dump = "\n".join(sqlite3.connect(banco).iterdump())
    chave = (tmp_path / ".chave_telefone").read_text(encoding="utf-8").encode()
    assert "98888-0001" not in dump and "99654-7821" not in dump
    assert chave_do_telefone("(67) 98888-0001", chave) in dump and hash_antigo("(67) 98888-0001") not in dump


def test_trocar_de_cliente_separa_conversas_e_apagar(demo):
    c, repo = demo
    c.post("/simulador/mensagem", data={"texto": "Estão abertos agora?"})
    c.post("/simulador/cliente", data={"telefone": "(81) 97777-0002"})
    c.post("/simulador/mensagem", data={"texto": "Qual o endereço?"})
    assert {x.telefone for x in repo.listar()} == {"(67) 9****-0001", "(81) 9****-0002"}
    c.post("/simulador/apagar")
    assert {x.telefone for x in repo.listar()} == {"(67) 9****-0001"}
    assert "inválido" in c.post("/simulador/cliente", data={"telefone": "123"}).text


def test_html_do_cliente_e_escapado(demo):
    c, _ = demo
    r = c.post("/simulador/mensagem", data={"texto": "<script>alert(1)</script>"}, headers=HX)
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text


def test_conversa_inexistente_404(demo):
    c, _ = demo
    assert c.get("/atendimento/naoexiste").status_code == 404


def test_formatar_markdown_minimo_e_seguro():
    assert formatar("**R$ 10** e _nota_ <b>") == "<strong>R$ 10</strong> e <em>nota</em> &lt;b&gt;"
    assert formatar("protocolo SIM_2026_0001") == "protocolo SIM_2026_0001"


def test_nome_do_perfil_no_simulador_e_no_painel(tmp_path):                  # SPEC-010 CN-04
    config = replace(Config(), llm_provider="fake", tickets_path=tmp_path / "t.jsonl")
    banco = tmp_path / "atendimento.db"
    c1 = entrar(criar_app(montar_agente(config), config, Repositorio(banco), usuarios=USUARIOS))
    pagina = c1.post("/simulador/cliente", data={"telefone": "(67) 98888-0001", "nome": "Carla Souza 🎸"}).text
    assert 'value="Carla Souza 🎸"' in pagina
    c1.post("/simulador/mensagem", data={"texto": "Oi"})
    [conv] = Repositorio(banco).listar()
    assert conv.nome == "Carla"
    c2 = entrar(criar_app(montar_agente(config), config, Repositorio(banco), usuarios=USUARIOS))  # reiniciou
    assert "Carla · (67) 9****-0001" in c2.get("/atendimento").text
    assert "Nome no perfil: Carla" in c2.get(f"/atendimento/{conv.id}").text
    c1.post("/simulador/cliente", data={"telefone": "(67) 98888-0001", "nome": "<script>Loja</script>"})            # perfil sem nome de pessoa
    c1.post("/simulador/mensagem", data={"texto": "oi de novo"})
    assert Repositorio(banco).listar()[0].nome is None


def test_banco_antigo_ganha_a_coluna_do_nome(tmp_path):
    banco = tmp_path / "antigo.db"
    db = sqlite3.connect(banco)
    db.execute("CREATE TABLE conversas (id TEXT PRIMARY KEY, chave_telefone TEXT UNIQUE NOT NULL, "
               "telefone_mascarado TEXT NOT NULL, origem TEXT, status TEXT NOT NULL DEFAULT 'lia', "
               "aguardando_vendedor INTEGER NOT NULL DEFAULT 0, criada_em TEXT NOT NULL, atualizada_em TEXT NOT NULL)")
    db.commit()
    db.close()
    repo = Repositorio(banco)
    conv = repo.conversa_do_telefone("(67) 98888-0001")
    repo.atualizar(conv.id, nome="Ana")
    assert repo.conversa(conv.id).nome == "Ana"


def test_ultima_compra_pelo_numero_do_whatsapp(catalogo, tmp_path):        # SPEC-011 CP-01, CP-04
    tb = Toolbox(catalogo, carregar_manual(), relogio_fixo(datetime(2026, 3, 25, 10, 0, tzinfo=FUSO)),
                 tickets_path=tmp_path / "t.jsonl")
    llm = FakeLLMClient([chamar("meus_pedidos"), responder("Sua última compra foi o pedido 19.")])
    config = replace(Config(), llm_provider="fake", tickets_path=tmp_path / "t.jsonl")
    banco = tmp_path / "a.db"
    c = entrar(criar_app(Agente(llm, tb), config, Repositorio(banco), usuarios=USUARIOS))
    c.post("/simulador/cliente", data={"telefone": "(67) 98432-1098"})
    c.post("/simulador/mensagem", data={"texto": "qual foi minha última compra?"})
    [conv] = Repositorio(banco).listar()
    [lia] = [m for m in Repositorio(banco).mensagens(conv.id) if m.autor == "lia"]
    assert lia.detalhes["rastro"][0]["tool"] == "meus_pedidos" and "22/02/2026" in lia.detalhes["rastro"][0]["resultado"]
    assert "98432-1098" not in "\n".join(sqlite3.connect(banco).iterdump())


def test_painel_mostra_o_nome_do_cadastro(demo):                         # SPEC-011 RP-08
    c, repo = demo
    c.post("/simulador/cliente", data={"telefone": "(67) 98432-1098", "nome": "Apelido"})
    c.post("/simulador/mensagem", data={"texto": "Oi"})
    [conv] = repo.listar()
    assert conv.nome == "Pedro" and "Pedro · (67) 9****-1098" in c.get("/atendimento").text


def test_conversa_com_hash_antigo_migra_para_o_hmac(tmp_path):            # SPEC-012 CL-03
    banco = tmp_path / "a.db"
    repo = Repositorio(banco)
    conv = repo.conversa_do_telefone("(67) 98888-0001")
    db = sqlite3.connect(banco)
    db.execute("UPDATE conversas SET chave_telefone = ? WHERE id = ?", (hash_antigo("(67) 98888-0001"), conv.id))
    db.commit()
    db.close()
    assert repo.conversa_do_telefone("(67) 98888-0001", criar=False).id == conv.id     # achou pelo hash antigo
    chave = (tmp_path / ".chave_telefone").read_text(encoding="utf-8").encode()
    dump = "\n".join(sqlite3.connect(banco).iterdump())
    assert chave_do_telefone("(67) 98888-0001", chave) in dump and hash_antigo("(67) 98888-0001") not in dump


def test_chave_do_telefone_vem_do_ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPORIO_CHAVE_TELEFONE", "segredo-de-teste")
    repo = Repositorio(tmp_path / "a.db")
    conv = repo.conversa_do_telefone("(67) 98888-0001")
    assert not (tmp_path / ".chave_telefone").exists()
    dump = "\n".join(sqlite3.connect(tmp_path / "a.db").iterdump())
    assert chave_do_telefone("(67) 98888-0001", b"segredo-de-teste") in dump and conv.id


def test_painel_exporta_apaga_e_audita(demo):                              # SPEC-012 CL-04, RL-09
    c, repo = demo
    c.post("/simulador/mensagem", data={"texto": "meu CPF é 123.456.789-09"})
    [conv] = repo.listar()
    assert "Exportar dados (JSON)" in c.get(f"/atendimento/{conv.id}").text
    r = c.get(f"/atendimento/{conv.id}/exportar")
    assert r.headers["content-disposition"].startswith("attachment") and r.json()["conversa"]["id"] == conv.id
    assert "***.***.***-09" in r.text and "123.456" not in r.text
    assert c.post(f"/atendimento/{conv.id}/apagar", data={}).status_code == 400      # sem confirmar, nada
    assert repo.conversa(conv.id) is not None
    assert c.post(f"/atendimento/{conv.id}/apagar", data={"confirmar": "sim"}, follow_redirects=False).status_code == 303
    assert repo.conversa(conv.id) is None and repo.listar() == []
    assert [x["acao"] for x in repo.auditoria()] == ["apagou", "exportou", "abriu"]
    assert all(x["usuario"] == "carlos" for x in repo.auditoria())


# ---------------------------------------------------------------- correções da revisão de LGPD (SPEC-012)

def test_simulador_nao_poe_telefone_nem_nome_em_url_ou_cookie(demo):            # RL-13
    c, repo = demo
    r = c.post("/simulador/cliente", data={"telefone": "(67) 98432-1098", "nome": "Ana Paula"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/simulador"
    cookies = "; ".join(f"{k}={v}" for k, v in c.cookies.items())
    assert "98432" not in cookies and "Ana" not in cookies and "emporio_simulador=" in cookies
    pagina = c.get("/simulador").text
    assert 'value="(67) 98432-1098"' in pagina and 'value="Ana Paula"' in pagina      # o servidor lembra
    assert 'method="post" action="/simulador/cliente"' in pagina


def test_apagar_no_simulador_limpa_logs_e_audita(demo, tmp_path):               # RL-05, RL-09
    c, repo = demo
    c.post("/simulador/mensagem", data={"texto": "oi"})
    [conv] = repo.listar()
    (tmp_path / "emporio.jsonl").write_text(
        f'{{"conversa": "{conv.id}", "registrado_em": "2099-01-01T00:00:00-04:00"}}\n', encoding="utf-8")
    c.post("/simulador/apagar")
    assert repo.listar() == [] and (tmp_path / "emporio.jsonl").read_text(encoding="utf-8") == ""
    assert [(a["acao"], a["conversa_id"]) for a in repo.auditoria()] == [("apagou", conv.id)]


def test_leitura_do_historico_e_auditada_sem_depender_de_cabecalho(demo):     # RL-09, SPEC-013 RS-08
    c, repo = demo
    c.post("/simulador/mensagem", data={"texto": "oi"})
    [conv] = repo.listar()
    c.get(f"/atendimento/{conv.id}/thread", headers=HX)          # mesmo com HX-Request: audita
    c.get(f"/atendimento/{conv.id}/thread")                      # dentro de 5 min: não repete
    c.get(f"/atendimento/{conv.id}")
    assert [a["acao"] for a in repo.auditoria()] == ["abriu"]


def test_expurgo_periodico_com_o_painel_no_ar(demo, monkeypatch):               # RL-12
    c, repo = demo
    chamadas = []
    monkeypatch.setattr("emporio.web.app.INTERVALO_EXPURGO_S", -1)
    monkeypatch.setattr("emporio.web.app.privacidade.expurgar",
                        lambda r: chamadas.append(r) or {"afetadas": []})
    c.get("/atendimento")
    assert chamadas == [repo]


def test_midia_no_simulador_guarda_so_o_marcador(demo):                    # SPEC-014 CM-03, RM-02
    c, repo = demo
    assert "📷 Foto" in c.get("/simulador").text
    c.post("/simulador/midia", data={"tipo": "foto"}, headers=HX)
    [conv] = repo.listar()
    msgs = repo.mensagens(conv.id)
    assert [(m.autor, m.texto) for m in msgs][0] == ("cliente", "[cliente enviou uma foto]")
    assert msgs[0].detalhes == {"midia": "foto"} and "só consigo ler mensagens de texto" in msgs[1].texto
    assert c.post("/simulador/midia", data={"tipo": "figurinha"}).status_code == 400


def test_midia_com_vendedor_atendendo_a_lia_nao_responde(demo):             # RM-06
    c, repo = demo
    c.post("/simulador/mensagem", data={"texto": "oi"})
    [conv] = repo.listar()
    c.post(f"/atendimento/{conv.id}/assumir")
    c.post("/simulador/midia", data={"tipo": "documento"})
    assert repo.mensagens(conv.id)[-1].texto == "[cliente enviou um documento]"
