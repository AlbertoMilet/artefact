"""Fotos, áudios, vídeos e documentos (SPEC-014): regras puras."""

import pytest

from emporio.rules import midia


@pytest.mark.parametrize("tipo, esperado", [("foto", "[cliente enviou uma foto]"), ("Áudio", "[cliente enviou um áudio]"),
                                            ("video", "[cliente enviou um vídeo]"),
                                            ("documento", "[cliente enviou um documento]")])
def test_marcador(tipo, esperado):
    assert midia.marcador(tipo) == esperado


def test_tipo_desconhecido_e_recusado():                                      # RM-01
    with pytest.raises(ValueError):
        midia.validar("figurinha")


def test_resposta_fixa_com_contato():                                         # RM-03
    r = midia.resposta("audio", "(67) 3341-4444")
    assert "só consigo ler mensagens de texto" in r and "ouvir áudios" in r and "(67) 3341-4444" in r


def test_quando_alertar_a_equipe():                                           # RM-05
    assert midia.precisa_da_equipe(None, None, []) is False
    assert midia.precisa_da_equipe(5, None, []) is True
    assert midia.precisa_da_equipe(None, {"tipo": "troca"}, []) is True
    assert midia.precisa_da_equipe(None, None, ["SIM-20260325-0001"]) is True
