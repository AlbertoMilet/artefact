"""LGPD no atendimento (SPEC-012): expurgo por prazo e exclusão dos dados de uma conversa.

As regras (prazos e o que sai de cada log) estão em `emporio.rules.privacidade`; aqui só a leitura e a
escrita dos arquivos. `tickets.jsonl` não entra: é o registro das solicitações, guardado por obrigação legal.

Uso:
    python -m emporio privacidade expurgar [--dias 90]
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from pathlib import Path

from emporio.alertas.central import caminho_fila
from emporio.rules.horario import relogio_real
from emporio.rules.privacidade import PRAZO_RETENCAO_DIAS, linhas_mantidas, linhas_texto_mantidas
from emporio.rules.verificacao import mascarar_texto

RAIZ = Path(__file__).resolve().parents[2]


class FormatoMascarado(logging.Formatter):
    """Formata o registro (inclusive o traceback) e mascara telefone, e-mail, CPF e CEP antes de gravar."""

    def format(self, record: logging.LogRecord) -> str:
        return mascarar_texto(super().format(record))


def caminho_log_turnos() -> Path:
    return Path(os.getenv("EMPORIO_LOG_TURNOS", str(RAIZ / "logs" / "emporio.jsonl")))


def caminho_log_avisos() -> Path:
    return Path(os.getenv("EMPORIO_LOG_AVISOS", str(RAIZ / "logs" / "avisos.log")))


def _reescrever(arquivo: Path, ficam: list[str]) -> None:
    temporario = arquivo.with_suffix(arquivo.suffix + ".tmp")
    temporario.write_text("".join(ficam), encoding="utf-8")
    temporario.replace(arquivo)


def limpar_texto(arquivo: Path, agora: datetime, dias: int = PRAZO_RETENCAO_DIAS) -> int:
    """Log de texto (`avisos.log`): tira os registros vencidos. Devolve quantas linhas saíram."""
    if not arquivo.exists():
        return 0
    linhas = arquivo.read_text(encoding="utf-8").splitlines(keepends=True)
    ficam = linhas_texto_mantidas(linhas, agora, dias)
    saem = len(linhas) - len(ficam)
    if saem:
        _reescrever(arquivo, ficam)
    return saem


def limpar_jsonl(arquivo: Path, agora: datetime, dias: int = PRAZO_RETENCAO_DIAS,
                 apagar_conversa: str | None = None) -> int:
    """Reescreve o arquivo só com as linhas que ficam. Devolve quantas saíram."""
    if not arquivo.exists():
        return 0
    linhas = arquivo.read_text(encoding="utf-8").splitlines(keepends=True)
    ficam = linhas_mantidas(linhas, agora, dias, apagar_conversa)
    saem = sum(1 for x in linhas if x.strip()) - len(ficam)
    if saem:
        _reescrever(arquivo, ficam)
    return saem


def logs() -> list[Path]:
    return [caminho_log_turnos(), caminho_fila()]


def expurgar(repo, agora: datetime | None = None, dias: int = PRAZO_RETENCAO_DIAS) -> dict:
    """Apaga mensagens, conversas vazias, linhas de log e auditoria vencidas (RL-01, RL-02, RL-11).
    Usa sempre o relógio real. `afetadas`: conversas cujo cache em memória precisa ser descartado."""
    agora = agora or relogio_real()
    banco = repo.expurgar(agora, dias)
    linhas = sum(limpar_jsonl(arq, agora, dias) for arq in logs()) + limpar_texto(caminho_log_avisos(), agora, dias)
    return {"mensagens": banco["mensagens"], "conversas": banco["conversas"], "linhas_de_log": linhas,
            "auditoria": repo.expurgar_auditoria(agora), "afetadas": banco["afetadas"]}


def apagar_conversa(repo, cid: str, usuario: str, agora: datetime | None = None) -> None:
    """Apaga os dados de uma conversa no banco e nos logs e registra quem fez (RL-05, RL-09)."""
    agora = agora or relogio_real()
    repo.apagar(cid)
    for arq in logs():
        limpar_jsonl(arq, agora, apagar_conversa=cid)
    repo.auditar(usuario, "apagou", cid)


def main(argv: list[str] | None = None) -> int:
    from emporio.web.repositorio import Repositorio

    ap = argparse.ArgumentParser(prog="emporio privacidade", description="LGPD no atendimento (SPEC-012)")
    sub = ap.add_subparsers(dest="comando", required=True)
    exp = sub.add_parser("expurgar", help="apaga conversas e logs sem atividade há mais que o prazo")
    exp.add_argument("--dias", type=int, default=PRAZO_RETENCAO_DIAS)
    sub.add_parser("auditoria", help="últimas ações no painel (abrir, exportar, apagar)")
    a = ap.parse_args(argv)
    repo = Repositorio()
    if a.comando == "expurgar":
        r = expurgar(repo, dias=a.dias)
        print(f"Expurgo ({a.dias} dias): {r['mensagens']} mensagem(ns), {r['conversas']} conversa(s), "
              f"{r['linhas_de_log']} linha(s) de log e {r['auditoria']} registro(s) de auditoria apagados.")
    else:
        for item in repo.auditoria():
            print(f"{item['criada_em']}  {item['usuario']:<12} {item['acao']:<10} {item['conversa_id']}")
    return 0
