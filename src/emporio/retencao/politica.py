"""Regras determinísticas da retenção: agenda, bloqueios, pedido para parar e conferência do lembrete.

Funções puras (SPEC-002 RI-02 a RI-09). Os bloqueios valem antes de consultar o modelo e de novo
antes do envio: o modelo decide SE fala e O QUE fala; o código decide se PODE falar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from emporio.data.normalize import normalizar
from emporio.retencao import janela
from emporio.retencao.modelos import Acompanhamento, Status
from emporio.rules.horario import FUSO


@dataclass(frozen=True)
class ConfigRetencao:
    ativa: bool = False                                  # RI-14: desligada por padrão
    avaliacoes_min: tuple[int, ...] = (30, 240, 1260)    # RI-03: 30 min, 4 h, 21 h de silêncio
    max_lembretes: int = 3                               # RI-04
    max_avaliacoes: int = 6
    intervalo_min: int = 20                              # RI-05
    ultima_tentativa_h: float = 4                        # RI-09
    margem_envio_min: int = 30                           # RI-02
    silencio_inicio: int = 21                            # RI-06: 21h às 8h, horário de Campo Grande
    silencio_fim: int = 8


# ---------------------------------------------------------------- pedido para parar (RI-07)

FRASES_PARAR = (
    "nao quero mais receber", "nao quero receber mensagem", "nao me mande", "nao me mandem",
    "nao mande mais", "nao mandem mais", "pare de me mandar", "pare de mandar", "parem de mandar",
    "para de mandar", "para de me mandar", "nao me envie", "nao envie mais", "nao me chame mais",
    "nao entre mais em contato", "nao me procure", "sair da lista", "me tire da lista", "me tira da lista",
    "descadastrar", "descadastre",
)
EXATAS_PARAR = ("pare", "parar", "stop", "chega")


def quer_parar(texto: str) -> bool:
    """Determinístico de propósito: é o único "não" que não pode depender do modelo entender."""
    t = normalizar(texto)
    return bool(t) and (t in EXATAS_PARAR or any(f in t for f in FRASES_PARAR))


# ---------------------------------------------------------------- tempo

def limite_envio(ac: Acompanhamento, cfg: ConfigRetencao) -> datetime | None:
    fim = janela.expira_em(ac.ultima_msg_cliente)
    return None if fim is None else fim - timedelta(minutes=cfg.margem_envio_min)


def em_silencio(dt: datetime, cfg: ConfigRetencao) -> bool:
    h = dt.astimezone(FUSO).hour
    return h >= cfg.silencio_inicio or h < cfg.silencio_fim


def fim_do_silencio(dt: datetime, cfg: ConfigRetencao) -> datetime:
    local = dt.astimezone(FUSO)
    dia = local.date() if local.hour < cfg.silencio_fim else local.date() + timedelta(days=1)
    return datetime.combine(dia, time(cfg.silencio_fim), tzinfo=FUSO)


def ultima_tentativa(ac: Acompanhamento, cfg: ConfigRetencao, agora: datetime) -> bool:
    lim = limite_envio(ac, cfg)
    return lim is not None and lim - agora <= timedelta(hours=cfg.ultima_tentativa_h)


def agendar(ac: Acompanhamento, cfg: ConfigRetencao, agora: datetime, pedido: datetime | None = None) -> None:
    """Próxima avaliação: o horário pedido (modelo ou bloqueio) ou o próximo momento padrão, fora do
    horário silencioso e dentro da janela. Sem horário possível, a próxima avaliação é o próprio limite
    de envio, que então registra janela_fechada."""
    lim = limite_envio(ac, cfg)
    if lim is None:
        ac.proxima_avaliacao = None
        return
    minimo = timedelta(minutes=max(cfg.intervalo_min, 1))
    if pedido is not None:
        candidato = max(pedido, agora + minimo)
    else:
        futuros = [ac.ultima_msg_cliente + timedelta(minutes=m) for m in sorted(cfg.avaliacoes_min)]
        futuros = [f for f in futuros if f > agora]
        candidato = futuros[0] if futuros else None
    if candidato is not None and em_silencio(candidato, cfg):
        candidato = fim_do_silencio(candidato, cfg)
    ac.proxima_avaliacao = candidato if candidato is not None and candidato < lim else lim


# ---------------------------------------------------------------- bloqueios

@dataclass(frozen=True)
class Bloqueio:
    status: Status
    motivo: str
    terminal: bool = True
    tentar_em: datetime | None = None


def bloqueio(ac: Acompanhamento, cfg: ConfigRetencao, agora: datetime) -> Bloqueio | None:
    if ac.optou_sair:
        return Bloqueio(Status.ENCERRADO, "pediu_para_parar")
    lim = limite_envio(ac, cfg)
    if lim is None:
        return Bloqueio(Status.ENCERRADO, "sem_janela")
    if agora >= lim:
        return Bloqueio(Status.JANELA_FECHADA, "janela_fechada")
    if len(ac.lembretes) >= cfg.max_lembretes:
        return Bloqueio(Status.ENCERRADO, "teto_de_lembretes")
    if ac.avaliacoes >= cfg.max_avaliacoes:
        return Bloqueio(Status.ENCERRADO, "teto_de_avaliacoes")
    intervalo = timedelta(minutes=cfg.intervalo_min)
    if ac.ultima_msg_auto and agora - ac.ultima_msg_auto < intervalo:
        return Bloqueio(ac.status, "mensagem_automatica_recente", False, ac.ultima_msg_auto + intervalo)
    if em_silencio(agora, cfg):
        return Bloqueio(ac.status, "horario_silencioso", False, fim_do_silencio(agora, cfg))
    return None


# ---------------------------------------------------------------- conferência do lembrete (RI-08)

MAX_PALAVRAS = 60
MAX_CARACTERES = 600
_RE_VALOR = re.compile(r"R\$|\d+\s*reais|\d+[.,]\d{2}\b", re.I)
_RE_PROMESSA = re.compile(r"reserv|separ(ei|ado|amos)|desconto|cupom|garant(o|imos)|prometo|cancel", re.I)


def conferir_lembrete(texto: str | None, anteriores: list[str]) -> list[str]:
    """Problemas que impedem o envio. Lista vazia = pode enviar."""
    if not texto or not texto.strip():
        return ["vazio"]
    t = texto.strip()
    problemas = []
    if len(t.split()) > MAX_PALAVRAS or len(t) > MAX_CARACTERES:
        problemas.append("longo_demais")
    if t.count("?") > 1:
        problemas.append("mais_de_uma_pergunta")
    if _RE_VALOR.search(t):
        problemas.append("contem_valor")
    if m := _RE_PROMESSA.search(t):
        problemas.append(f"promessa:{m.group()}")
    if any(normalizar(t) == normalizar(a) for a in anteriores):
        problemas.append("repetido")
    return problemas
