"""Usuários do painel (SPEC-008). Nada é gravado: o comando só imprime o que vai no .env.

    python -m emporio usuario criar carlos     pede a senha (sem mostrar) e imprime nome:hash
    python -m emporio usuario segredo          gera EMPORIO_SEGREDO_SESSAO
    python -m emporio usuario listar           nomes configurados em EMPORIO_USUARIOS (sem hashes)
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import warnings
from pathlib import Path

from dotenv import load_dotenv

from emporio.web.auth import NOME_VALIDO, carregar_usuarios, hash_senha

RAIZ = Path(__file__).resolve().parents[2]


def _ler_senha(rotulo: str) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass(rotulo)
        except getpass.GetPassWarning:
            raise ValueError("a senha exige um terminal interativo que esconda a digitação") from None


def criar(nome: str) -> int:
    if not NOME_VALIDO.match(nome):
        raise ValueError("nome inválido: 2 a 64 letras, números ou . _ @ + -")
    senha = _ler_senha(f"Senha para {nome} (mínimo 8 caracteres): ")
    if senha != _ler_senha("Repita a senha: "):
        raise ValueError("as senhas não conferem")
    linha = f"{nome}:{hash_senha(senha)}"
    print("\nAcrescente em EMPORIO_USUARIOS no .env (vários usuários separados por vírgula):\n")
    print(f"EMPORIO_USUARIOS={linha}")
    print("\nA senha não é guardada em lugar nenhum; só o hash vai para o .env.")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="emporio usuario", description="Usuários do painel (SPEC-008)")
    sub = ap.add_subparsers(dest="acao", required=True)
    c = sub.add_parser("criar", help="gera a linha nome:hash para EMPORIO_USUARIOS")
    c.add_argument("nome")
    sub.add_parser("segredo", help="gera EMPORIO_SEGREDO_SESSAO")
    sub.add_parser("listar", help="nomes configurados (sem os hashes)")
    a = ap.parse_args(argv)
    try:
        if a.acao == "criar":
            return criar(a.nome)
        if a.acao == "segredo":
            print("Coloque no .env:\nEMPORIO_SEGREDO_SESSAO=" + secrets.token_hex(32))
            return 0
        load_dotenv(RAIZ / ".env")
        nomes = sorted(carregar_usuarios())
        print("Usuários: " + ", ".join(nomes) if nomes else "Nenhum usuário em EMPORIO_USUARIOS.")
        return 0
    except ValueError as e:
        print(f"Erro: {e}")
        return 2
