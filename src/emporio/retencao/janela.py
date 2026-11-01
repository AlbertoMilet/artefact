"""Janela de atendimento de 24 h do WhatsApp: fonte única da regra (SPEC-002 RI-01).

Mensagem livre só vale até 24 h depois da última mensagem DO CLIENTE. Resposta ou lembrete da loja não
reabre nada. (No Saúde Legal, um lembrete automático lido como "janela aberta" levou a um engano no
painel: por isso a âncora é só a mensagem do cliente.)
"""

from __future__ import annotations

from datetime import datetime, timedelta

from emporio.rules.horario import FUSO

DURACAO = timedelta(hours=24)
MARGEM_ENTREGA = timedelta(seconds=60)    # enviar em cima do limite arrisca a recusa do provedor


def expira_em(ultima_msg_cliente: datetime | None) -> datetime | None:
    return None if ultima_msg_cliente is None else ultima_msg_cliente + DURACAO


def aberta(ultima_msg_cliente: datetime | None, agora: datetime) -> bool:
    """Sem mensagem do cliente não há janela."""
    if ultima_msg_cliente is None:
        return False
    return agora - ultima_msg_cliente <= DURACAO - MARGEM_ENTREGA


def rotulo(ultima_msg_cliente: datetime | None, agora: datetime) -> str:
    if ultima_msg_cliente is None:
        return "Sem janela (o cliente ainda não escreveu)"
    fim = expira_em(ultima_msg_cliente).astimezone(FUSO)
    if aberta(ultima_msg_cliente, agora):
        return f"Janela aberta até {fim:%d/%m %H:%M}"
    return f"Janela encerrada desde {fim:%d/%m %H:%M}: só uma nova mensagem do cliente a reabre"
