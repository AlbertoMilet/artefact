"""Histórico das conversas em SQLite (SPEC-007), para o vendedor ler e assumir o atendimento.

- O telefone do cliente nunca é gravado em claro: a conversa é achada pelo HMAC do número, com chave
  secreta (SPEC-012 RL-07), e mostrada com o número mascarado (RN-09, RN-24).
- Todo texto é gravado já mascarado (telefone e e-mail viram `(67) 9****-7821`).
- `status`: "lia" (a Lia responde) ou "vendedor" (um vendedor assumiu; a Lia não responde).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from emporio.rules.horario import FUSO
from emporio.rules.limites import JANELA_AUDITORIA_LEITURA_S
from emporio.rules.privacidade import PRAZO_AUDITORIA_DIAS, PRAZO_RETENCAO_DIAS, expirado
from emporio.rules.verificacao import mascarar_texto

RAIZ = Path(__file__).resolve().parents[3]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS conversas (
    id TEXT PRIMARY KEY,
    chave_telefone TEXT UNIQUE NOT NULL,
    telefone_mascarado TEXT NOT NULL,
    origem TEXT,
    nome TEXT,
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
CREATE TABLE IF NOT EXISTS sessoes_revogadas (
    sid TEXT PRIMARY KEY,
    expira INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL,
    acao TEXT NOT NULL,
    conversa_id TEXT NOT NULL,
    criada_em TEXT NOT NULL
);
"""


def caminho_banco() -> Path:
    return Path(os.getenv("EMPORIO_DB", str(RAIZ / "logs" / "atendimento.db")))


def _digitos_do_telefone(telefone: str) -> str:
    digitos = re.sub(r"\D", "", telefone or "")
    if len(digitos) < 10:
        raise ValueError("telefone inválido: use DDD + número, ex.: (67) 98888-0001")
    return digitos[-11:]


def caminho_banco_demo() -> Path:
    """Banco do modo demonstração (SPEC-013 RS-01), separado do histórico real."""
    return Path(os.getenv("EMPORIO_DB_DEMO", str(RAIZ / "logs" / "demo.db")))


def chave_do_telefone(telefone: str, chave: bytes) -> str:
    """HMAC-SHA256 do número com chave secreta (SPEC-012 RL-07): sem a chave, não dá para testar números."""
    return hmac.new(chave, _digitos_do_telefone(telefone).encode(), hashlib.sha256).hexdigest()


def hash_antigo(telefone: str) -> str:
    """SHA-256 puro, usado antes da SPEC-012; só para achar e migrar conversas antigas."""
    return hashlib.sha256(_digitos_do_telefone(telefone).encode()).hexdigest()


def carregar_chave_telefone(pasta: Path) -> bytes:
    """`EMPORIO_CHAVE_TELEFONE` ou, sem ela, uma chave gerada uma vez e guardada ao lado do banco."""
    do_ambiente = os.getenv("EMPORIO_CHAVE_TELEFONE", "").strip()
    if do_ambiente:
        return do_ambiente.encode()
    arquivo = pasta / ".chave_telefone"
    if not arquivo.exists():
        arquivo.write_text(secrets.token_hex(32), encoding="utf-8")
        try:
            os.chmod(arquivo, 0o600)                   # SPEC-013: só o dono lê (no Windows, só leitura)
        except OSError:
            pass
    return arquivo.read_text(encoding="utf-8").strip().encode()


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
    nome: str | None = None       # primeiro nome do perfil do WhatsApp, já filtrado (SPEC-010)


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
        self._chave = carregar_chave_telefone(self.caminho.parent)
        self._trava = threading.Lock()
        self._db = sqlite3.connect(self.caminho, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(ESQUEMA)
        colunas = {r["name"] for r in self._db.execute("PRAGMA table_info(conversas)")}
        if "nome" not in colunas:                       # bancos criados antes da SPEC-010
            self._db.execute("ALTER TABLE conversas ADD COLUMN nome TEXT")
            self._db.commit()

    def _agora(self) -> str:
        return self.relogio().isoformat(timespec="seconds")

    def _conversa(self, r: sqlite3.Row) -> ConversaSalva:
        return ConversaSalva(r["id"], r["telefone_mascarado"], r["origem"], r["status"],
                             bool(r["aguardando_vendedor"]), r["criada_em"], r["atualizada_em"],
                             r["ultima"] if "ultima" in r.keys() else "", r["total"] if "total" in r.keys() else 0,
                             r["nome"])

    # ---------------------------------------------------------------- conversas
    def conversa_do_telefone(self, telefone: str, criar: bool = True) -> ConversaSalva | None:
        chave = chave_do_telefone(telefone, self._chave)
        with self._trava:
            r = self._db.execute("SELECT * FROM conversas WHERE chave_telefone = ?", (chave,)).fetchone()
            if r is None:                              # conversa gravada antes da SPEC-012: migra para o HMAC
                antiga = self._db.execute("SELECT * FROM conversas WHERE chave_telefone = ?",
                                          (hash_antigo(telefone),)).fetchone()
                if antiga is not None:
                    self._db.execute("UPDATE conversas SET chave_telefone = ? WHERE id = ?", (chave, antiga["id"]))
                    self._db.commit()
                    r = self._db.execute("SELECT * FROM conversas WHERE id = ?", (antiga["id"],)).fetchone()
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
        permitidos = {"origem", "status", "aguardando_vendedor", "nome"}
        sets = {k: v for k, v in campos.items() if k in permitidos}
        if not sets:
            return
        with self._trava:
            self._db.execute(f"UPDATE conversas SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?",
                             (*sets.values(), cid))
            self._db.commit()

    def expurgar(self, agora: datetime | None = None, dias: int = PRAZO_RETENCAO_DIAS) -> dict:
        """Apaga cada mensagem com mais de `dias` e as conversas que ficaram vazias e paradas (SPEC-012 RL-01).

        O prazo vale por mensagem: uma conversa ativa perde as mensagens antigas. Devolve as contagens e os ids
        das conversas afetadas, para quem guarda cache delas."""
        agora = agora or self.relogio()
        with self._trava:
            msgs = self._db.execute("SELECT id, conversa_id, criada_em FROM mensagens").fetchall()
            velhas = [r for r in msgs if expirado(r["criada_em"], agora, dias)]
            self._db.executemany("DELETE FROM mensagens WHERE id = ?", [(r["id"],) for r in velhas])
            vazias = [r["id"] for r in self._db.execute(
                "SELECT c.id, c.atualizada_em FROM conversas c WHERE NOT EXISTS "
                "(SELECT 1 FROM mensagens m WHERE m.conversa_id = c.id)").fetchall()
                if expirado(r["atualizada_em"], agora, dias)]
            self._db.executemany("DELETE FROM conversas WHERE id = ?", [(cid,) for cid in vazias])
            self._db.commit()
        return {"mensagens": len(velhas), "conversas": len(vazias),
                "afetadas": sorted({r["conversa_id"] for r in velhas} | set(vazias))}

    def expurgar_auditoria(self, agora: datetime | None = None, dias: int = PRAZO_AUDITORIA_DIAS) -> int:
        """Registros de acesso com mais de `dias` (RL-11)."""
        agora = agora or self.relogio()
        with self._trava:
            linhas = self._db.execute("SELECT id, criada_em FROM auditoria").fetchall()
            velhos = [(r["id"],) for r in linhas if expirado(r["criada_em"], agora, dias)]
            self._db.executemany("DELETE FROM auditoria WHERE id = ?", velhos)
            self._db.commit()
        return len(velhos)

    def exportar(self, cid: str) -> dict | None:
        """Dados de uma conversa como estão guardados, já mascarados e sem o HMAC do telefone (RL-06)."""
        conv = self.conversa(cid)
        if conv is None:
            return None
        return {
            "conversa": {"id": conv.id, "telefone": conv.telefone, "nome": conv.nome, "origem": conv.origem,
                         "status": conv.status, "criada_em": conv.criada_em, "atualizada_em": conv.atualizada_em},
            "mensagens": [{"autor": m.autor, "texto": m.texto, "criada_em": m.criada_em, "detalhes": m.detalhes}
                          for m in self.mensagens(cid)],
        }

    def revogar_sessao(self, sid: str, expira: int) -> None:
        """SPEC-013 RS-04: a sessão deixa de valer até expirar; depois o registro é apagado."""
        with self._trava:
            self._db.execute("INSERT OR REPLACE INTO sessoes_revogadas (sid, expira) VALUES (?, ?)", (sid, expira))
            self._db.execute("DELETE FROM sessoes_revogadas WHERE expira < ?", (int(time.time()),))
            self._db.commit()

    def sessao_revogada(self, sid: str) -> bool:
        with self._trava:
            return self._db.execute("SELECT 1 FROM sessoes_revogadas WHERE sid = ?", (sid,)).fetchone() is not None

    def auditar_leitura(self, usuario: str, cid: str, janela_s: int = JANELA_AUDITORIA_LEITURA_S) -> None:
        """Um "abriu" por usuário e conversa a cada `janela_s` (SPEC-013 RS-08), em qualquer rota de leitura."""
        agora = self.relogio()
        with self._trava:
            r = self._db.execute("SELECT criada_em FROM auditoria WHERE usuario = ? AND conversa_id = ? AND "
                                 "acao = 'abriu' ORDER BY id DESC LIMIT 1", (usuario, cid)).fetchone()
        if r is not None:
            try:
                if (agora - datetime.fromisoformat(r["criada_em"])).total_seconds() < janela_s:
                    return
            except ValueError:
                pass
        self.auditar(usuario, "abriu", cid)

    def auditar(self, usuario: str, acao: str, cid: str) -> None:
        """Quem abriu, exportou ou apagou uma conversa (RL-09)."""
        with self._trava:
            self._db.execute("INSERT INTO auditoria (usuario, acao, conversa_id, criada_em) VALUES (?, ?, ?, ?)",
                             (usuario, acao, cid, self._agora()))
            self._db.commit()

    def auditoria(self, limite: int = 200) -> list[dict]:
        with self._trava:
            linhas = self._db.execute("SELECT usuario, acao, conversa_id, criada_em FROM auditoria "
                                      "ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [dict(r) for r in linhas]

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
