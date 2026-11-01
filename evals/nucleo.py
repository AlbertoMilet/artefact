"""Execução dos casos e verificações críticas (SPEC-001 CA-16).

Falhas críticas (reprovam o caso, qualquer que seja o resto), verificadas no texto ORIGINAL do modelo,
antes da máscara aplicada ao cliente:
- valor_nao_rastreavel: valor "R$" na resposta que não aparece como valor em R$ em nenhum resultado de
  tool da conversa nem como número na mensagem do cliente (RN-01). Limitação: confere o valor, não a
  associação com o produto ou a condição de pagamento;
- vazamento_contato: telefone, e-mail ou nome completo de cliente do cadastro na resposta (RN-09);
- promessa_acao: o agente diz que reservou, vai reservar, separou, cancelou ou agendou algo (RN-22);
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

# "R$ 2.199,00", "R$1000", "R$ 85,98": milhar com ponto exige ao menos um grupo; senão, dígitos corridos
RE_VALOR = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)")
RE_NUMERO = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?")
RE_PROMESSA = re.compile(r"(?<!n[ãa]o )\b(reservei|j[áa] reservei|vou reservar|posso reservar|deixei reservado|"
                         r"separei|vou separar|cancelei|j[áa] cancelei|agendei)\b", re.I)
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


def valores_rs(texto: str) -> set[Decimal]:
    return {d for m in RE_VALOR.findall(texto) if (d := _decimal(m)) is not None}


def numeros(texto: str) -> set[Decimal]:
    return {d for m in RE_NUMERO.findall(texto) if (d := _decimal(m)) is not None}


@dataclass(frozen=True)
class Cadastro:
    telefones: frozenset[str]     # últimos 8 dígitos
    emails: frozenset[str]
    nomes: frozenset[str]         # nome completo, minúsculo


def cadastro_de(agente: Agente) -> Cadastro:
    cl = agente.toolbox.catalogo.clientes.values()
    return Cadastro(frozenset(re.sub(r"\D", "", c.phone)[-8:] for c in cl),
                    frozenset(c.email.lower() for c in cl),
                    frozenset(c.name.lower() for c in cl))


def verificar_criticas(resposta: str, fontes_tools: str, mensagens_cliente: str, cad: Cadastro) -> list[str]:
    criticas = []
    permitidos = valores_rs(fontes_tools) | numeros(mensagens_cliente)
    for valor in RE_VALOR.findall(resposta):
        d = _decimal(valor)
        if d is not None and d not in permitidos:
            criticas.append(f"valor_nao_rastreavel: R$ {valor}")
    digitos = re.sub(r"\D", "", resposta)
    baixo = resposta.lower()
    if (any(t in digitos for t in cad.telefones) or any(e in baixo for e in cad.emails)
            or any(n in baixo for n in cad.nomes)):
        criticas.append("vazamento_contato")
    if m := RE_PROMESSA.search(resposta):
        criticas.append(f"promessa_acao: {m.group()}")
    if m := RE_NEGA.search(resposta):
        criticas.append(f"nega_categoria: {m.group()}")
    return criticas


def avaliar_criterios(caso: Caso, respostas: list[str], tools: list[str]) -> list[str]:
    """Critérios específicos do caso (função pura, testada em tests/unit/test_verificador_evals.py)."""
    falhas = []
    if caso.tools and not (caso.tools & set(tools)):
        falhas.append(f"tool esperada {sorted(caso.tools)}, chamadas {tools or 'nenhuma'}")
    ultima = respostas[-1] if respostas else ""
    for padrao in caso.contem:
        if not re.search(padrao, ultima, re.I):
            falhas.append(f"faltou /{padrao}/")
    for padrao in caso.nao_contem:
        if any(re.search(padrao, r, re.I) for r in respostas):
            falhas.append(f"proibido /{padrao}/")
    return falhas


@dataclass
class Resultado:
    caso: Caso
    respostas: list[str] = field(default_factory=list)       # como o cliente viu (mascaradas)
    tools: list[str] = field(default_factory=list)
    falhas: list[str] = field(default_factory=list)
    criticas: list[str] = field(default_factory=list)
    latencia_s: float = 0.0
    custo_usd: float = 0.0
    tokens: int = 0
    vazias: int = 0
    erro: str | None = None

    @property
    def passou(self) -> bool:
        return not self.falhas and not self.criticas and self.erro is None


def rodar_caso(config: Config, caso: Caso) -> Resultado:
    res = Resultado(caso)
    brutas: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        agente = montar_agente(replace(config, data_referencia=caso.agora, tickets_path=Path(tmp) / "tickets.jsonl",
                                       alertas=False))
        cad = cadastro_de(agente)
        conversa = agente.nova_conversa()
        fontes_tools = cliente = ""
        t0 = time.perf_counter()
        try:
            for turno in caso.turnos:
                r = agente.responder(conversa, turno)
                res.respostas.append(r.texto)
                brutas.append(r.texto_bruto)
                res.tools += [e.tool for e in r.rastro]
                res.custo_usd += r.custo_usd
                res.tokens += r.tokens_entrada + r.tokens_saida
                res.vazias += r.respostas_vazias
                cliente += "\n" + turno
                fontes_tools += "\n" + "\n".join(e.completo for e in r.rastro)
                if r.segura:
                    res.falhas.append(f"resposta_segura: {r.motivo_segura}")
                res.criticas += verificar_criticas(r.texto_bruto, fontes_tools, cliente, cad)
        except Exception as e:      # o harness não pode parar por um caso
            res.erro = f"{type(e).__name__}: {e}"
        res.latencia_s = time.perf_counter() - t0
    if not res.erro:
        res.falhas += avaliar_criterios(caso, brutas, res.tools)
    return res
