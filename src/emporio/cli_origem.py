"""Origem dos leads (SPEC-005).

    python -m emporio origem links [--numero "(67) 3341-4444"] [--mensagem "Olá! Quero mais informações"]
    python -m emporio origem relatorio [--log logs/emporio.jsonl]

`links` imprime um link do WhatsApp por canal, cada um com o emoji do canal no fim da mensagem.
`relatorio` conta as conversas por canal a partir do log dos turnos.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from emporio.rules import origem
from emporio.tools.toolbox import LOJA

RAIZ = Path(__file__).resolve().parents[2]


def links(numero: str, mensagem: str) -> int:
    print(f"Links do WhatsApp por canal (mensagem: \"{mensagem} <emoji>\"):\n")
    for o in origem.ORIGENS:
        print(f"  {o.marcador}  {o.nome}\n     {origem.link_whatsapp(numero, o, mensagem)}\n")
    print("Use cada link só no seu canal. Se o cliente apagar o emoji, a origem fica desconhecida.")
    return 0


def origens_do_log(caminho: Path) -> dict[str, str | None]:
    """Conversa -> última origem registrada nos turnos (None se nunca houve marcador)."""
    por_conversa: dict[str, str | None] = {}
    if not caminho.is_file():
        return por_conversa
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if d.get("evento") != "turno" or not d.get("conversa"):
            continue
        por_conversa[d["conversa"]] = d.get("origem") or por_conversa.get(d["conversa"])
    return por_conversa


def relatorio(caminho: Path) -> int:
    por_conversa = origens_do_log(caminho)
    if not por_conversa:
        print(f"Nenhuma conversa em {caminho}.")
        return 0
    contagem = origem.resumir(list(por_conversa.values()))
    total = len(por_conversa)
    print(f"Conversas por origem ({total} no total):")
    for chave, n in contagem.items():
        o = origem.POR_CHAVE.get(chave)
        rotulo = f"{o.marcador}  {o.nome}" if o else "❔  Desconhecida (sem marcador)"
        print(f"  {rotulo:<32} {n:>4}  ({n / total:.0%})")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="emporio origem", description="Origem dos leads (SPEC-005)")
    sub = ap.add_subparsers(dest="acao", required=True)
    lk = sub.add_parser("links", help="links do WhatsApp com o emoji de cada canal")
    lk.add_argument("--numero", default=LOJA["telefone_whatsapp"], help="WhatsApp da loja (padrão: o oficial)")
    lk.add_argument("--mensagem", default=origem.MENSAGEM_PADRAO, help="mensagem pré-preenchida, sem o emoji")
    rel = sub.add_parser("relatorio", help="conversas por canal, a partir do log")
    rel.add_argument("--log", type=Path, default=RAIZ / "logs" / "emporio.jsonl")
    a = ap.parse_args(argv)
    try:
        return links(a.numero, a.mensagem) if a.acao == "links" else relatorio(a.log)
    except ValueError as e:
        print(f"Erro: {e}")
        return 2
