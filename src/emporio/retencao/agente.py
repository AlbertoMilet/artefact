"""Agente de retenção: entra em cena só no SILÊNCIO do cliente (SPEC-002).

Em cada avaliação vencida:
1. bloqueios em código (politica.bloqueio): pedido para parar, janela, tetos, intervalo, madrugada;
2. o LLM decide ENVIAR / ESPERAR / PARAR em JSON validado, a partir do histórico já mascarado;
3. a mensagem é conferida em código (sem R$, sem promessa, sem repetição) e os bloqueios são
   conferidos de novo antes do envio.
Saída inválida do modelo vira ESPERAR, nunca envio (RI-10).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Literal

from pydantic import BaseModel, ValidationError, field_validator

from emporio.llm.base import LLMClient, LLMIndisponivel
from emporio.retencao import janela, politica
from emporio.retencao.modelos import AGENDAVEIS, Acompanhamento, Status
from emporio.retencao.politica import ConfigRetencao
from emporio.rules.horario import FUSO
from emporio.rules.verificacao import mascarar_texto

log = logging.getLogger("emporio.retencao")

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
CAUDA = 12            # mensagens recentes no contexto
MAX_CHARS_MSG = 300

PROMPT = """Você é o agente de retenção da Empório da Música, loja de instrumentos musicais em Campo Grande/MS.
Você recebe um JSON com uma conversa de WhatsApp em que o cliente parou de responder: as últimas mensagens,
há quanto tempo ele está em silêncio, os lembretes já enviados e quanto falta para fechar a janela de 24 h.

Objetivo: retomar conversas interrompidas quando houver uma razão útil e contextual, no tom da loja
(informal mas profissional, acolhedor, como uma amiga que entende de música). Não envie mensagem só para
provocar resposta. O lembrete serve SÓ para continuar o atendimento que o próprio cliente começou: nada de
promoção, oferta, novidade ou lançamento (isso exige consentimento do cliente).

Decida uma ação:
- "ENVIAR": há algo útil a dizer para retomar o ponto exato onde o cliente parou (uma dúvida sobre os produtos
  mostrados, a informação que a Lia pediu e ficou sem resposta, a confirmação de um registro). Escreva em
  "mensagem": português do Brasil, no máximo 50 palavras e no máximo uma pergunta, assinando como a Lia só se
  for natural.
- "ESPERAR": ainda não é hora (ele avisou que volta depois, ou não há nada útil agora). "mensagem" = null.
- "PARAR": não faz sentido insistir (assunto resolvido, agradeceu e encerrou, desinteresse, recusa, já houve
  tentativas suficientes). "mensagem" = null.

Regras da mensagem (o sistema recusa a mensagem que as violar):
- não escreva nenhum valor em reais, nem preço, parcela, estoque, disponibilidade, entrega, frete ou prazo, nem
  mesmo o orçamento que o cliente citou ("até R$ 1.000"): você não consultou o sistema agora;
- não ofereça desconto, reserva, cancelamento nem nada que dependa da equipe;
- não repita um lembrete de "lembretes_anteriores" nem pergunta já respondida;
- sem pressão nem urgência artificial.

Momento do lembrete: as avaliações acontecem em 30 min, 4 h e 21 h de silêncio ("proxima_avaliacao_padrao_min"
diz quando será a próxima se você esperar). Se a última mensagem foi da Lia com uma pergunta ou uma oferta de
ajuda e o cliente sumiu sem dizer que voltaria, um lembrete leve já na primeira avaliação é adequado: retome a
pergunta de outro jeito, sem repetir as mesmas palavras.

Leia a última mensagem do cliente: "depois eu vejo", "estou no trabalho", "vou pensar" indicam que ele volta
depois: prefira ESPERAR e, se houver referência de horário, use "agora_local" para sugerir
"proxima_avaliacao_min". "Obrigado, era isso", "valeu" depois de resolvido: PARAR.
Quando "ultima_tentativa" for true, a janela está acabando: envie só se fizer sentido para este atendimento.

Responda SOMENTE com um objeto JSON, sem markdown:
{"acao": "ENVIAR" | "ESPERAR" | "PARAR", "mensagem": string ou null, "proxima_avaliacao_min": inteiro ou null,
 "motivo": "uma frase, uso interno"}"""

LEMBRETES_FIXOS = [   # modo demonstração (sem modelo de linguagem)
    "Oi! Ficou alguma dúvida? Se quiser, sigo te ajudando por aqui. 🎸",
    "Passando só para lembrar que estou por aqui, caso precise de algo da Empório da Música.",
]


class Decisao(BaseModel):
    acao: Literal["ENVIAR", "ESPERAR", "PARAR"]
    mensagem: str | None = None
    proxima_avaliacao_min: int | None = None
    motivo: str = ""

    @field_validator("acao", mode="before")
    @classmethod
    def _acao(cls, v):
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("proxima_avaliacao_min", mode="before")
    @classmethod
    def _minutos(cls, v):
        """Sugestão fora do intervalo não invalida a decisão: é limitada a 1..1440 (a agenda aplica os limites)."""
        if v in (None, ""):
            return None
        try:
            return min(max(int(float(v)), 1), 1440)
        except (TypeError, ValueError, OverflowError):     # "Infinity", "NaN", texto
            return None


@dataclass(frozen=True)
class Avaliacao:
    """Resultado de uma avaliação, para o CLI (--debug) e o log."""
    quando: datetime
    acao: str            # ENVIAR, ESPERAR, PARAR ou BLOQUEADO
    motivo: str
    mensagem: str | None = None
    status: str = ""


def _json(texto: str | None) -> dict | None:
    if not texto:
        return None
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip(), flags=re.S)
    m = re.search(r"\{.*\}", t, re.S)
    try:
        return json.loads(m.group() if m else t)
    except (json.JSONDecodeError, AttributeError):
        return None


class Retencao:
    def __init__(self, llm: LLMClient, cfg: ConfigRetencao, relogio: Callable[[], datetime] | None = None):
        self.llm = llm
        self.cfg = cfg
        self.relogio = relogio      # relido antes do envio: a chamada ao modelo leva tempo (revisão do Codex)
        self.modo_fixo = llm.modelo.startswith("demo/")

    # ------------------------------------------------------------ ganchos do agente

    def ao_receber(self, ac: Acompanhamento, texto: str, agora: datetime) -> None:
        """Mensagem do cliente: reancora a janela e zera o ciclo deste silêncio."""
        ac.ultima_msg_cliente = agora
        if politica.quer_parar(texto):
            ac.optou_sair = True
        if ac.optou_sair:
            ac.status, ac.motivo, ac.proxima_avaliacao = Status.ENCERRADO, "pediu_para_parar", None
            return
        ac.status, ac.motivo = Status.ATIVO, ""
        ac.avaliacoes = 0
        ac.lembretes = []
        if self.cfg.ativa:
            politica.agendar(ac, self.cfg, agora)

    def ao_responder(self, ac: Acompanhamento, agora: datetime, equipe_assumiu: bool = False) -> None:
        ac.ultima_msg_auto = agora
        if equipe_assumiu and ac.status in AGENDAVEIS:      # RI-11
            ac.status, ac.motivo, ac.proxima_avaliacao = Status.ENCERRADO, "encaminhado_equipe", None

    # ------------------------------------------------------------ avaliação

    def vencida(self, ac: Acompanhamento, agora: datetime) -> bool:
        return (self.cfg.ativa and ac.status in AGENDAVEIS and ac.proxima_avaliacao is not None
                and ac.proxima_avaliacao <= agora)

    def avaliar(self, ac: Acompanhamento, historico: list[dict], agora: datetime) -> Avaliacao | None:
        """Avalia se vencida. Devolve a avaliação (com a mensagem, se enviar) ou None."""
        if not self.vencida(ac, agora):
            return None
        b = politica.bloqueio(ac, self.cfg, agora)
        if b is not None:
            return self._aplicar_bloqueio(ac, b, agora)
        ac.avaliacoes += 1
        ultima = politica.ultima_tentativa(ac, self.cfg, agora)
        decisao = self._decidir(ac, historico, agora, ultima)

        if decisao.acao == "PARAR":
            ac.status, ac.motivo, ac.proxima_avaliacao = Status.ENCERRADO, f"parar: {decisao.motivo}", None
            return self._registro(ac, agora, "PARAR", decisao.motivo)
        if decisao.acao == "ENVIAR":
            problemas = politica.conferir_lembrete(decisao.mensagem, ac.lembretes)
            if self.relogio is not None:                         # horário efetivo do envio
                agora = max(agora, self.relogio())
            b = politica.bloqueio(ac, self.cfg, agora, antes_do_modelo=False)   # de novo antes do envio
            if b is not None:
                return self._aplicar_bloqueio(ac, b, agora)
            if problemas:
                ac.status = Status.AGUARDANDO if ac.status == Status.ATIVO else ac.status
                politica.agendar(ac, self.cfg, agora)
                return self._registro(ac, agora, "ESPERAR", f"lembrete recusado: {', '.join(problemas)}")
            msg = mascarar_texto(decisao.mensagem.strip())
            ac.lembretes.append(msg)
            ac.total_lembretes += 1
            ac.ultima_msg_auto = agora
            ac.status = Status.ULTIMA if ultima else Status.LEMBRETE
            historico.append({"role": "assistant", "content": msg})
            if ultima:      # depois da última tentativa, a próxima avaliação só registra o fechamento da janela
                ac.proxima_avaliacao = politica.limite_envio(ac, self.cfg)
            else:
                politica.agendar(ac, self.cfg, agora)
            return self._registro(ac, agora, "ENVIAR", decisao.motivo, msg)
        # ESPERAR
        if ac.status == Status.ATIVO:
            ac.status = Status.AGUARDANDO
        pedido = agora + timedelta(minutes=decisao.proxima_avaliacao_min) if decisao.proxima_avaliacao_min else None
        politica.agendar(ac, self.cfg, agora, pedido)
        return self._registro(ac, agora, "ESPERAR", decisao.motivo)

    def _aplicar_bloqueio(self, ac: Acompanhamento, b: politica.Bloqueio, agora: datetime) -> Avaliacao:
        if b.terminal:
            ac.status, ac.motivo, ac.proxima_avaliacao = b.status, b.motivo, None
        else:
            politica.agendar(ac, self.cfg, agora, b.tentar_em)
        return self._registro(ac, agora, "BLOQUEADO", b.motivo)

    def _registro(self, ac: Acompanhamento, agora: datetime, acao: str, motivo: str,
                  mensagem: str | None = None) -> Avaliacao:
        motivo = mascarar_texto(motivo or "")[:300]          # o motivo vem do modelo: nunca contato em claro
        av = Avaliacao(agora, acao, motivo, mensagem, ac.status.value)
        log.info(json.dumps({"evento": "retencao", "quando": agora.isoformat(), "acao": acao, "motivo": motivo,
                             "status": ac.status.value, "lembretes": len(ac.lembretes)}, ensure_ascii=False))
        return av

    # ------------------------------------------------------------ decisão

    def _decidir(self, ac: Acompanhamento, historico: list[dict], agora: datetime, ultima: bool) -> Decisao:
        if self.modo_fixo:
            if len(ac.lembretes) < len(LEMBRETES_FIXOS):
                return Decisao(acao="ENVIAR", mensagem=LEMBRETES_FIXOS[len(ac.lembretes)], motivo="modo demonstração")
            return Decisao(acao="PARAR", motivo="modo demonstração: lembretes esgotados")
        contexto = self._contexto(ac, historico, agora, ultima)
        mensagens = [{"role": "system", "content": PROMPT},
                     {"role": "user", "content": json.dumps(contexto, ensure_ascii=False)}]
        try:
            r = self.llm.completar(mensagens, [], sem_raciocinio=True)
            if not (r.texto or "").strip():        # resposta vazia ocasional do modelo: uma nova tentativa
                r = self.llm.completar(mensagens, [], sem_raciocinio=True)
        except LLMIndisponivel as e:
            return Decisao(acao="ESPERAR", motivo=f"llm_indisponivel: {mascarar_texto(str(e))[:120]}")
        dados = _json(r.texto)
        try:
            return Decisao.model_validate(dados)
        except (ValidationError, ValueError, TypeError):
            trecho = mascarar_texto(" ".join((r.texto or "<vazio>").split()))[:100]
            return Decisao(acao="ESPERAR", motivo=f"saida_invalida_do_modelo: {trecho!r}")

    def _contexto(self, ac: Acompanhamento, historico: list[dict], agora: datetime, ultima: bool) -> dict:
        # o histórico já vem mascarado; mascarar de novo na entrada do contexto é a segunda barreira (RI-13)
        conversa = [{"de": "cliente" if m["role"] == "user" else "Lia",
                     "texto": mascarar_texto(m.get("content") or "")[:MAX_CHARS_MSG]}
                    for m in historico if m["role"] in ("user", "assistant") and m.get("content")][-CAUDA:]
        local = agora.astimezone(FUSO)
        silencio = int((agora - ac.ultima_msg_cliente).total_seconds() // 60) if ac.ultima_msg_cliente else None
        fim = janela.expira_em(ac.ultima_msg_cliente)
        padrao = sorted(m for m in self.cfg.avaliacoes_min if silencio is not None and m > silencio)
        return {
            "proxima_avaliacao_padrao_min": (padrao[0] - silencio) if padrao else None,
            "agora_local": f"{DIAS[local.weekday()]} {local:%d/%m %H:%M}",
            "minutos_de_silencio": silencio,
            "horas_para_fechar_a_janela": round((fim - agora).total_seconds() / 3600, 1) if fim else None,
            "ultima_tentativa": ultima,
            "lembretes_anteriores": ac.lembretes,
            "conversa_recente": conversa,
        }

    # ------------------------------------------------------------ varredura

    def varrer(self, conversas: list, agora: datetime) -> list[tuple[object, Avaliacao]]:
        """Avalia todas as conversas vencidas (o agendador de produção chamaria isto a cada minuto)."""
        out = []
        for c in conversas:
            av = self.avaliar(c.acompanhamento, c.historico, agora)
            if av is not None:
                out.append((c, av))
        return out
