"""Contrato entre o agente e qualquer LLM. O agente não conhece o provedor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class LLMIndisponivel(RuntimeError):
    """Falha de rede, chave, limite de uso ou ausência de endpoint ZDR. Vira resposta segura (RN-23)."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    nome: str
    argumentos: str          # JSON, como veio do modelo


@dataclass(frozen=True)
class Uso:
    tokens_entrada: int = 0
    tokens_saida: int = 0
    custo_usd: float = 0.0
    provedor: str | None = None
    modelo: str | None = None


@dataclass(frozen=True)
class RespostaLLM:
    texto: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    uso: Uso = field(default_factory=Uso)

    def mensagem_assistente(self) -> dict:
        """Formato de mensagem compatível com a API de chat da OpenAI, para o histórico."""
        msg: dict = {"role": "assistant", "content": self.texto or ""}
        if self.tool_calls:
            msg["tool_calls"] = [{"id": c.id, "type": "function",
                                  "function": {"name": c.nome, "arguments": c.argumentos}} for c in self.tool_calls]
        return msg


class LLMClient(Protocol):
    modelo: str

    def completar(self, mensagens: list[dict], tools: list[dict], forcar_texto: bool = False,
                  sem_raciocinio: bool = False) -> RespostaLLM:
        """forcar_texto: responder em texto, sem pedir tools (limite do turno).
        sem_raciocinio: desliga o raciocínio estendido, quando o modelo permite (tarefas curtas em JSON)."""
        ...
