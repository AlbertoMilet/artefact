"""Primeiro nome do cliente a partir do nome do perfil do WhatsApp (SPEC-010). Função pura.

O perfil é escrito pelo próprio cliente: pode ter emoji, apelido, nome de empresa ou uma tentativa de
instrução. Só uma palavra feita de letras, que pareça nome de pessoa, chega ao prompt (NC-01 a NC-04).
"""

from __future__ import annotations

import re
import unicodedata

TAMANHO_MIN, TAMANHO_MAX = 2, 20

_NOME = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")          # só letras; hífen/apóstrofo internos
_PONTAS = re.compile(r"^[\W_]+|[\W_]+$")                       # emoji e pontuação nas pontas

TITULOS = frozenset({"dr", "dra", "sr", "sra", "srta", "prof", "profa", "pe", "pr"})

NAO_NOMES = frozenset({
    "loja", "lojas", "cliente", "vendas", "venda", "comercial", "contato", "atendimento", "suporte", "empresa",
    "whatsapp", "business", "zap", "oi", "ola", "olá", "eu", "voce", "você", "user", "usuario", "usuário",
    "teste", "test", "admin", "system", "sistema", "assistant", "assistente", "ignore", "ignorar", "esqueça",
    "esqueca", "instrucao", "instrução", "prompt", "desconto", "promo", "promocao", "promoção",
    "musica", "música", "music", "instrumentos", "desconhecido", "anonimo", "anônimo", "null", "none",
})


def _capitalizar(nome: str) -> str:
    return re.sub(r"[^\W\d_]+", lambda m: m.group(0)[0].upper() + m.group(0)[1:].lower(), nome)


def primeiro_nome(perfil: str | None) -> str | None:
    """Primeiro nome do perfil, ou None quando o perfil não traz um nome de pessoa."""
    if not perfil:
        return None
    for palavra in unicodedata.normalize("NFC", perfil).split():
        palavra = _PONTAS.sub("", palavra)
        if not palavra:
            continue                                            # só emoji ou pontuação: tenta a próxima
        if palavra.casefold() in TITULOS:
            continue                                            # NC-01: "Dra. Ana" -> Ana
        if not _NOME.fullmatch(palavra) or not TAMANHO_MIN <= len(palavra) <= TAMANHO_MAX:
            return None                                         # NC-02
        if palavra.casefold() in NAO_NOMES:
            return None                                         # NC-03
        return _capitalizar(palavra)                            # NC-04
    return None
