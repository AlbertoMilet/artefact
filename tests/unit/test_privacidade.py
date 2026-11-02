"""LGPD no atendimento (SPEC-012): prazos, filtro do expurgo e máscara de CPF e CEP. Valores escritos à mão."""

import json
from datetime import datetime

import pytest

from emporio.rules.horario import FUSO
from emporio.rules.privacidade import PRAZO_RESPOSTA_TITULAR_DIAS, PRAZO_RETENCAO_DIAS, expirado, linhas_mantidas
from emporio.rules.verificacao import mascarar_texto

AGORA = datetime(2026, 11, 2, 10, 0, tzinfo=FUSO)


def test_prazos_da_politica():
    assert PRAZO_RETENCAO_DIAS == 90 and PRAZO_RESPOSTA_TITULAR_DIAS == 15


@pytest.mark.parametrize("registrado_em, esperado", [
    ("2026-08-05T10:00:00-04:00", False),    # CL-01: 89 dias
    ("2026-08-03T10:00:00-04:00", True),     # CL-01: 91 dias
    ("2026-11-01T09:00:00", False),           # sem fuso: assume Campo Grande
    (None, True), ("", True), ("ontem", True),   # RL-02: sem data ou ilegível conta como expirado
])
def test_expirado(registrado_em, esperado):
    assert expirado(registrado_em, AGORA) is esperado


def test_noventa_dias_exatos_ainda_ficam():
    assert expirado("2026-08-04T10:00:00-04:00", AGORA) is False      # 90 dias exatos: não passou do prazo
    assert expirado("2026-08-04T09:59:00-04:00", AGORA) is True       # um minuto além


def _linha(conversa, registrado_em=None):
    item = {"evento": "turno", "conversa": conversa}
    if registrado_em:
        item["registrado_em"] = registrado_em
    return json.dumps(item) + "\n"


def test_linhas_mantidas_no_expurgo_e_ao_apagar_conversa():
    linhas = [_linha("a", "2026-10-30T10:00:00-04:00"), _linha("b", "2026-10-30T10:00:00-04:00"),
              _linha("c", "2026-07-01T10:00:00-04:00"),       # vencida
              _linha("d"),                                     # sem data (antes da SPEC-012)
              "isto não é json\n", "\n", "[1, 2]\n"]
    assert [json.loads(x)["conversa"] for x in linhas_mantidas(linhas, AGORA)] == ["a", "b"]
    assert [json.loads(x)["conversa"] for x in linhas_mantidas(linhas, AGORA, apagar_conversa="a")] == ["b"]


@pytest.mark.parametrize("texto, esperado", [
    ("Meu CPF é 123.456.789-09", "Meu CPF é ***.***.***-09"),                       # CL-02
    ("CEP 79002-100, por favor", "CEP 79***-***, por favor"),
    ("A loja fica no CEP 79202-333", "A loja fica no CEP 79202-333"),               # CEP público da loja
    ("protocolo SIM-20260325-0001", "protocolo SIM-20260325-0001"),                 # não é CEP
    ("telefone (67) 99654-7821", "telefone (67) 9****-7821"),                       # máscara antiga continua
    ("versão 1.123.456.789-09x", "versão 1.123.456.789-09x"),                       # dentro de outro identificador
    ("CEP 79002100", "CEP 79***-***"),                                              # sem hífen, depois de "CEP"
    ("cep: 79002100", "cep: 79***-***"),
    ("CEP 79202333", "CEP 79202333"),                                              # o da loja, sem hífen
    ("pedido 12345678", "pedido 12345678"),                                        # 8 dígitos sem "CEP": não mexe
])
def test_mascara_cpf_e_cep(texto, esperado):
    assert mascarar_texto(texto) == esperado
