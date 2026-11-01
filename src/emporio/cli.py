"""CLI do agente (SPEC-001 Fase 4).

    python -m emporio chat                 conversa interativa
    python -m emporio chat --debug         mostra tools chamadas, argumentos e resultado (mascarados)
    python -m emporio chat --fake          modo demonstração, sem chave nem modelo de linguagem
    python -m emporio chat -m "oi" -m "qual o endereço?"   mensagens em sequência, sem interação

Comandos durante a conversa: /novo (recomeça), /sair (ou Ctrl+D / Ctrl+Z+Enter no Windows).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import replace
from pathlib import Path

from emporio.agent import Agente, Conversa, RespostaTurno
from emporio.config import RAIZ, Config, montar_agente
from emporio.data import DadosIndisponiveis
from emporio.llm import LLMIndisponivel

CORES = sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def _cor(texto: str, codigo: str) -> str:
    return f"\033[{codigo}m{texto}\033[0m" if CORES else texto


def configurar_log(pasta: Path) -> None:
    """Log JSON por turno (já mascarado pelo agente) em arquivo; nada de log no terminal."""
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in ("emporio.turno", ""):
        lg = logging.getLogger(nome)
        for antigo in [x for x in lg.handlers if getattr(x, "_emporio", False)]:
            lg.removeHandler(antigo)
            antigo.close()
    h = logging.FileHandler(pasta / "emporio.jsonl", encoding="utf-8")
    h.setFormatter(logging.Formatter("%(message)s"))
    h._emporio = True
    turno = logging.getLogger("emporio.turno")
    turno.setLevel(logging.INFO)
    turno.addHandler(h)
    turno.propagate = False
    avisos = logging.FileHandler(pasta / "avisos.log", encoding="utf-8")
    avisos.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    avisos._emporio = True
    raiz = logging.getLogger()
    raiz.setLevel(logging.WARNING)
    raiz.addHandler(avisos)


def mostrar(resp: RespostaTurno, debug: bool, saida=None) -> None:
    saida = saida or sys.stdout
    if debug:
        for e in resp.rastro:
            status = _cor(f"erro: {e.erro}", "31") if e.erro else "ok"
            print(_cor(f"  [tool] {e.tool}({e.argumentos}) -> {status} em {e.duracao_ms} ms", "2"), file=saida)
            print(_cor(f"         {e.resultado}", "2"), file=saida)
        extra = f" | resposta segura: {resp.motivo_segura}" if resp.segura else ""
        print(_cor(f"  [turno] {resp.latencia_s:.1f} s | {resp.tokens_entrada}+{resp.tokens_saida} tokens | "
                   f"US$ {resp.custo_usd:.5f}{extra}", "2"), file=saida)
    print(f"{_cor('Lia:', '1;35')} {resp.texto}\n", file=saida)


def conversar(agente: Agente, mensagens: list[str] | None, debug: bool) -> int:
    conversa: Conversa = agente.nova_conversa()
    if mensagens:
        for m in mensagens:
            print(f"{_cor('Você:', '1;36')} {m}")
            mostrar(agente.responder(conversa, m), debug)
        return 0
    print(_cor("Empório da Música: atendimento virtual. /novo recomeça, /sair encerra.\n", "2"))
    while True:
        try:
            texto = input(_cor("Você: ", "1;36")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not texto:
            continue
        if texto.lower() in ("/sair", "sair", "/exit", "/quit"):
            return 0
        if texto.lower() == "/novo":
            conversa = agente.nova_conversa()
            print(_cor("(nova conversa)\n", "2"))
            continue
        mostrar(agente.responder(conversa, texto), debug)


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="emporio", description="Agente de atendimento da Empório da Música")
    sub = ap.add_subparsers(dest="comando", required=True)
    chat = sub.add_parser("chat", help="conversar com o agente")
    chat.add_argument("--debug", action="store_true", help="mostra o rastro de tools e fontes")
    chat.add_argument("--fake", action="store_true", help="modo demonstração sem modelo (LLM_PROVIDER=fake)")
    chat.add_argument("--modelo", help="sobrescreve OPENROUTER_MODEL")
    chat.add_argument("-m", "--mensagem", action="append", help="mensagem não interativa (pode repetir)")
    a = ap.parse_args(argv)

    configurar_log(RAIZ / "logs")
    config = Config.do_ambiente()
    if a.fake:
        config = replace(config, llm_provider="fake")
    if a.modelo:
        config = replace(config, openrouter_model=a.modelo)
    try:
        agente = montar_agente(config)
    except DadosIndisponiveis as e:
        print(f"Não foi possível carregar os dados da loja: {e}", file=sys.stderr)
        return 2
    except LLMIndisponivel as e:
        print(f"LLM indisponível: {e}\nConfigure OPENROUTER_API_KEY no .env (veja .env.example) "
              "ou rode em modo demonstração: python -m emporio chat --fake", file=sys.stderr)
        return 2
    if a.debug:
        print(_cor(f"[modelo: {agente.llm.modelo} | ZDR obrigatório | dados: {config.data_dir}]", "2"))
    return conversar(agente, a.mensagem, a.debug)


if __name__ == "__main__":
    sys.exit(main())
