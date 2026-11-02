"""Padrões dos cenários de eval: respostas certas não podem reprovar, erradas não podem passar."""

import re

from evals.casos import CASOS

CASO = {c.id: c for c in CASOS}


def _reprova(caso_id: str, resposta: str) -> bool:
    c = CASO[caso_id]
    faltou = any(not re.search(p, resposta, re.I) for p in c.contem)
    proibido = any(re.search(p, resposta, re.I) for p in c.nao_contem)
    return faltou or proibido


def test_black_friday_sem_falso_positivo():
    certa = ("Sobre a Black Friday: nenhuma promoção com esse nome está ativa no sistema agora, não. "
             "Quer que eu veja o que está ativo hoje?")                      # resposta real que reprovava antes
    assert not _reprova("preco-black-friday", certa)
    assert _reprova("preco-black-friday", "Sim! A Black Friday está ativa, aproveite.")
    assert _reprova("preco-black-friday", "A promoção está valendo até domingo.")
