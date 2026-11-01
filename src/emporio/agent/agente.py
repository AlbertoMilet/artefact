"""Loop do agente (SPEC-001 §4.1, RN-23 a RN-26).

Um agente, um loop curto: o LLM pede tools, o código executa e devolve o resultado, até o LLM
responder em texto. Limites por turno (chamadas de tool e tempo), resposta segura em falha,
rastro de ferramentas para o --debug e histórico guardado sem telefone nem e-mail.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field

from emporio.agent.prompt import AVISO_PRIVACIDADE, montar_prompt
from emporio.llm.base import LLMClient, LLMIndisponivel, RespostaLLM
from emporio.rules.verificacao import mascarar_texto
from emporio.tools.toolbox import LOJA, Sessao, Toolbox

log = logging.getLogger("emporio.turno")

RESPOSTA_SEGURA = (
    "Desculpe, tive um problema para consultar isso agora. Você pode falar com a nossa equipe pelo "
    f"telefone/WhatsApp {LOJA['telefone_whatsapp']} ou pelo e-mail {LOJA['email']} "
    "(segunda a sexta, das 9h às 18h, e sábado, das 9h às 13h)."
)


@dataclass
class EventoTool:
    tool: str
    argumentos: str          # mascarado
    resultado: str           # mascarado e resumido
    duracao_ms: int
    erro: str | None = None


@dataclass
class Conversa:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    historico: list[dict] = field(default_factory=list)   # sem system; já mascarado
    sessao: Sessao = field(default_factory=Sessao)
    turnos: int = 0


@dataclass
class RespostaTurno:
    texto: str
    rastro: list[EventoTool] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_saida: int = 0
    custo_usd: float = 0.0
    latencia_s: float = 0.0
    segura: bool = False              # True quando caiu na resposta segura
    motivo_segura: str | None = None


def _resumir(resultado: dict, limite: int = 400) -> str:
    texto = json.dumps(resultado, ensure_ascii=False)
    return texto if len(texto) <= limite else texto[:limite] + "…"


def janela(historico: list[dict], turnos: int) -> list[dict]:
    """Últimos `turnos` turnos do cliente, cortando sempre numa mensagem de usuário
    (nunca deixa resultado de tool sem a chamada que o originou)."""
    inicios = [i for i, m in enumerate(historico) if m["role"] == "user"]
    if len(inicios) <= turnos:
        return list(historico)
    return list(historico[inicios[-turnos]:])


def _mascarar_mensagem(m: dict) -> dict:
    m = dict(m)
    if m.get("role") in ("user", "assistant") and m.get("content"):
        m["content"] = mascarar_texto(m["content"])
    if m.get("tool_calls"):
        m["tool_calls"] = [{**c, "function": {**c["function"], "arguments": mascarar_texto(c["function"]["arguments"])}}
                           for c in m["tool_calls"]]
    return m


class Agente:
    def __init__(self, llm: LLMClient, toolbox: Toolbox, max_tool_calls: int = 5,
                 timeout_turno_s: float = 30, janela_turnos: int = 10):
        self.llm = llm
        self.toolbox = toolbox
        self.max_tool_calls = max_tool_calls
        self.timeout_turno_s = timeout_turno_s
        self.janela_turnos = janela_turnos

    def nova_conversa(self) -> Conversa:
        return Conversa()

    def responder(self, conversa: Conversa, texto_cliente: str) -> RespostaTurno:
        inicio = time.perf_counter()
        primeira = conversa.turnos == 0
        conversa.turnos += 1
        system = {"role": "system", "content": montar_prompt(self.toolbox.relogio())}
        novas: list[dict] = [{"role": "user", "content": texto_cliente}]
        tools = self.toolbox.schemas_openai()
        resp = RespostaTurno(texto="")
        chamadas = erros = 0
        texto_final: str | None = None

        def mensagens() -> list[dict]:
            return [system, *janela(conversa.historico, self.janela_turnos - 1), *novas]

        try:
            while True:
                if time.perf_counter() - inicio > self.timeout_turno_s:
                    resp.motivo_segura = "tempo_limite"
                    break
                limite = chamadas >= self.max_tool_calls
                r: RespostaLLM = self.llm.completar(mensagens(), tools, forcar_texto=limite)
                resp.tokens_entrada += r.uso.tokens_entrada
                resp.tokens_saida += r.uso.tokens_saida
                resp.custo_usd += r.uso.custo_usd
                if not r.tool_calls or limite:
                    texto_final = (r.texto or "").strip() or None
                    if texto_final is None:
                        resp.motivo_segura = "resposta_vazia"
                    break
                novas.append(r.mensagem_assistente())
                for call in r.tool_calls:
                    chamadas += 1
                    t0 = time.perf_counter()
                    resultado = self.toolbox.executar(call.nome, call.argumentos, conversa.sessao)
                    erro = resultado.get("erro") if isinstance(resultado, dict) else None
                    erros += bool(erro)
                    resp.rastro.append(EventoTool(call.nome, mascarar_texto(call.argumentos),
                                                  mascarar_texto(_resumir(resultado)),
                                                  int((time.perf_counter() - t0) * 1000), erro))
                    novas.append({"role": "tool", "tool_call_id": call.id,
                                  "content": json.dumps(resultado, ensure_ascii=False)})
                if erros >= 2:            # erro de tool volta ao modelo uma vez; o segundo encerra (RN-26)
                    resp.motivo_segura = "erros_de_tool"
                    break
        except LLMIndisponivel as e:
            log.warning("LLM indisponível: %s", mascarar_texto(str(e)))
            resp.motivo_segura = "llm_indisponivel"

        if texto_final is None:
            resp.segura = True
            resp.motivo_segura = resp.motivo_segura or "sem_resposta"
            texto_final = RESPOSTA_SEGURA
            novas = novas[:1]             # não guarda chamadas pela metade
        novas.append({"role": "assistant", "content": texto_final})
        conversa.historico.extend(_mascarar_mensagem(m) for m in novas)

        resp.texto = f"{texto_final}\n\n{AVISO_PRIVACIDADE}" if primeira else texto_final
        resp.latencia_s = time.perf_counter() - inicio
        self._registrar_log(conversa, resp)
        return resp

    def _registrar_log(self, conversa: Conversa, resp: RespostaTurno) -> None:
        log.info(json.dumps({
            "evento": "turno", "conversa": conversa.id, "turno": conversa.turnos, "modelo": self.llm.modelo,
            "tools": [{"tool": e.tool, "args": e.argumentos, "ms": e.duracao_ms, "erro": e.erro} for e in resp.rastro],
            "tokens_entrada": resp.tokens_entrada, "tokens_saida": resp.tokens_saida,
            "custo_usd": round(resp.custo_usd, 6), "latencia_s": round(resp.latencia_s, 2),
            "segura": resp.segura, "motivo": resp.motivo_segura,
        }, ensure_ascii=False))
