"""Acompanhamento de inatividade, um por conversa (SPEC-002 §4.2).

Separado do estado da conversa, como no Saúde Legal: a conversa diz o que foi falado; o
acompanhamento diz se o cliente sumiu, quando olhar de novo e o que já foi tentado neste silêncio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Status(str, Enum):
    ATIVO = "ativo"                        # cliente acabou de falar; primeira avaliação agendada
    AGUARDANDO = "aguardando"              # avaliado, nada enviado ainda
    LEMBRETE = "lembrete_enviado"          # ao menos um lembrete neste silêncio
    ULTIMA = "ultima_tentativa"            # lembrete enviado com a janela acabando
    JANELA_FECHADA = "janela_fechada"      # terminal até o cliente voltar
    ENCERRADO = "encerrado"                # terminal: pediu para parar, teto, resolvido, equipe assumiu


AGENDAVEIS = {Status.ATIVO, Status.AGUARDANDO, Status.LEMBRETE, Status.ULTIMA}


@dataclass
class Acompanhamento:
    status: Status = Status.ATIVO
    ultima_msg_cliente: datetime | None = None    # âncora da janela (RI-01)
    ultima_msg_auto: datetime | None = None       # resposta ou lembrete da Lia (RI-05)
    proxima_avaliacao: datetime | None = None
    avaliacoes: int = 0                           # deste silêncio
    lembretes: list[str] = field(default_factory=list)   # textos deste silêncio (não repetir)
    total_lembretes: int = 0                      # da conversa inteira
    optou_sair: bool = False                      # permanente nesta conversa (RI-07)
    motivo: str = ""
