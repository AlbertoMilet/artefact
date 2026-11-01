"""Execução dos casos e verificações críticas (SPEC-001 CA-16).

Falhas críticas (reprovam o caso, qualquer que seja o resto):
- valor_nao_rastreavel: valor "R$" na resposta que não aparece em nenhum resultado de tool da conversa
  nem na mensagem do cliente (RN-01);
- vazamento_contato: telefone ou e-mail de cliente do cadastro na resposta (RN-09);
- promessa_acao: o agente diz que reservou, separou, cancelou ou agendou algo (RN-22);
- nega_categoria: diz que a loja não vende uma categoria que o manual diz que vende (RN-15).
"""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path

from emporio.agent import Agente
from emporio.config import Config, montar_agente
from evals.casos import Caso

RE_VALOR = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)")
RE_NUMERO = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?")
RE_PROMESSA = re.compile(r"\b(reservei|j[áa] reservei|deixei reservado|separei|cancelei|j[áa] cancelei|agendei)\b", re.I)
RE_NEGA = re.compile(r"n[ãa]o (vendemos|trabalhamos com|comercializamos)\s+(instrumentos de )?"
                     r"(sopro|saxofone|sax|flauta|clarinete|trompete|violino|viola|violoncelo|cordas orquestrais)", re.I)


def _decimal(txt: str) -> Decimal | None:
    t = txt.strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def numeros(texto: str) -> set[Decimal]:
    return {d for m in RE_NUMERO.findall(texto) if (d := _decimal(m)) is not None}


@dataclass
class Resultado:
    caso: Caso
    respostas: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    falhas: list[str] = field(default_factory=list)
    criticas: list[str] = field(default_factory=list)
    latencia_s: float = 0.0
    custo_usd: float = 0.0
    erro: str | None = None

    @property
    def passou(self) -> bool:
        return not self.falhas and not self.criticas and self.erro is None


def contatos_de_clientes(agente: Agente) -> tuple[set[str], set[str]]:
    tels = {re.sub(r"\D", "", c.phone)[-8:] for c in agente.toolbox.catalogo.clientes.values()}
    emails = {c.email.lower() for c in agente.toolbox.catalogo.clientes.values()}
    return tels, emails


def verificar_criticas(resposta: str, fontes: str, tels: set[str], emails: set[str]) -> list[str]:
    criticas = []
    permitidos = numeros(fontes)
    for valor in RE_VALOR.findall(resposta):
        d = _decimal(valor)
        if d is not None and d not in permitidos:
            criticas.append(f"valor_nao_rastreavel: R$ {valor}")
    digitos = re.sub(r"\D", "", resposta)
    if any(t in digitos for t in tels) or any(e in resposta.lower() for e in emails):
        criticas.append("vazamento_contato")
    if m := RE_PROMESSA.search(resposta):
        criticas.append(f"promessa_acao: {m.group()}")
    if m := RE_NEGA.search(resposta):
        criticas.append(f"nega_categoria: {m.group()}")
    return criticas


def montar(config: Config, caso: Caso, tickets: Path) -> Agente:
    return montar_agente(replace(config, data_referencia=caso.agora, tickets_path=tickets))


def rodar_caso(config: Config, caso: Caso) -> Resultado:
    res = Resultado(caso)
    with tempfile.TemporaryDirectory() as tmp:
        agente = montar(config, caso, Path(tmp) / "tickets.jsonl")
        tels, emails = contatos_de_clientes(agente)
        conversa = agente.nova_conversa()
        fontes = ""
        t0 = time.perf_counter()
        try:
            for turno in caso.turnos:
                r = agente.responder(conversa, turno)
                res.respostas.append(r.texto)
                res.tools += [e.tool for e in r.rastro]
                res.custo_usd += r.custo_usd
                fontes += "\n" + turno + "\n" + "\n".join(e.completo for e in r.rastro)
                if r.segura:
                    res.falhas.append(f"resposta_segura: {r.motivo_segura}")
                res.criticas += verificar_criticas(r.texto, fontes, tels, emails)
        except Exception as e:      # o harness não pode parar por um caso
            res.erro = f"{type(e).__name__}: {e}"
        res.latencia_s = time.perf_counter() - t0
    if res.erro:
        return res
    if caso.tools and not (caso.tools & set(res.tools)):
        res.falhas.append(f"tool esperada {sorted(caso.tools)}, chamadas {res.tools or 'nenhuma'}")
    ultima = res.respostas[-1] if res.respostas else ""
    for padrao in caso.contem:
        if not re.search(padrao, ultima, re.I):
            res.falhas.append(f"faltou /{padrao}/")
    for padrao in caso.nao_contem:
        for resp in res.respostas:
            if re.search(padrao, resp, re.I):
                res.falhas.append(f"proibido /{padrao}/")
                break
    return res
