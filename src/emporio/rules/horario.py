"""Horário de funcionamento e relógio injetável (RN-17; §2; lição do ALJ: `now` injetado).

Feriados: nacionais fixos, Sexta-feira Santa (móvel), o estadual de MS e os municipais de Campo
Grande. A lista é configurável: o manual não a define e horários especiais (Black Friday, Natal)
dependem de comunicado da loja. Conferir com o calendário oficial antes de produção.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Campo_Grande")

# dia da semana (0 = segunda) -> (abre, fecha); ausente = fechado
EXPEDIENTE: dict[int, tuple[time, time]] = {
    **{d: (time(9), time(18)) for d in range(5)},
    5: (time(9), time(13)),
}

FERIADOS_FIXOS = {
    (1, 1): "Confraternização Universal",
    (4, 21): "Tiradentes",
    (5, 1): "Dia do Trabalho",
    (6, 13): "Santo Antônio (padroeiro de Campo Grande)",
    (8, 26): "Aniversário de Campo Grande",
    (9, 7): "Independência",
    (10, 11): "Criação do Estado de Mato Grosso do Sul",
    (10, 12): "Nossa Senhora Aparecida",
    (11, 2): "Finados",
    (11, 15): "Proclamação da República",
    (11, 20): "Consciência Negra",
    (12, 25): "Natal",
}


def pascoa(ano: int) -> date:
    """Algoritmo de Meeus/Jones/Butcher (calendário gregoriano)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


@dataclass(frozen=True)
class Calendario:
    fixos: dict[tuple[int, int], str] = field(default_factory=lambda: dict(FERIADOS_FIXOS))
    extras: dict[date, str] = field(default_factory=dict)   # feriados avulsos configuráveis

    def feriado(self, d: date) -> str | None:
        if d in self.extras:
            return self.extras[d]
        if (d.month, d.day) in self.fixos:
            return self.fixos[(d.month, d.day)]
        if d == pascoa(d.year) - timedelta(days=2):
            return "Sexta-feira Santa"
        return None


Relogio = Callable[[], datetime]


def relogio_real() -> datetime:
    return datetime.now(FUSO)


def relogio_fixo(momento: datetime) -> Relogio:
    fixo = momento if momento.tzinfo else momento.replace(tzinfo=FUSO)
    return lambda: fixo


def _local(dt: datetime) -> datetime:
    return dt.astimezone(FUSO) if dt.tzinfo else dt.replace(tzinfo=FUSO)


def aberto_agora(agora: datetime, calendario: Calendario = Calendario()) -> bool:
    dt = _local(agora)
    if calendario.feriado(dt.date()) or dt.weekday() not in EXPEDIENTE:
        return False
    abre, fecha = EXPEDIENTE[dt.weekday()]
    return abre <= dt.time() < fecha


def proxima_abertura(agora: datetime, calendario: Calendario = Calendario()) -> datetime:
    """Próximo instante de abertura estritamente depois de `agora` (ou o próprio, se já aberto)."""
    dt = _local(agora)
    if aberto_agora(dt, calendario):
        return dt
    for i in range(0, 15):
        d = dt.date() + timedelta(days=i)
        if calendario.feriado(d) or d.weekday() not in EXPEDIENTE:
            continue
        abertura = datetime.combine(d, EXPEDIENTE[d.weekday()][0], tzinfo=FUSO)
        if abertura > dt:
            return abertura
    raise RuntimeError("nenhuma abertura nos próximos 15 dias: confira o calendário")
