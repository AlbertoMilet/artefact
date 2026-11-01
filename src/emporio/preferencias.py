"""Preferências do agente salvas pelo `python -m emporio configurar` (arquivo `.emporio.json`, fora do git).

Precedência, da menor para a maior: valores padrão < `.env` e variáveis de ambiente < preferências
salvas < flags do comando (`chat --modelo`, `--fake`, `--retencao`). As preferências são escolha
explícita do usuário pelo CLI, por isso valem sobre o `.env`. Evals e geração de exemplos ignoram as
preferências, para serem reproduzíveis.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from emporio import modelos

CHAVES = {"modelo", "raciocinio", "retencao", "data_referencia"}


def caminho() -> Path:
    padrao = Path(__file__).resolve().parents[2] / ".emporio.json"
    return Path(os.getenv("EMPORIO_PREFERENCIAS", str(padrao)))


def validar(prefs: dict) -> dict:
    """Mantém só chaves conhecidas e valores válidos; erro claro para valor inválido."""
    out = {}
    for chave, valor in prefs.items():
        if chave not in CHAVES or valor is None:
            continue
        if chave == "modelo":
            out[chave] = modelos.resolver(str(valor))
        elif chave in ("raciocinio", "retencao"):
            if not isinstance(valor, bool):
                raise ValueError(f"{chave} deve ser verdadeiro ou falso")
            out[chave] = valor
        elif chave == "data_referencia":
            datetime.fromisoformat(str(valor))       # valida o formato
            out[chave] = str(valor)
    return out


def carregar() -> dict:
    arq = caminho()
    if not arq.is_file():
        return {}
    try:
        return validar(json.loads(arq.read_text(encoding="utf-8")))
    except (ValueError, json.JSONDecodeError):
        return {}                                    # arquivo corrompido não impede o agente de rodar


def salvar(prefs: dict) -> Path:
    arq = caminho()
    arq.write_text(json.dumps(validar(prefs), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return arq


def redefinir() -> bool:
    arq = caminho()
    if arq.is_file():
        arq.unlink()
        return True
    return False
