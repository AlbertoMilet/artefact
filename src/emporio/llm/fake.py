"""LLM falso e roteirizado (SPEC-001 5.2): testes sem chave, sem rede e sem custo.

Cada passo do roteiro é uma RespostaLLM ou uma função que recebe as mensagens e devolve uma.
As chamadas recebidas ficam em `chamadas`, para os testes inspecionarem o que o agente enviou.
"""

from __future__ import annotations

import itertools
import json
from typing import Callable

from emporio.llm.base import LLMIndisponivel, RespostaLLM, ToolCall

Passo = RespostaLLM | Callable[[list[dict]], RespostaLLM] | Exception

_ids = itertools.count(1)


def chamar(nome: str, **argumentos) -> RespostaLLM:
    """Atalho: resposta do modelo pedindo uma tool."""
    return RespostaLLM(tool_calls=[ToolCall(f"call_{next(_ids)}", nome, json.dumps(argumentos, ensure_ascii=False))])


def responder(texto: str) -> RespostaLLM:
    return RespostaLLM(texto=texto)


class FakeLLMClient:
    modelo = "fake/roteiro"

    def __init__(self, roteiro: list[Passo] | None = None):
        self.roteiro = list(roteiro or [])
        self.chamadas: list[dict] = []

    def completar(self, mensagens: list[dict], tools: list[dict], forcar_texto: bool = False,
                  sem_raciocinio: bool = False) -> RespostaLLM:
        self.chamadas.append({"mensagens": [dict(m) for m in mensagens], "tools": [t["function"]["name"] for t in tools],
                              "forcar_texto": forcar_texto})
        if not self.roteiro:
            raise LLMIndisponivel("roteiro do FakeLLMClient esgotado")
        passo = self.roteiro.pop(0)
        if isinstance(passo, Exception):
            raise passo
        return passo(mensagens) if callable(passo) else passo
