"""Login do painel (SPEC-008): usuários no .env, senha só como hash, sessão em cookie assinado.

    EMPORIO_USUARIOS=carlos:pbkdf2_sha256$600000$<sal>$<hash>,ana:pbkdf2_sha256$...
    EMPORIO_SEGREDO_SESSAO=<64 caracteres hex>

A linha de cada usuário sai de `python -m emporio usuario criar <nome>` (pede a senha sem mostrar).
Só biblioteca padrão: PBKDF2-SHA256 com 600 mil iterações e HMAC-SHA256 no cookie.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass, field

ITERACOES = 600_000
DURACAO_SESSAO_S = 12 * 3600
TENTATIVAS_MAX = 5
BLOQUEIO_S = 60
NOME_VALIDO = re.compile(r"^[\w.@+-]{2,64}$")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _de_b64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_senha(senha: str, sal: bytes | None = None, iteracoes: int = ITERACOES) -> str:
    if len(senha or "") < 8:
        raise ValueError("a senha precisa de pelo menos 8 caracteres")
    sal = sal or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, iteracoes)
    return f"pbkdf2_sha256${iteracoes}${_b64(sal)}${_b64(dk)}"


def conferir_senha(senha: str, guardado: str) -> bool:
    try:
        algoritmo, iteracoes, sal, esperado = guardado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", (senha or "").encode(), _de_b64(sal), int(iteracoes))
        return hmac.compare_digest(dk, _de_b64(esperado))
    except (ValueError, TypeError):
        return False


def carregar_usuarios(texto: str | None = None) -> dict[str, str]:
    """`nome:hash,nome2:hash2` -> {nome: hash}. Entrada malformada ou senha em claro é recusada."""
    texto = os.getenv("EMPORIO_USUARIOS", "") if texto is None else texto
    usuarios: dict[str, str] = {}
    for item in filter(None, (x.strip() for x in texto.split(","))):
        nome, _, guardado = item.partition(":")
        if not NOME_VALIDO.match(nome) or not guardado.startswith("pbkdf2_sha256$") or guardado.count("$") != 3:
            raise ValueError(f"EMPORIO_USUARIOS: entrada inválida para '{nome[:20]}' (use `python -m emporio usuario criar`)")
        usuarios[nome] = guardado
    return usuarios


def segredo_da_sessao() -> tuple[bytes, bool]:
    """(segredo, veio_do_env). Sem EMPORIO_SEGREDO_SESSAO, um aleatório: as sessões caem ao reiniciar."""
    valor = os.getenv("EMPORIO_SEGREDO_SESSAO", "").strip()
    if valor:
        if len(valor) < 32:
            raise ValueError("EMPORIO_SEGREDO_SESSAO precisa de pelo menos 32 caracteres")
        return valor.encode(), True
    return secrets.token_bytes(32), False


@dataclass
class Sessoes:
    segredo: bytes
    duracao_s: int = DURACAO_SESSAO_S
    relogio: callable = time.time

    def emitir(self, usuario: str) -> str:
        expira = int(self.relogio()) + self.duracao_s
        corpo = f"{_b64(usuario.encode())}.{expira}"
        return f"{corpo}.{self._assinar(corpo)}"

    def validar(self, token: str | None) -> str | None:
        try:
            usuario_b64, expira, assinatura = (token or "").split(".")
            corpo = f"{usuario_b64}.{expira}"
            if not hmac.compare_digest(assinatura, self._assinar(corpo)) or int(expira) < self.relogio():
                return None
            return _de_b64(usuario_b64).decode()
        except (ValueError, TypeError):
            return None

    def _assinar(self, corpo: str) -> str:
        return _b64(hmac.new(self.segredo, corpo.encode(), hashlib.sha256).digest())


@dataclass
class Limitador:
    """Depois de 5 senhas erradas seguidas do mesmo endereço, 60 s de espera."""
    relogio: callable = time.time
    falhas: dict = field(default_factory=dict)

    def bloqueado(self, chave: str) -> int:
        n, ultimo = self.falhas.get(chave, (0, 0.0))
        falta = BLOQUEIO_S - (self.relogio() - ultimo)
        return int(falta) + 1 if n >= TENTATIVAS_MAX and falta > 0 else 0

    def falhou(self, chave: str) -> None:
        n, ultimo = self.falhas.get(chave, (0, 0.0))
        if n >= TENTATIVAS_MAX and self.relogio() - ultimo >= BLOQUEIO_S:
            n = 0
        self.falhas[chave] = (n + 1, self.relogio())

    def acertou(self, chave: str) -> None:
        self.falhas.pop(chave, None)
