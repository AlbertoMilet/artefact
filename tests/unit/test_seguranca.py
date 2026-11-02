"""Segurança (SPEC-013): limites, máscara com pontos e sessões. Valores escritos à mão."""

from datetime import datetime, timedelta

import pytest

from emporio.rules.horario import FUSO
from emporio.rules.limites import passou_do_limite
from emporio.rules.verificacao import mascarar_texto

AGORA = datetime(2026, 11, 2, 10, 0, tzinfo=FUSO)


def _antes(*segundos):
    return [(AGORA - timedelta(seconds=s)).isoformat() for s in segundos]


def test_limite_por_minuto():                                        # CS-05, RS-05
    assert passou_do_limite(_antes(*range(1, 10)), AGORA) is False      # 9 no último minuto: a 10ª passa
    assert passou_do_limite(_antes(*range(1, 11)), AGORA) is True       # 10 no último minuto: a 11ª não
    assert passou_do_limite(_antes(*range(61, 71)), AGORA) is False     # as 10 foram há mais de 1 minuto


def test_limite_por_dia():
    duzentas = _antes(*range(100, 100 + 200 * 60, 60))                  # 200 espalhadas nas últimas ~3,3 h
    assert passou_do_limite(duzentas, AGORA) is True
    assert passou_do_limite(duzentas[:199], AGORA) is False
    assert passou_do_limite(_antes(*[86_400 + s for s in range(300)]), AGORA) is False   # todas de ontem


def test_limite_ignora_datas_ilegiveis_e_futuras():
    assert passou_do_limite(["ontem"] * 50 + [(AGORA + timedelta(minutes=5)).isoformat()] * 50, AGORA) is False


@pytest.mark.parametrize("texto, esperado", [
    ("ligue 67.91234.5678", "ligue (67) 9****-5678"),                  # CS-07
    ("67 9 1234 5678", "(67) 9****-5678"),
    ("+55 67 99654 7821", "(67) 9****-7821"),
    ("R$ 2.199,00 e R$ 11.499,00", "R$ 2.199,00 e R$ 11.499,00"),       # preços não mudam
    ("pedido 12 de 22.02.2026", "pedido 12 de 22.02.2026"),             # datas não mudam
])
def test_mascara_telefone_com_pontos_e_espacos(texto, esperado):
    assert mascarar_texto(texto) == esperado
