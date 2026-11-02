"""Limites contra abuso (SPEC-013): mensagens por conversa e tentativas de verificação. Funções puras."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from emporio.rules.horario import FUSO

MENSAGENS_POR_MINUTO = 10          # RS-05
MENSAGENS_POR_DIA = 200            # RS-05
TENTATIVAS_VERIFICACAO = 5         # RS-06: verificações de pedido que não conferem, por sessão
JANELA_AUDITORIA_LEITURA_S = 300   # RS-08: um "abriu" por usuário e conversa a cada 5 minutos


def _quando(iso: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=FUSO)


def passou_do_limite(anteriores: Iterable[str], agora: datetime, por_minuto: int = MENSAGENS_POR_MINUTO,
                     por_dia: int = MENSAGENS_POR_DIA) -> bool:
    """True se uma nova mensagem do cliente passaria do limite (RS-05). `anteriores`: horários ISO das
    mensagens já recebidas do cliente nesta conversa."""
    datas = [d for d in map(_quando, anteriores) if d is not None and d <= agora]
    no_minuto = sum(1 for d in datas if agora - d < timedelta(seconds=60))
    no_dia = sum(1 for d in datas if agora - d < timedelta(hours=24))
    return no_minuto >= por_minuto or no_dia >= por_dia
