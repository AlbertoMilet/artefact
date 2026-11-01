"""Origem do lead por marcador na mensagem pré-preenchida do link do WhatsApp (SPEC-005).

Cada canal divulga um link `wa.me` com a mesma mensagem e um emoji próprio no fim. A primeira mensagem
da conversa (ou a primeira de uma janela de 24 h nova) é conferida aqui, em código, sem o modelo. O
marcador é tirado do texto antes de ir ao LLM, para a Lia não comentar o emoji.

Funções puras: sem banco, rede nem LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

VS16 = "️"                         # seletor de variação: "▶️" pode chegar com ou sem ele


@dataclass(frozen=True)
class Origem:
    chave: str
    nome: str
    marcador: str


ORIGENS: tuple[Origem, ...] = (
    Origem("instagram", "Instagram", "📸"),
    Origem("tiktok", "TikTok", "🎬"),
    Origem("google", "Landing page (Google)", "🔎"),
    Origem("youtube", "YouTube", "▶️"),
)
POR_CHAVE = {o.chave: o for o in ORIGENS}
MENSAGEM_PADRAO = "Olá! Quero mais informações"


def _sem_vs16(texto: str) -> str:
    return texto.replace(VS16, "")


def detectar(texto: str) -> tuple[Origem | None, str]:
    """(origem, texto sem o marcador). Só reconhece o marcador no FIM da mensagem: um emoji no meio da
    frase ("adoro 🎬 e quero um violão") não vira origem."""
    limpo = (texto or "").rstrip()
    base = _sem_vs16(limpo)
    origem = next((o for o in ORIGENS if base.endswith(_sem_vs16(o.marcador))), None)
    if origem is None:
        return None, texto
    marcador = re.escape(_sem_vs16(origem.marcador)) + f"{VS16}?"
    sem = re.sub(rf"\s*{marcador}\s*$", "", limpo).rstrip()
    return origem, sem or texto


def link_whatsapp(numero_whatsapp: str, origem: Origem, mensagem: str = MENSAGEM_PADRAO) -> str:
    """https://wa.me/55DDDNUMERO?text=... com o marcador do canal no fim da mensagem."""
    digitos = re.sub(r"\D", "", numero_whatsapp or "")
    if not digitos.startswith("55"):
        digitos = "55" + digitos
    if len(digitos) not in (12, 13):
        raise ValueError("número do WhatsApp inválido: use DDD + número, ex.: (67) 3341-4444")
    return f"https://wa.me/{digitos}?text={quote(f'{mensagem.strip()} {origem.marcador}')}"


def resumir(origens: list[str | None]) -> dict[str, int]:
    """Contagem por canal, na ordem de ORIGENS, com 'desconhecida' para conversa sem marcador."""
    contagem = {o.chave: 0 for o in ORIGENS} | {"desconhecida": 0}
    for chave in origens:
        contagem[chave if chave in POR_CHAVE else "desconhecida"] += 1
    return contagem
