"""Conexão do WhatsApp da loja (SPEC-004): regras, fluxo retomável, cifra e Graph API sem rede."""

import json
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import pytest

from emporio.whatsapp import conexao as arq
from emporio.whatsapp import regras
from emporio.whatsapp.conexao import Conexao, Etapa
from emporio.whatsapp.fluxo import EtapaInvalida, Onboarding
from emporio.whatsapp.meta import ErroMeta, GraphMeta, Numero, Token
from emporio.whatsapp.oauth_local import aguardar_retorno
from emporio.whatsapp.simulado import ProvedorSimulado


class Relogio:
    def __init__(self):
        self.t = datetime(2026, 11, 1, 10, 0)

    def __call__(self):
        return self.t

    def avancar(self, s):
        self.t += timedelta(seconds=s)


@pytest.fixture
def chave(monkeypatch):
    monkeypatch.setenv("WHATSAPP_CHAVE_CIFRA", arq.gerar_chave())


def novo(prov=None, relogio=None):
    return Onboarding(prov or ProvedorSimulado(codigo_fixo="482913"), Conexao(), relogio or Relogio())


def logar(ob):
    st = regras.novo_state()
    return ob.autenticar("codigo-oauth-simulado", st, st)


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
    ob = Onboarding(prov, Conexao(), Relogio())
    assert logar(ob) == ["2001"] and ob.c.etapa == Etapa.AUTENTICADO
    ob.cadastrar_numero("(67) 99999-0000", "Empório da Música")
    assert ob.c.etapa == Etapa.NUMERO_ESCOLHIDO and ob.c.numero_exibicao == "+55 67999990000"
    ob.pedir_codigo("SMS")
    assert prov.chamadas[-1] == "pedir_codigo:SMS" and ob.c.etapa == Etapa.CODIGO_ENVIADO
    ob.confirmar_codigo("482913")
    ob.registrar("123456")
    ob.assinar_webhooks()
    assert ob.c.etapa == Etapa.CONECTADO and prov.webhooks == {"2001"}
    salvo = arq.caminho().read_text(encoding="utf-8")
    assert "token-longo-simulado" not in salvo and "123456" not in salvo          # nem token nem PIN em claro
    assert arq.decifrar(arq.carregar().token_cifrado).startswith("token-longo-simulado")


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


def test_cw06_retoma_de_onde_parou(chave):
    prov = ProvedorSimulado(codigo_fixo="482913")
    ob = Onboarding(prov, Conexao(), Relogio())
    logar(ob)
    ob.escolher_numero(ob.numeros()[0])
    ob.pedir_codigo()
    # novo comando: conexão relida do disco, token decifrado, sem novo login
    ob2 = Onboarding(prov, arq.carregar(), Relogio())
    assert ob2.c.etapa == Etapa.CODIGO_ENVIADO and not ob2.precisa_login()
    ob2.confirmar_codigo("482913")
    assert ob2.c.etapa == Etapa.VERIFICADO


def test_login_refeito_no_meio_nao_perde_a_etapa():
    prov = ProvedorSimulado(codigo_fixo="482913")
    ob = Onboarding(prov, Conexao(), Relogio())
    logar(ob)
    ob.escolher_numero(ob.numeros()[0])
    ob.pedir_codigo()
    ob2 = Onboarding(prov, arq.carregar(), Relogio())                           # sem chave: sem token salvo
    assert ob2.precisa_login()
    logar(ob2)
    assert ob2.c.etapa == Etapa.CODIGO_ENVIADO


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


# ---------------------------------------------------------------- Graph API real, sem rede (CW-07)

def test_cw07_graph_meta_endpoints_v25():
    chamadas = []
    respostas = {
        "oauth/access_token": {"access_token": "EAAG-curto", "expires_in": 3600},
        "debug_token": {"data": {"is_valid": True, "app_id": "123", "scopes": list(regras.ESCOPOS),
                                 "granular_scopes": [{"scope": "whatsapp_business_management", "target_ids": ["777"]}]}},
        "777/phone_numbers": {"id": "888", "data": [{"id": "888", "display_phone_number": "+55 67 99999-0000",
                                                     "verified_name": "Empório", "code_verification_status": "NOT_VERIFIED",
                                                     "status": "PENDING"}]},
    }

    def transporte(metodo, url, params, token):
        caminho = url.split("/v25.0/")[1]
        chamadas.append((metodo, caminho, params, token))
        return respostas.get(caminho, {"success": True})

    g = GraphMeta("123", "segredo", "http://localhost:8765/callback", transporte=transporte)
    url = urlparse(g.url_login("st"))
    q = parse_qs(url.query)
    assert url.netloc == "www.facebook.com" and url.path == "/v25.0/dialog/oauth"
    assert q["state"] == ["st"] and set(q["scope"][0].split(",")) >= set(regras.ESCOPOS_OBRIGATORIOS)
    tok = g.longa_duracao(g.trocar_codigo("abc"))
    info = g.validar(tok)
    assert info == {"valido": True, "app_id": "123", "escopos": list(regras.ESCOPOS), "wabas": ["777"]}
    assert g.listar_numeros(tok, "777")[0].id == "888"
    g.cadastrar_numero(tok, "777", "55", "67999990000", "Empório")
    g.pedir_codigo(tok, "888")
    g.confirmar_codigo(tok, "888", "482913")
    g.registrar(tok, "888", "123456")
    g.assinar_webhooks(tok, "777")
    por_caminho = {(m, c): (p, t) for m, c, p, t in chamadas}
    assert por_caminho[("GET", "oauth/access_token")][0].get("grant_type") == "fb_exchange_token"
    assert por_caminho[("GET", "debug_token")][0]["access_token"] == "123|segredo"
    assert por_caminho[("POST", "777/phone_numbers")][0] == {"cc": "55", "phone_number": "67999990000",
                                                            "verified_name": "Empório"}
    assert por_caminho[("POST", "888/request_code")][0] == {"code_method": "SMS", "language": "pt_BR"}
    assert por_caminho[("POST", "888/verify_code")][0] == {"code": "482913"}
    assert por_caminho[("POST", "888/register")][0] == {"messaging_product": "whatsapp", "pin": "123456"}
    assert ("POST", "777/subscribed_apps") in por_caminho
    assert all(t == "EAAG-curto" for (m, c), (p, t) in por_caminho.items() if c not in ("oauth/access_token", "debug_token"))


def test_graph_meta_exige_credenciais():
    with pytest.raises(ErroMeta, match="META_APP_ID"):
        GraphMeta("", "", "http://localhost:8765/callback")


def test_servidor_local_recebe_o_retorno_do_oauth():
    resultado = {}

    def esperar():
        resultado["r"] = aguardar_retorno("x", "http://localhost:8799/callback", timeout_s=10, abrir=False)

    t = threading.Thread(target=esperar)
    t.start()
    for _ in range(50):
        try:
            urlopen("http://localhost:8799/callback?code=abc&state=xyz", timeout=2).read()
            break
        except OSError:
            time.sleep(0.1)
    t.join(10)
    assert resultado["r"] == ("abc", "xyz", None)
