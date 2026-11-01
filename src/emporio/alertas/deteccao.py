"""Pedido explícito por um vendedor ou atendente (SPEC-003 RA-01).

Determinístico de propósito, como o EXPLICIT_LAWYER_REQUEST do Saúde Legal: é o caso mais quente e não
pode depender de o modelo entender. Exige um verbo de pedido perto da pessoa pedida, para não disparar
em "o vendedor de vocês me indicou este violão" nem em "quero um violão para uma pessoa iniciante".
Trechos negados ("não quero falar com um vendedor") são retirados antes da busca (revisão do Codex).
"""

from __future__ import annotations

import re

from emporio.data.normalize import normalizar

_PESSOA = (r"(vendedor|vendedora|atendente|humano|humana|pessoa|alguem|gerente|consultor|consultora|"
           r"funcionario|funcionaria)")
# "não/nem/sem ... (até 5 palavras) ... vendedor": o cliente recusa a pessoa, não a pede
_NEGADO = re.compile(r"\b(nao|nem|sem)\s+(\w+\s+){0,5}?" + _PESSOA + r"\b")
_PADROES = [
    # verbo de comunicação, com até 3 palavras no meio: "posso falar com o gerente", "me passa pra um atendente"
    re.compile(r"\b(falar|conversar|atendimento|atender|chamar?|chama|passa|passar|transferir|transfere|transfira)\b"
               r"(\s+\w+){0,3}?\s+(com\s+)?(um|uma|o|a|algum|alguma)?\s*" + _PESSOA + r"\b"),
    # verbo de desejo colado na pessoa: "quero um vendedor", "tem algum atendente"
    re.compile(r"\b(quero|queria|preciso|gostaria de|tem|existe|ha)\s+(um|uma|algum|alguma|o|a)\s+" + _PESSOA + r"\b"),
    re.compile(r"\batendimento\s+(humano|pessoal|com\s+pessoa)\b"),
    re.compile(r"\b(nao|nem)\s+quero\s+(falar\s+com\s+)?(robo|bot|maquina|ia)\b"),
    re.compile(r"^\s*(atendente|vendedor|humano)\s*[!?.]*\s*$"),
]


def pediu_vendedor(texto: str) -> bool:
    t = normalizar(texto)
    if not t:
        return False
    t = _NEGADO.sub(" ", t)
    return any(p.search(t) for p in _PADROES)
