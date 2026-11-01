"""Estado da conexão do WhatsApp da loja, salvo e retomável (SPEC-004 §4.1, RW-06, RW-08).

O token da Meta é salvo só cifrado com Fernet (chave em WHATSAPP_CHAVE_CIFRA), como no crypto.py do
Trato Fácil, mas sem derrubar a aplicação quando a chave falta: aí os IDs são salvos e o token não.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class Etapa(str, Enum):
    NAO_CONECTADO = "nao_conectado"
    AUTENTICADO = "autenticado"
    NUMERO_ESCOLHIDO = "numero_escolhido"
    CODIGO_ENVIADO = "codigo_enviado"
    VERIFICADO = "verificado"
    REGISTRADO = "registrado"
    CONECTADO = "conectado"


ORDEM = list(Etapa)


@dataclass
class Conexao:
    etapa: Etapa = Etapa.NAO_CONECTADO
    waba_id: str | None = None
    phone_number_id: str | None = None
    numero_exibicao: str | None = None
    nome_verificado: str | None = None
    token_cifrado: str | None = None
    token_expira_em: str | None = None           # ISO 8601, quando a Meta informa
    codigo_pedido_em: str | None = None          # ISO 8601 (intervalo para pedir outro, RW-04)
    tentativas_codigo: int = 0
    atualizado_em: str | None = None
    historico: list[str] = field(default_factory=list)   # etapas e erros, sem segredos

    def chegou(self, etapa: Etapa) -> bool:
        return ORDEM.index(self.etapa) >= ORDEM.index(etapa)

    def avancar(self, etapa: Etapa, agora: datetime, nota: str = "") -> None:
        self.etapa = etapa
        self.atualizado_em = agora.isoformat()
        self.historico.append(f"{agora:%d/%m %H:%M} {etapa.value}" + (f": {nota}" if nota else ""))


# ---------------------------------------------------------------- cifra do token

class SemChaveDeCifra(RuntimeError):
    pass


def _fernet():
    from cryptography.fernet import Fernet
    chave = os.getenv("WHATSAPP_CHAVE_CIFRA", "").strip()
    if not chave:
        raise SemChaveDeCifra("WHATSAPP_CHAVE_CIFRA não definida: gere com `python -m emporio whatsapp gerar-chave`")
    return Fernet(chave.encode())


def gerar_chave() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def cifrar(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decifrar(token_cifrado: str) -> str:
    return _fernet().decrypt(token_cifrado.encode()).decode()


# ---------------------------------------------------------------- arquivo

def caminho() -> Path:
    padrao = Path(__file__).resolve().parents[3] / ".emporio_whatsapp.json"
    return Path(os.getenv("WHATSAPP_CONEXAO", str(padrao)))


def carregar() -> Conexao:
    arq = caminho()
    if not arq.is_file():
        return Conexao()
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
        dados["etapa"] = Etapa(dados.get("etapa", "nao_conectado"))
        return Conexao(**{k: v for k, v in dados.items() if k in Conexao.__dataclass_fields__})
    except (ValueError, TypeError, json.JSONDecodeError):
        return Conexao()


def salvar(c: Conexao) -> Path:
    arq = caminho()
    dados = asdict(c)
    dados["etapa"] = c.etapa.value
    arq.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return arq


def apagar() -> bool:
    arq = caminho()
    if arq.is_file():
        arq.unlink()
        return True
    return False
