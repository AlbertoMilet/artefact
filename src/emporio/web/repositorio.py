"""Histórico das conversas em SQLite (SPEC-007), para o vendedor ler e assumir o atendimento.

- O telefone do cliente nunca é gravado em claro: a conversa é achada pelo hash do número e mostrada
  com o número mascarado (RN-09, RN-24).
- Todo texto é gravado já mascarado (telefone e e-mail viram `(67) 9****-7821`).
- `status`: "lia" (a Lia responde) ou "vendedor" (um vendedor assumiu; a Lia não responde).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from emporio.rules.horario import FUSO
from emporio.rules.verificacao import mascarar_texto

RAIZ = Path(__file__).resolve().parents[3]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS conversas (
    id TEXT PRIMARY KEY,
    chave_telefone TEXT UNIQUE NOT NULL,
    telefone_mascarado TEXT NOT NULL,
    origem TEXT,
    status TEXT NOT NULL DEFAULT 'lia',
    aguardando_vendedor INTEGER NOT NULL DEFAULT 0,
    criada_em TEXT NOT NULL,
    atualizada_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mensagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversa_id TEXT NOT NULL REFERENCES conversas(id),
    autor TEXT NOT NULL,
    texto TEXT NOT NULL,
    detalhes TEXT,
    criada_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mensagens_conversa ON mensagens(conversa_id, id);
"""


def caminho_banco() -> Path:
    return Path(os.getenv("EMPORIO_DB", str(RAIZ / "logs" / "atendimento.db")))


def chave_do_telefone(telefone: str) -> str:
    digitos = re.sub(r"\D", "", telefone or "")
    if len(digitos) < 10:
        raise ValueError("telefone inválido: use DDD + número, ex.: (67) 98888-0001")
    return hashlib.sha256(digitos[-11:].encode()).hexdigest()


@dataclass
class ConversaSalva:
    id: str
    telefone: str                 # mascarado
    origem: str | None
    status: str
    aguardando_vendedor: bool
    criada_em: str
    atualizada_em: str
    ultima: str = ""
    total: int = 0


@dataclass
class MensagemSalva:
    id: int
    autor: str                    # cliente | lia | vendedor | alerta
    texto: str
    detalhes: dict
    criada_em: str

    @property
    def hora(self) -> str:
        return self.criada_em[11:16]


class Repositorio:
    def __init__(self, caminho: Path | str | None = None, relogio=None):
        self.caminho = Path(caminho) if caminho else caminho_banco()
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.relogio = relogio or (lambda: datetime.now(FUSO))
        self._trava = threading.Lock()
        self._db = sqlite3.connect(self.caminho, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(ESQUEMA)

    def _agora(self) -> str:
        return self.relogio().isoformat(timespec="seconds")

    def _conversa(self, r: sqlite3.Row) -> ConversaSalva:
        return ConversaSalva(r["id"], r["telefone_mascarado"], r["origem"], r["status"],
                             bool(r["aguardando_vendedor"]), r["criada_em"], r["atualizada_em"],
                             r["ultima"] if "ultima" in r.keys() else "", r["total"] if "total" in r.keys() else 0)

    # ---------------------------------------------------------------- conversas
    def conversa_do_telefone(self, telefone: str, criar: bool = True) -> ConversaSalva | None:
        chave = chave_do_telefone(telefone)
        with self._trava:
            r = self._db.execute("SELECT * FROM conversas WHERE chave_telefone = ?", (chave,)).fetchone()
            if r is None and not criar:
                return None
            if r is None:
                agora = self._agora()
                cid = uuid.uuid4().hex[:12]
                self._db.execute("INSERT INTO conversas (id, chave_telefone, telefone_mascarado, criada_em, "
                                 "atualizada_em) VALUES (?, ?, ?, ?, ?)",
                                 (cid, chave, mascarar_texto(telefone.strip()), agora, agora))
                self._db.commit()
                r = self._db.execute("SELECT * FROM conversas WHERE id = ?", (cid,)).fetchone()
        return self._conversa(r)

    def conversa(self, cid: str) -> ConversaSalva | None:
        with self._trava:
            r = self._db.execute("SELECT * FROM conversas WHERE id = ?", (cid,)).fetchone()
        return self._conversa(r) if r else None

    def listar(self, limite: int = 100) -> list[ConversaSalva]:
        with self._trava:
            linhas = self._db.execute(
                "SELECT c.*, (SELECT texto FROM mensagens m WHERE m.conversa_id = c.id AND m.autor != 'alerta' "
                "ORDER BY m.id DESC LIMIT 1) AS ultima, "
                "(SELECT COUNT(*) FROM mensagens m WHERE m.conversa_id = c.id AND m.autor != 'alerta') AS total "
                "FROM conversas c ORDER BY c.aguardando_vendedor DESC, c.atualizada_em DESC LIMIT ?",
                (limite,)).fetchall()
        return [self._conversa(r) for r in linhas]

    def atualizar(self, cid: str, **campos) -> None:
        permitidos = {"origem", "status", "aguardando_vendedor"}
        sets = {k: v for k, v in campos.items() if k in permitidos}
        if not sets:
            return
        with self._trava:
            self._db.execute(f"UPDATE conversas SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?",
                             (*sets.values(), cid))
            self._db.commit()

    def apagar(self, cid: str) -> None:
        with self._trava:
            self._db.execute("DELETE FROM mensagens WHERE conversa_id = ?", (cid,))
            self._db.execute("DELETE FROM conversas WHERE id = ?", (cid,))
            self._db.commit()

    # ---------------------------------------------------------------- mensagens
    def adicionar(self, cid: str, autor: str, texto: str, detalhes: dict | None = None) -> MensagemSalva:
        agora = self._agora()
        with self._trava:
            cur = self._db.execute(
                "INSERT INTO mensagens (conversa_id, autor, texto, detalhes, criada_em) VALUES (?, ?, ?, ?, ?)",
                (cid, autor, mascarar_texto(texto), json.dumps(detalhes or {}, ensure_ascii=False), agora))
            self._db.execute("UPDATE conversas SET atualizada_em = ? WHERE id = ?", (agora, cid))
            self._db.commit()
        return MensagemSalva(cur.lastrowid, autor, mascarar_texto(texto), detalhes or {}, agora)

    def mensagens(self, cid: str) -> list[MensagemSalva]:
        with self._trava:
            linhas = self._db.execute("SELECT * FROM mensagens WHERE conversa_id = ? ORDER BY id", (cid,)).fetchall()
        return [MensagemSalva(r["id"], r["autor"], r["texto"], json.loads(r["detalhes"] or "{}"), r["criada_em"])
                for r in linhas]

    def alertas_recentes(self, limite: int = 30) -> list[tuple[str, MensagemSalva]]:
        """(conversa_id, alerta) dos alertas mais recentes de todas as conversas."""
        with self._trava:
            linhas = self._db.execute("SELECT * FROM mensagens WHERE autor = 'alerta' ORDER BY id DESC LIMIT ?",
                                      (limite,)).fetchall()
        return [(r["conversa_id"], MensagemSalva(r["id"], r["autor"], r["texto"], json.loads(r["detalhes"] or "{}"),
                                                 r["criada_em"])) for r in linhas]

    def fechar(self) -> None:
        self._db.close()
