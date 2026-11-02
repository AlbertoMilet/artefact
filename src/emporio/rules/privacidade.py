"""Prazos da LGPD e filtro do expurgo (SPEC-012). Funções puras: sem arquivo, banco ou relógio próprio."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime, timedelta

from emporio.rules.horario import FUSO

PRAZO_RETENCAO_DIAS = 90            # RL-01: cada mensagem e cada linha de log vive no máximo isso
PRAZO_RESPOSTA_TITULAR_DIAS = 15    # RL-04: art. 19, II, da LGPD
PRAZO_AUDITORIA_DIAS = 365          # RL-11: registros de acesso, para responsabilização (art. 6º, X)
INTERVALO_EXPURGO_S = 3600          # RL-12: com o painel no ar, o expurgo roda de novo a cada hora

_DATA_NO_INICIO = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")


def expirado(registrado_em: str | None, agora: datetime, dias: int = PRAZO_RETENCAO_DIAS) -> bool:
    """True quando o registro passou do prazo. Sem data ou com data ilegível, conta como expirado (RL-02)."""
    if not registrado_em:
        return True
    try:
        quando = datetime.fromisoformat(registrado_em)
    except (TypeError, ValueError):
        return True
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=FUSO)
    return agora - quando > timedelta(days=dias)


def linhas_mantidas(linhas: Iterable[str], agora: datetime, dias: int = PRAZO_RETENCAO_DIAS,
                    apagar_conversa: str | None = None) -> list[str]:
    """Linhas de um log JSONL que continuam depois do expurgo (RL-01, RL-02) ou de apagar uma conversa (RL-05)."""
    mantidas = []
    for linha in linhas:
        if not linha.strip():
            continue
        try:
            item = json.loads(linha)
        except json.JSONDecodeError:
            continue                                   # ilegível: não dá para saber de quem é nem quando
        if not isinstance(item, dict):
            continue
        if apagar_conversa is not None and item.get("conversa") == apagar_conversa:
            continue
        if expirado(item.get("registrado_em"), agora, dias):
            continue
        mantidas.append(linha if linha.endswith("\n") else linha + "\n")
    return mantidas


def linhas_texto_mantidas(linhas: Iterable[str], agora: datetime, dias: int = PRAZO_RETENCAO_DIAS) -> list[str]:
    """Log de texto (`avisos.log`): cada registro começa com data e hora; as linhas seguintes sem data
    (traceback) seguem o registro. Registro sem data no início conta como expirado (RL-02)."""
    mantidas, mantendo = [], False
    for linha in linhas:
        m = _DATA_NO_INICIO.match(linha)
        if m:
            mantendo = not expirado(m.group(1).replace(" ", "T"), agora, dias)
        if mantendo:
            mantidas.append(linha if linha.endswith("\n") else linha + "\n")
    return mantidas
