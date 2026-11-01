"""Origem do lead pelo emoji do link (SPEC-005): função pura, valores escritos à mão."""

import pytest

from emporio.rules import origem
from emporio.rules.origem import POR_CHAVE, detectar, link_whatsapp, resumir


@pytest.mark.parametrize("texto, chave, limpo", [
    ("Olá! Quero mais informações 📸", "instagram", "Olá! Quero mais informações"),
    ("Olá! Quero mais informações 🎬", "tiktok", "Olá! Quero mais informações"),
    ("Olá! Quero mais informações 🔎", "google", "Olá! Quero mais informações"),
    ("Olá! Quero mais informações ▶️", "youtube", "Olá! Quero mais informações"),
    ("Olá! Quero mais informações ▶", "youtube", "Olá! Quero mais informações"),     # sem o seletor VS16
    ("Tem violão Takamine?📸  ", "instagram", "Tem violão Takamine?"),                # cliente editou o texto
])
def test_reconhece_o_marcador_no_fim(texto, chave, limpo):
    o, sem = detectar(texto)
    assert o.chave == chave and sem == limpo


@pytest.mark.parametrize("texto", [
    "Olá! Quero mais informações",            # cliente apagou o emoji
    "Adoro 🎬 e quero um violão",             # emoji no meio da frase não conta
    "Quero um violão 🎸",                       # emoji que não é de canal
    "",
])
def test_sem_origem(texto):
    assert detectar(texto) == (None, texto)


def test_so_o_marcador_do_fim_conta():
    o, sem = detectar("Oi 📸🎬")
    assert o.chave == "tiktok" and sem == "Oi 📸"


def test_mensagem_so_com_o_emoji_mantem_o_texto():
    o, sem = detectar("🔎")
    assert o.chave == "google" and sem == "🔎"           # nada sobraria: o texto original segue ao modelo


def test_link_do_whatsapp():
    url = link_whatsapp("(67) 3341-4444", POR_CHAVE["instagram"])
    assert url == "https://wa.me/556733414444?text=Ol%C3%A1%21%20Quero%20mais%20informa%C3%A7%C3%B5es%20%F0%9F%93%B8"
    assert link_whatsapp("+55 67 99999-0000", POR_CHAVE["tiktok"], "Oi").endswith("?text=Oi%20%F0%9F%8E%AC")
    with pytest.raises(ValueError):
        link_whatsapp("3341-4444", POR_CHAVE["google"])


def test_marcadores_unicos():
    assert len({o.marcador for o in origem.ORIGENS}) == len(origem.ORIGENS)


def test_resumo_por_canal():
    assert resumir(["instagram", None, "instagram", "youtube", "x"]) == {
        "instagram": 2, "tiktok": 0, "google": 0, "youtube": 1, "desconhecida": 2}
