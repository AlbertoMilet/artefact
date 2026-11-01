"""Estado da conexão do WhatsApp da loja, salvo e retomável (SPEC-004 §4.1, RW-06, RW-08).

O token da Meta é salvo só cifrado com Fernet (chave em WHATSAPP_CHAVE_CIFRA), como no crypto.py do
Trato Fácil, mas sem derrubar a aplicação quando a chave falta: aí os IDs são salvos e o token não.
Real e simulado usam arquivos separados e a conexão guarda o ambiente e o app (revisão do Codex).
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
    ASSINADO = "app_assinado"        # número registrado e app assinado na WABA; falta o webhook HTTPS


ORDEM = list(Etapa)


@dataclass
class Conexao:
    etapa: Etapa = Etapa.NAO_CONECTADO
    ambiente: str = "real"                      # "real" ou "simulado"
    app_id: str | None = None                   # app da Meta que autorizou (não mistura conexões de apps)
    waba_id: str | None = None
    phone_number_id: str | None = None
    numero_exibicao: str | None = None
    nome_verificado: str | None = None
    token_cifrado: str | None = None
    token_expira_em: str | None = None           # ISO 8601 com fuso, quando a Meta informa
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
        self.historico = self.historico[-50:]


class ConexaoCorrompida(RuntimeError):
    pass


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

def caminho(simulado: bool = False) -> Path:
    padrao = Path(__file__).resolve().parents[3] / ".emporio_whatsapp.json"
    real = Path(os.getenv("WHATSAPP_CONEXAO", str(padrao)))
    return real.with_name(real.stem + "_simulado" + real.suffix) if simulado else real


def carregar(simulado: bool = False) -> Conexao:
    arq = caminho(simulado)
    if not arq.is_file():
        return Conexao(ambiente="simulado" if simulado else "real")
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
        if dados.get("etapa") == "conectado":                 # nome antigo da etapa final
            dados["etapa"] = Etapa.ASSINADO.value
        dados["etapa"] = Etapa(dados.get("etapa", "nao_conectado"))
        return Conexao(**{k: v for k, v in dados.items() if k in Conexao.__dataclass_fields__})
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        raise ConexaoCorrompida(f"arquivo de conexão ilegível ({arq.name}): confira ou rode `whatsapp desconectar`"
                                f"{' --simulado' if simulado else ''}") from e


def salvar(c: Conexao) -> Path:
    """Escrita atômica: grava num temporário e troca (interrupção não deixa o arquivo pela metade)."""
    arq = caminho(c.ambiente == "simulado")
    dados = asdict(c)
    dados["etapa"] = c.etapa.value
    tmp = arq.with_name(arq.name + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, arq)
    return arq


def apagar(simulado: bool = False) -> bool:
    arq = caminho(simulado)
    if arq.is_file():
        arq.unlink()
        return True
    return False
