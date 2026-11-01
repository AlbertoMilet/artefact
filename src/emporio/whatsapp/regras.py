"""Regras puras da conexão do WhatsApp (SPEC-004 RW-01 a RW-05, RW-09).

Os limites de 5 tentativas por código e 60 s para pedir outro são política LOCAL (proteção contra uso
excessivo), não limites oficiais da Meta, que tem os próprios.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlparse

ESCOPOS = ("whatsapp_business_management", "whatsapp_business_messaging", "business_management")
ESCOPOS_OBRIGATORIOS = ("whatsapp_business_management", "whatsapp_business_messaging")
TENTATIVAS_POR_CODIGO = 5
INTERVALO_NOVO_CODIGO = timedelta(seconds=60)
HOSTS_LOCAIS = {"localhost", "127.0.0.1"}


def novo_state() -> str:
    """Valor aleatório do parâmetro `state` do OAuth (RW-01)."""
    return secrets.token_urlsafe(24)


def state_confere(esperado: str, recebido: str | None) -> bool:
    return bool(recebido) and secrets.compare_digest(esperado, recebido)


def validar_redirect(uri: str) -> tuple[str, int, str]:
    """RW-09: o retorno do OAuth só pode ser http://localhost:PORTA/caminho (servidor local em loopback)."""
    u = urlparse(uri or "")
    if u.scheme != "http" or (u.hostname or "") not in HOSTS_LOCAIS or not u.port or not u.path.startswith("/"):
        raise ValueError("META_REDIRECT_URI deve ser http://localhost:PORTA/caminho (ex.: http://localhost:8765/callback)")
    return u.hostname, u.port, u.path


def normalizar_numero_br(texto: str) -> tuple[str, str]:
    """'(81) 99999-0000' -> ('55', '81999990000'). Aceita +55, 55, com ou sem máscara (RW-03)."""
    d = re.sub(r"\D", "", texto or "")
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) not in (10, 11) or d[0] == "0":
        raise ValueError("número inválido: informe DDD + número, por exemplo (67) 99999-0000")
    if len(d) == 11 and d[2] != "9":
        raise ValueError("celular com 11 dígitos deve ter o 9 depois do DDD")
    return "55", d


def validar_codigo(codigo: str) -> str:
    c = re.sub(r"\D", "", codigo or "")
    if len(c) != 6:
        raise ValueError("o código de confirmação tem 6 dígitos")
    return c


def validar_pin(pin: str) -> str:
    if not re.fullmatch(r"\d{6}", pin or ""):
        raise ValueError("o PIN de duas etapas tem exatamente 6 dígitos")
    return pin


def escopos_faltando(escopos: list[str]) -> list[str]:
    return [e for e in ESCOPOS_OBRIGATORIOS if e not in set(escopos or [])]


def pode_pedir_codigo(ultimo_pedido: datetime | None, agora: datetime) -> tuple[bool, int]:
    """(pode, segundos para esperar)."""
    if ultimo_pedido is None:
        return True, 0
    falta = INTERVALO_NOVO_CODIGO - (agora - ultimo_pedido)
    return (falta <= timedelta(0)), max(0, int(falta.total_seconds() + 0.999))
