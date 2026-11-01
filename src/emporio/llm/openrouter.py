"""Cliente do OpenRouter com Zero Data Retention obrigatório (SPEC-001 D-02, RN-23).

- Toda requisição leva provider = {"zdr": true, "require_parameters": true, "data_collection": "deny"}.
- Sem endpoint ZDR disponível, a chamada falha (LLMIndisponivel); nunca há nova tentativa sem ZDR.
- Parâmetros opcionais (temperature, limite de saída) só vão quando algum endpoint ZDR do modelo os
  suporta. Com require_parameters, mandar um parâmetro sem suporte faz o OpenRouter responder 404
  "No endpoints found" (Fase 0: Claude Haiku 5.5 e GPT-6 Luna não aceitam temperature).
"""

from __future__ import annotations

import json
import logging
import threading
from urllib.request import urlopen

from openai import OpenAI, OpenAIError

from emporio.llm.base import LLMIndisponivel, RespostaLLM, ToolCall, Uso

log = logging.getLogger(__name__)

BASE_URL = "https://openrouter.ai/api/v1"
URL_ZDR = f"{BASE_URL}/endpoints/zdr"
PROVIDER = {"zdr": True, "require_parameters": True, "data_collection": "deny"}
TEMPERATURA = 0.2
MAX_SAIDA = 800


_cache_zdr: list | None = None
_trava_zdr = threading.Lock()


def _lista_zdr(timeout: float) -> list | None:
    """Lista de endpoints ZDR, lida uma vez por processo (com uma nova tentativa)."""
    global _cache_zdr
    with _trava_zdr:
        if _cache_zdr is not None:
            return _cache_zdr
        for tentativa in (1, 2):
            try:
                with urlopen(URL_ZDR, timeout=timeout) as resp:
                    _cache_zdr = json.load(resp)["data"]
                return _cache_zdr
            except Exception as e:  # rede, TLS, JSON: não bloqueia; envia só o obrigatório
                if tentativa == 2:
                    log.warning("não foi possível ler a lista ZDR do OpenRouter: %s", e)
        return None


def parametros_zdr(modelo: str, timeout: float = 20) -> set[str] | None:
    """Parâmetros que algum endpoint ZDR do modelo (com suporte a tools) aceita.

    set() quando o modelo não tem endpoint ZDR com tools; None quando a lista não pôde ser lida.
    """
    dados = _lista_zdr(timeout)
    if dados is None:
        return None
    suportados: set[str] = set()
    for e in dados:
        params = set(e.get("supported_parameters") or [])
        if e.get("model_id") == modelo and "tools" in params:
            suportados |= params
    return suportados


class OpenRouterClient:
    def __init__(self, api_key: str, modelo: str, timeout: float = 30,
                 parametros_suportados: set[str] | None = None, cliente: OpenAI | None = None):
        if not api_key:
            raise LLMIndisponivel("OPENROUTER_API_KEY não definida")
        self.modelo = modelo
        self.suportados = parametros_suportados if parametros_suportados is not None else parametros_zdr(modelo)
        if self.suportados == set():
            log.error("modelo %s sem endpoint ZDR com suporte a tools", modelo)
        self._cliente = cliente or OpenAI(base_url=BASE_URL, api_key=api_key, timeout=timeout, max_retries=1)

    def montar_requisicao(self, mensagens: list[dict], tools: list[dict], forcar_texto: bool = False,
                          sem_raciocinio: bool = False) -> dict:
        """Argumentos de chat.completions.create. Separado para ser testado sem rede (CA-14)."""
        req: dict = {"model": self.modelo, "messages": mensagens,
                     "extra_body": {"provider": dict(PROVIDER), "usage": {"include": True}}}
        if tools:
            req["tools"] = tools
            if forcar_texto:
                req["tool_choice"] = "none"
        s = self.suportados or set()        # lista ZDR ilegível: só o obrigatório
        if "temperature" in s:
            req["temperature"] = TEMPERATURA
        if "max_tokens" in s:
            req["max_tokens"] = MAX_SAIDA
        elif "max_completion_tokens" in s:
            req["extra_body"]["max_completion_tokens"] = MAX_SAIDA
        if sem_raciocinio and "reasoning" in s:
            # SPEC-002: com raciocínio, o DeepSeek às vezes gastava todos os tokens de saída deliberando
            # (finish_reason=length, conteúdo vazio). A decisão de retenção é curta e em JSON.
            req["extra_body"]["reasoning"] = {"enabled": False}
        return req

    def completar(self, mensagens: list[dict], tools: list[dict], forcar_texto: bool = False,
                  sem_raciocinio: bool = False) -> RespostaLLM:
        if self.suportados == set():
            raise LLMIndisponivel(f"modelo {self.modelo} sem endpoint ZDR com tools")
        try:
            r = self._cliente.chat.completions.create(**self.montar_requisicao(mensagens, tools, forcar_texto, sem_raciocinio))
        except OpenAIError as e:
            raise LLMIndisponivel(f"{type(e).__name__}: {e}") from e
        if not r.choices:
            raise LLMIndisponivel("resposta sem conteúdo")
        m = r.choices[0].message
        extra = r.model_extra or {}
        u = r.usage
        custo = 0.0
        if u is not None:
            custo = float(getattr(u, "cost", None) or (u.model_extra or {}).get("cost") or 0)
        uso = Uso(tokens_entrada=getattr(u, "prompt_tokens", 0) or 0, tokens_saida=getattr(u, "completion_tokens", 0) or 0,
                  custo_usd=custo, provedor=extra.get("provider"), modelo=r.model)
        calls = [ToolCall(c.id, c.function.name, c.function.arguments or "{}") for c in (m.tool_calls or [])]
        return RespostaLLM(texto=m.content, tool_calls=calls, uso=uso)
