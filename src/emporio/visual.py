"""Identidade visual do terminal, a partir da logo da marca (a do painel é `web/static/marca.png`).

Paleta extraída da logo: verde-água da palheta-balão (#00AE9E), verde-petróleo da sombra (#017970) e
azul-marinho da marca (#071527). Os demais tons são neutros ou de sinal (alerta, erro).

- Cor só em terminal interativo e sem NO_COLOR; saída redirecionada (testes, pipes) sai sem ANSI.
- 24 bits quando o terminal anuncia (COLORTERM, Windows Terminal, VS Code); senão, a cor mais
  próxima da paleta de 256.
- EMPORIO_TEMA=claro troca os tons claros por versões escuras, para manter o contraste em fundo branco.
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap

# papel -> ((r, g, b) no tema escuro, índice 256, (r, g, b) no tema claro, índice 256 claro)
PALETA = {
    "marca": ((0x00, 0xAE, 0x9E), 37, (0x01, 0x79, 0x70), 30),       # verde-água: banner, Lia, destaques
    "trilho": ((0x01, 0x79, 0x70), 30, (0x01, 0x79, 0x70), 30),      # verde-petróleo: trilho do --debug
    "fundo": ((0x07, 0x15, 0x27), 17, (0x07, 0x15, 0x27), 17),       # azul-marinho: a nota dentro da palheta
    "suave": ((0x8A, 0x9B, 0xB4), 103, (0x5B, 0x6B, 0x82), 60),      # cinza-azulado: sistema, rastro, dicas
    "alerta": ((0xF2, 0xA9, 0x3B), 214, (0xA8, 0x62, 0x00), 130),    # âmbar: alerta para o vendedor
    "erro": ((0xF0, 0x66, 0x6B), 203, (0xC0, 0x2B, 0x31), 160),      # coral: erro de tool, resposta segura
}
PREFIXO_CLIENTE = "Você ›"
PREFIXO_LIA = "♪ Lia ›"
RECUO = " " * (len(PREFIXO_LIA) + 1)


def cores_ligadas(fluxo=None) -> bool:
    fluxo = fluxo or sys.stdout
    return hasattr(fluxo, "isatty") and fluxo.isatty() and os.getenv("NO_COLOR") is None


def _truecolor() -> bool:
    return (os.getenv("COLORTERM", "").lower() in ("truecolor", "24bit") or bool(os.getenv("WT_SESSION"))
            or os.getenv("TERM_PROGRAM", "") in ("vscode", "iTerm.app", "WezTerm"))


def _claro() -> bool:
    return os.getenv("EMPORIO_TEMA", "").strip().lower() == "claro"


def _sgr(papel: str, fundo: bool = False) -> str:
    escuro, i_escuro, claro, i_claro = PALETA[papel]
    rgb, indice = (claro, i_claro) if _claro() else (escuro, i_escuro)
    base = 48 if fundo else 38
    return f"{base};2;{rgb[0]};{rgb[1]};{rgb[2]}" if _truecolor() else f"{base};5;{indice}"


class Estilo:
    """Aplica os papéis da paleta; sem cor, devolve o texto puro."""

    def __init__(self, ligado: bool | None = None):
        self.ligado = cores_ligadas() if ligado is None else ligado

    def __call__(self, texto: str, papel: str | None = None, negrito: bool = False, italico: bool = False,
                 fundo: str | None = None) -> str:
        if not self.ligado:
            return texto
        codigos = [c for c, ok in (("1", negrito), ("3", italico)) if ok]
        if papel:
            codigos.append(_sgr(papel))
        if fundo:
            codigos.append(_sgr(fundo, fundo=True))
        return f"\033[{';'.join(codigos)}m{texto}\033[0m" if codigos else texto

    # ---- elementos da conversa
    def cliente(self) -> str:
        return self(PREFIXO_CLIENTE, negrito=True)

    def lia(self, rotulo: str = "") -> str:
        return self(f"♪ Lia{rotulo} ›", "marca", negrito=True)

    def rastro(self, etiqueta: str, texto: str, erro: str | None = None) -> str:
        linha = f"{self('  │', 'trilho')} {self(f'{etiqueta:<7}', 'marca', negrito=True)} {self(texto, 'suave')}"
        return linha + (f" {self(erro, 'erro')}" if erro else "")

    def alerta(self, texto: str) -> str:
        return f"{self('  ▲ vendedor', 'alerta', negrito=True)} {self(texto, 'alerta')}"

    def sistema(self, texto: str) -> str:
        return self(texto, "suave")

    def banner(self, modelo: str, linhas_extra: tuple[str, ...] = ()) -> str:
        """A palheta-balão da logo em blocos, com a nota em azul-marinho, e a marca ao lado."""
        m = lambda t: self(t, "marca")
        nota = self(" ♪ ", "fundo", negrito=True, fundo="marca") if self.ligado else " ♪ "
        textos = [
            "",
            self("Empório da Música", negrito=True),
            self("Lia · assistente virtual", "marca"),
            self(f"{modelo} · ZDR obrigatório", "suave"),
            self("/novo recomeça · /sair encerra", "suave"),
            "",
        ]
        desenho = [
            m(" ▄██████████▄ "),
            m("██████████████"),
            m("█████") + nota + m("██████"),
            m(" ▀██████████▀ "),
            m("   ▀██████▀   "),
            m("     ▀██▀▖    "),
        ]
        corpo = [f"{d}   {t}".rstrip() for d, t in zip(desenho, textos)]
        return "\n".join(corpo + [self(x, "suave") for x in linhas_extra]) + "\n"


def recuar(texto: str, largura: int | None = None) -> str:
    """Continuação das falas da Lia alinhada depois do prefixo. Com `largura` (terminal interativo),
    quebra as linhas longas; sem ela (saída redirecionada), só alinha as quebras que já existem."""
    if largura is None:
        return ("\n" + RECUO).join(texto.split("\n"))
    util = max(40, largura - len(RECUO) - 1)      # uma coluna livre: o Windows quebra de novo na última
    linhas: list[str] = []
    for paragrafo in texto.split("\n"):
        linhas.extend(textwrap.wrap(paragrafo, util, break_long_words=False, break_on_hyphens=False) or [""])
    return ("\n" + RECUO).join(linhas)


def largura_terminal(fluxo=None) -> int | None:
    fluxo = fluxo or sys.stdout
    return shutil.get_terminal_size((100, 24)).columns if hasattr(fluxo, "isatty") and fluxo.isatty() else None
