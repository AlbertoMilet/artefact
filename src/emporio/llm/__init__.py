"""Clientes de LLM (SPEC-001 D-02, D-06): OpenRouter com ZDR e um falso roteirizado para testes."""

from emporio.llm.base import LLMClient, LLMIndisponivel, RespostaLLM, ToolCall, Uso
from emporio.llm.fake import FakeLLMClient
from emporio.llm.openrouter import OpenRouterClient

__all__ = ["FakeLLMClient", "LLMClient", "LLMIndisponivel", "OpenRouterClient", "RespostaLLM", "ToolCall", "Uso"]
