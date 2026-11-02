"""Fotos, áudios, vídeos e documentos no chat (SPEC-014). Funções puras.

O agente é de texto: a mídia vira um marcador e nunca chega ao modelo nem ao disco (RM-02).
"""

from __future__ import annotations

TIPOS = {                         # tipo -> (como aparece no marcador, o que a Lia não consegue fazer)
    "foto": ("uma foto", "ver fotos"),
    "audio": ("um áudio", "ouvir áudios"),
    "video": ("um vídeo", "assistir vídeos"),
    "documento": ("um documento", "abrir documentos"),
}


def validar(tipo: str) -> str:
    """RM-01: só os quatro tipos; devolve o tipo normalizado ou levanta ValueError."""
    t = (tipo or "").strip().lower().replace("á", "a").replace("í", "i")
    if t not in TIPOS:
        raise ValueError(f"tipo de mídia desconhecido: {tipo!r} (use foto, audio, video ou documento)")
    return t


def marcador(tipo: str) -> str:
    return f"[cliente enviou {TIPOS[validar(tipo)][0]}]"


def resposta(tipo: str, telefone_loja: str) -> str:
    """RM-03: texto fixo, sem LLM."""
    nao_consigo = TIPOS[validar(tipo)][1]
    return (f"Por enquanto eu só consigo ler mensagens de texto, então não consigo {nao_consigo}. "
            "Pode me escrever o que você precisa? Se for um defeito ou uma troca, eu registro a sua solicitação "
            f"ou passo para a nossa equipe, que atende pelo telefone/WhatsApp {telefone_loja}.")


def precisa_da_equipe(pedido_verificado: int | None, registro_proposto: dict | None, registros: list) -> bool:
    """RM-05: com pedido ou solicitação em andamento, o arquivo provavelmente importa para a equipe."""
    return pedido_verificado is not None or registro_proposto is not None or bool(registros)
