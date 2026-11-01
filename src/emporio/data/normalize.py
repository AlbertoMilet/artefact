"""Normalização de texto, marca e specs (SPEC-001 RN-13, A10, A11)."""

from __future__ import annotations

import re
import unicodedata

# Marcas presentes nos dados (nome e descrição). Ordem: nomes compostos antes.
MARCAS = [
    "Music Man", "Takamine", "Yamaha", "Fender", "Squier", "Gibson", "Epiphone", "Ibanez", "Tagima",
    "Giannini", "Rozini", "Shelby", "Strinberg", "Washburn", "Martin", "Taylor", "Cort", "Crafter",
    "PRS", "Kalani", "Kala", "Ohana",
    "Pearl", "Tama", "Ludwig", "Mapex", "Korg", "Roland", "Casio", "Kawai", "Nord",
]


def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento, só letras/dígitos e espaço simples."""
    t = sem_acento(texto.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


def compactar(texto: str) -> str:
    """Normaliza e remove espaços: 'Takamine GD 20' -> 'takaminegd20'."""
    return normalizar(texto).replace(" ", "")


def marcas_em(texto: str) -> set[str]:
    t = f" {normalizar(texto)} "
    return {m for m in MARCAS if f" {normalizar(m)} " in t}


def marca_do_nome(nome: str) -> str | None:
    """A marca vem do nome (RN-13). Sem marca conhecida, a primeira palavra do nome."""
    encontradas = [m for m in MARCAS if f" {normalizar(m)} " in f" {normalizar(nome)} "]
    if encontradas:
        return min(encontradas, key=lambda m: normalizar(nome).find(normalizar(m)))
    return None


def descricao_confiavel(nome: str, descricao: str) -> bool:
    """Falso quando a descrição cita marca diferente da do nome (A10: produtos 135, 137, 139...)."""
    no_nome, na_desc = marcas_em(nome), marcas_em(descricao)
    return not (no_nome and na_desc and not (no_nome & na_desc))


def normalizar_specs(specs: dict) -> dict:
    """`strings` vira `material_cordas` (texto) ou `num_cordas` (número), conforme o valor (A11)."""
    out = {}
    for chave, valor in specs.items():
        if chave == "strings":
            v = str(valor).strip()
            if v.isdigit():
                out["num_cordas"] = int(v)
            else:
                out["material_cordas"] = {"steel": "aço", "nylon": "nylon"}.get(v.lower(), v)
        else:
            out[chave] = valor
    return out
