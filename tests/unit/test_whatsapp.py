"""Conexão do WhatsApp da loja (SPEC-004): regras, fluxo retomável, cifra, segurança e Graph API sem rede."""

import threading
import time
from datetime import datetime, timedelta
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import pytest

from emporio.rules.horario import FUSO
from emporio.whatsapp import conexao as arq
from emporio.whatsapp import regras
from emporio.whatsapp.conexao import Conexao, ConexaoCorrompida, Etapa
from emporio.whatsapp.fluxo import EtapaInvalida, Onboarding, PrecisaLogin
from emporio.whatsapp.meta import ErroMeta, GraphMeta, Numero, Token
from emporio.whatsapp.oauth_local import aguardar_retorno
from emporio.whatsapp.simulado import ProvedorSimulado


class Relogio:
    def __init__(self):
        self.t = datetime(2026, 11, 1, 10, 0, tzinfo=FUSO)      # com fuso (revisão do Codex)

    def __call__(self):
        return self.t

    def avancar(self, s):
        self.t += timedelta(seconds=s)


@pytest.fixture
def chave(monkeypatch):
    monkeypatch.setenv("WHATSAPP_CHAVE_CIFRA", arq.gerar_chave())


def novo(prov=None, relogio=None):
    return Onboarding(prov or ProvedorSimulado(codigo_fixo="482913"), Conexao(ambiente="simulado"),
                      relogio or Relogio(), simulado=True)


def logar(ob, **kw):
    st = regras.novo_state()
    return ob.autenticar("codigo-oauth-simulado", st, st, **kw)


# ---------------------------------------------------------------- regras

def test_cw03_normalizar_numero():
    assert regras.normalizar_numero_br("(81) 99999-0000") == ("55", "81999990000")
    assert regras.normalizar_numero_br("+55 67 3341-4444") == ("55", "6733414444")
    for ruim in ("99999-0000", "(81) 89999-0000", "0800 123 456"):
        with pytest.raises(ValueError):
            regras.normalizar_numero_br(ruim)


def test_codigo_e_pin():
    assert regras.validar_codigo("482 913") == "482913"
    with pytest.raises(ValueError):
        regras.validar_codigo("12345")
    with pytest.raises(ValueError):
        regras.validar_pin("12a456")


def test_redirect_so_em_loopback():
    assert regras.validar_redirect("http://localhost:8765/callback") == ("localhost", 8765, "/callback")
    for ruim in ("http://0.0.0.0:8765/callback", "https://minhaloja.com/callback", "http://localhost/callback"):
        with pytest.raises(ValueError):
            regras.validar_redirect(ruim)


def test_cw01_state_diferente_recusa():
    ob = novo()
    with pytest.raises(EtapaInvalida, match="CSRF"):
        ob.autenticar("codigo-oauth-simulado", "outro", regras.novo_state())
    assert ob.c.etapa == Etapa.NAO_CONECTADO


def test_cw02_token_de_outro_app_ou_sem_permissao():
    prov = ProvedorSimulado()
    prov.app_id = "meu-app"                                    # validar() devolve "app-simulado"
    with pytest.raises(EtapaInvalida, match="outro app"):
        logar(novo(prov))
    prov2 = ProvedorSimulado()
    prov2.validar = lambda t: {"valido": True, "app_id": prov2.app_id, "escopos": ["whatsapp_business_management"],
                               "wabas": ["2001"]}
    with pytest.raises(EtapaInvalida, match="whatsapp_business_messaging"):
        logar(novo(prov2))


# ---------------------------------------------------------------- fluxo

def test_cw05_fluxo_completo_sem_token_em_claro(chave):
    prov = ProvedorSimulado(codigo_fixo="482913")
    ob = novo(prov)
    assert logar(ob) == ["2001"] and ob.c.etapa == Etapa.AUTENTICADO
    ob.cadastrar_numero("(67) 99999-0000", "Empório da Música")
    assert ob.c.etapa == Etapa.NUMERO_ESCOLHIDO and ob.c.numero_exibicao == "+55 67999990000"
    ob.pedir_codigo("SMS")
    assert prov.chamadas[-1] == "pedir_codigo:SMS" and ob.c.etapa == Etapa.CODIGO_ENVIADO
    ob.confirmar_codigo("482913")
    ob.registrar("123456")
    ob.assinar_webhooks()
    assert ob.c.etapa == Etapa.ASSINADO and prov.webhooks == {"2001"}
    salvo = arq.caminho(simulado=True).read_text(encoding="utf-8")
    assert "token-longo-simulado" not in salvo and "123456" not in salvo          # nem token nem PIN em claro
    assert arq.decifrar(arq.carregar(True).token_cifrado).startswith("token-longo-simulado")
    assert prov.registrados == {ob.c.phone_number_id}                              # PIN não guardado nem no simulado
    assert not arq.caminho(simulado=False).exists()                                # real e simulado separados


def test_sem_chave_o_token_nao_e_salvo():
    ob = novo()
    logar(ob)
    assert ob.c.token_cifrado is None and any("WHATSAPP_CHAVE_CIFRA" in a for a in ob.avisos)
    assert ob.numeros()                                                          # token segue em memória


def test_cw04_tentativas_e_intervalo_do_codigo():
    rel = Relogio()
    ob = novo(relogio=rel)
    logar(ob)
    ob.escolher_numero(ob.numeros()[0])
    ob.pedir_codigo()
    with pytest.raises(EtapaInvalida, match="aguarde"):
        ob.pedir_codigo()
    for _ in range(5):
        with pytest.raises(ErroMeta):
            ob.confirmar_codigo("000000")
    with pytest.raises(EtapaInvalida, match="peça outro"):
        ob.confirmar_codigo("482913")
    rel.avancar(61)
    ob.pedir_codigo()
    ob.confirmar_codigo("482913")
    assert ob.c.etapa == Etapa.VERIFICADO


def test_falha_de_rede_nao_gasta_tentativa():
    prov = ProvedorSimulado(codigo_fixo="482913")
    ob = novo(prov)
    logar(ob)
    ob.escolher_numero(ob.numeros()[0])
    ob.pedir_codigo()

    def sem_rede(*a):
        raise ErroMeta("sem conexão com a Meta: timeout")

    prov.confirmar_codigo = sem_rede
    with pytest.raises(ErroMeta):
        ob.confirmar_codigo("482913")
    assert ob.c.tentativas_codigo == 0


def test_cw06_retoma_de_onde_parou_com_provedor_novo(chave):
    # cada comando cria um provedor novo: o simulado do CLI é determinístico (estrito=False, código fixo)
    ob = novo(ProvedorSimulado(codigo_fixo="123456", estrito=False))
    logar(ob)
    ob.escolher_numero(ob.numeros()[0])
    ob.pedir_codigo()
    ob2 = Onboarding(ProvedorSimulado(codigo_fixo="123456", estrito=False), arq.carregar(True), Relogio(), simulado=True)
    assert ob2.c.etapa == Etapa.CODIGO_ENVIADO and not ob2.precisa_login()
    ob2.confirmar_codigo("123456")
    ob3 = Onboarding(ProvedorSimulado(codigo_fixo="123456", estrito=False), arq.carregar(True), Relogio(), simulado=True)
    ob3.registrar("654321")
    assert ob3.c.etapa == Etapa.REGISTRADO


def test_login_refeito_no_meio_nao_perde_a_etapa():
    prov = ProvedorSimulado(codigo_fixo="482913")
    ob = novo(prov)
    logar(ob)
    ob.escolher_numero(ob.numeros()[0])
    ob.pedir_codigo()
    ob2 = Onboarding(prov, arq.carregar(True), Relogio(), simulado=True)        # sem chave: sem token salvo
    assert ob2.precisa_login()
    logar(ob2)
    assert ob2.c.etapa == Etapa.CODIGO_ENVIADO


def test_token_expirado_e_token_revogado_pedem_login(chave):
    rel = Relogio()
    prov = ProvedorSimulado(codigo_fixo="482913")
    ob = novo(prov, rel)
    logar(ob)
    rel.avancar(61 * 24 * 3600)                                                  # o simulado expira em 60 dias
    assert ob.precisa_login()
    with pytest.raises(PrecisaLogin, match="expirou"):
        ob.numeros()
    rel.t = datetime(2026, 11, 1, 10, 0, tzinfo=FUSO)
    logar(ob)

    def revogado(*a):
        raise ErroMeta("Error validating access token", 190)

    prov.listar_numeros = revogado
    with pytest.raises(PrecisaLogin, match="recusou o token"):
        ob.numeros()


def test_conexao_de_outro_app_e_recusada():
    with pytest.raises(EtapaInvalida, match="outro app"):
        Onboarding(ProvedorSimulado(), Conexao(app_id="outro-app"), Relogio(), simulado=True)


def test_arquivo_corrompido_avisa():
    arq.caminho(simulado=True).write_text("{quebrado", encoding="utf-8")
    with pytest.raises(ConexaoCorrompida, match="desconectar"):
        arq.carregar(True)


def test_escolha_da_waba_e_waba_de_reserva():
    prov = ProvedorSimulado()
    prov.wabas = ["2001", "2002"]
    ob = novo(prov)
    logar(ob, escolher_waba=lambda ws: "2002")
    assert ob.c.waba_id == "2002"
    prov2 = ProvedorSimulado()
    prov2.wabas = []
    with pytest.raises(EtapaInvalida, match="META_WABA_ID"):
        logar(novo(prov2))
    ob3 = novo(prov2)
    logar(ob3, waba_reserva="9999")
    assert ob3.c.waba_id == "9999"


def test_cadastro_reconcilia_numero_que_ja_existe():
    prov = ProvedorSimulado(numeros=[Numero("1", "+55 67 99999-0000", "Loja", "VERIFIED", "PENDING")])
    ob = novo(prov)
    logar(ob)
    ob.cadastrar_numero("(67) 99999-0000", "Loja")
    assert ob.c.phone_number_id == "1" and ob.c.etapa == Etapa.VERIFICADO and len(prov.numeros) == 1


def test_numero_ja_verificado_ou_ativo_pula_etapas():
    ob = novo(ProvedorSimulado(numeros=[Numero("1", "+55 67 1", "Loja", "VERIFIED", "PENDING"),
                                        Numero("2", "+55 67 2", "Loja", "VERIFIED", "CONNECTED")]))
    logar(ob)
    n1, n2 = ob.numeros()
    ob.escolher_numero(n1)
    assert ob.c.etapa == Etapa.VERIFICADO
    ob.escolher_numero(n2)
    assert ob.c.etapa == Etapa.REGISTRADO


def test_etapa_fora_de_ordem():
    ob = novo()
    with pytest.raises(EtapaInvalida):
        ob.registrar("123456")
    logar(ob)
    with pytest.raises(EtapaInvalida, match="próxima ação: escolher"):
        ob.confirmar_codigo("482913")


# ---------------------------------------------------------------- segredos

def test_token_e_segredo_fora_do_repr_e_erro_limpo():
    assert "EAAG" not in repr(Token("EAAGsegredo1234567890"))
    g = GraphMeta("123", "meu-segredo", "http://localhost:8765/callback", transporte=lambda *a: {})
    assert "meu-segredo" not in repr(g)
    e = ErroMeta("token EAAGabcdefghijklmnop inválido; access_token=xyz; código 482913", 190)
    assert "EAAG" not in str(e) and "xyz" not in str(e) and "482913" not in str(e) and e.autenticacao


# ---------------------------------------------------------------- Graph API real, sem rede (CW-07)

def test_cw07_graph_meta_endpoints_v25():
    chamadas = []
    respostas = {
        "debug_token": {"data": {"is_valid": True, "app_id": "123", "scopes": list(regras.ESCOPOS),
                                 "granular_scopes": [{"scope": "whatsapp_business_management", "target_ids": ["777"]}]}},
        "777/phone_numbers": {"id": "888", "data": [{"id": "888", "display_phone_number": "+55 67 99999-0000",
                                                     "verified_name": "Empório", "code_verification_status": "NOT_VERIFIED",
                                                     "status": "PENDING"}],
                              "paging": {"next": "https://graph.facebook.com/v25.0/777/phone_numbers?after=X"}},
    }

    def transporte(metodo, url, params, token):
        caminho = url.split("/v25.0/")[1]
        chamadas.append((metodo, caminho, dict(params), token))
        if caminho == "oauth/access_token":
            return {"access_token": "EAAG-longo" if params.get("grant_type") else "EAAG-curto", "expires_in": 3600}
        if caminho.startswith("777/phone_numbers?after"):
            return {"data": [{"id": "889", "display_phone_number": "+55 67 98888-0000", "verified_name": "Empório 2"}]}
        if caminho in respostas:
            return respostas[caminho]
        if (metodo, caminho) in {("POST", "888/request_code"), ("POST", "888/verify_code"), ("POST", "888/register"),
                                 ("POST", "777/subscribed_apps")}:
            return {"success": True}
        raise AssertionError(f"chamada inesperada: {metodo} {caminho}")         # nada de sucesso por padrão

    g = GraphMeta("123", "segredo", "http://localhost:8765/callback", transporte=transporte)
    url = urlparse(g.url_login("st"))
    q = parse_qs(url.query)
    assert url.netloc == "www.facebook.com" and url.path == "/v25.0/dialog/oauth"
    assert q["state"] == ["st"] and set(q["scope"][0].split(",")) >= set(regras.ESCOPOS_OBRIGATORIOS)
    tok = g.longa_duracao(g.trocar_codigo("abc"))
    assert tok.valor == "EAAG-longo"
    info = g.validar(tok)
    assert info == {"valido": True, "app_id": "123", "escopos": list(regras.ESCOPOS), "wabas": ["777"]}
    assert [n.id for n in g.listar_numeros(tok, "777")] == ["888", "889"]               # paginação
    g.cadastrar_numero(tok, "777", "55", "67999990000", "Empório")
    g.pedir_codigo(tok, "888")
    g.confirmar_codigo(tok, "888", "482913")
    g.registrar(tok, "888", "123456")
    g.assinar_webhooks(tok, "777")
    troca, longa = chamadas[0], chamadas[1]
    assert troca == ("GET", "oauth/access_token", {"client_id": "123", "client_secret": "segredo",
                                                  "redirect_uri": "http://localhost:8765/callback", "code": "abc"}, None)
    assert longa[2] == {"grant_type": "fb_exchange_token", "client_id": "123", "client_secret": "segredo",
                        "fb_exchange_token": "EAAG-curto"}
    por = {(m, c): (p, t) for m, c, p, t in chamadas[2:]}
    assert por[("GET", "debug_token")][0] == {"input_token": "EAAG-longo", "access_token": "123|segredo"}
    assert por[("POST", "777/phone_numbers")][0] == {"cc": "55", "phone_number": "67999990000", "verified_name": "Empório"}
    assert por[("POST", "888/request_code")][0] == {"code_method": "SMS", "language": "pt_BR"}
    assert por[("POST", "888/verify_code")][0] == {"code": "482913"}
    assert por[("POST", "888/register")][0] == {"messaging_product": "whatsapp", "pin": "123456"}
    assert ("POST", "777/subscribed_apps") in por
    assert all(t == "EAAG-longo" for (m, c), (p, t) in por.items() if c != "debug_token")


def test_graph_meta_exige_credenciais():
    with pytest.raises(ErroMeta, match="META_APP_ID"):
        GraphMeta("", "", "http://localhost:8765/callback")


# ---------------------------------------------------------------- servidor local do OAuth

def _get(url):
    try:
        return urlopen(url, timeout=2).read().decode()
    except HTTPError as e:
        return e.read().decode()


def test_servidor_local_ignora_requisicoes_alheias_e_escapa_html():
    resultado = {}

    def esperar():
        resultado["r"] = aguardar_retorno("x", "http://localhost:8799/callback", state_esperado="xyz",
                                          timeout_s=15, abrir=False)

    t = threading.Thread(target=esperar)
    t.start()
    pagina = ""
    for _ in range(50):
        try:
            pagina = _get("http://localhost:8799/outro")                     # caminho errado: não encerra
            break
        except OSError:
            time.sleep(0.1)
    assert "desconhecido" in pagina
    assert "não corresponde" in _get("http://localhost:8799/callback?code=abc&state=errado")   # state errado: não encerra
    injecao = _get("http://localhost:8799/callback?state=xyz&error=x&error_description=%3Cscript%3Ealert(1)%3C/script%3E")
    assert "<script>" not in injecao and "&lt;script&gt;" in injecao
    t.join(15)
    assert resultado["r"] == (None, "xyz", "<script>alert(1)</script>")
