"""Busca BM25 nas subseções do manual (SPEC-001 D-04, Q 7.1).

O manual tem 8 páginas: não justifica banco vetorial. Cada subseção (### N.M), ou a seção inteira
quando não tem subseções, vira um trecho citável ("§4.1 Direito de Arrependimento"). A consulta
passa por normalização, remoção de palavras vazias, sinônimos e radical por prefixo, que bastam
para o português deste corpus ("arrependi" ~ "arrependimento", "parcelar" ~ "parcelamento").
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from emporio.data.normalize import normalizar

MANUAL_PADRAO = Path(__file__).with_name("manual.md")

PALAVRAS_VAZIAS = set("""
a o as os um uma uns umas de do da dos das no na nos nas em para pra por com sem e ou que se
eu voce voces vcs meu minha meus minhas seu sua nosso nossa ele ela isso esse essa este esta
qual quais quando como onde quanto quantos quantas posso pode podem consigo gostaria queria
quero tem ter ha sao ser foi vai vou ja nao sim mais muito tambem sobre ai la aqui
""".split())

# termo do cliente -> termos do manual (antes do radical)
SINONIMOS = {
    "devolver": "devolucao arrependimento", "devolvo": "devolucao arrependimento",
    "desistir": "arrependimento devolucao", "desisti": "arrependimento devolucao",
    "arrependi": "arrependimento", "reembolso": "reembolso devolucao",
    "trocar": "troca trocas", "parcelar": "parcelamento parcela", "parcelado": "parcelamento",
    "vezes": "parcelamento parcela", "cartao": "cartao credito parcelamento",
    "pagar": "pagamento formas", "pago": "pagamento", "boleto": "boleto pagamento",
    "entrega": "entregas frete prazo", "entregar": "entregas frete", "chega": "entregas prazo",
    "enviar": "envios frete", "rastrear": "rastreamento", "rastreio": "rastreamento codigo",
    "horario": "horario funcionamento", "abre": "horario funcionamento", "fecha": "horario funcionamento",
    "aberto": "horario funcionamento", "abertos": "horario funcionamento", "sabado": "sabado horario",
    "domingo": "domingo feriados", "feriado": "feriados horario",
    "endereco": "endereco dados empresa", "telefone": "telefone whatsapp dados", "email": "mail dados",
    "cnpj": "cnpj dados empresa", "defeito": "defeito garantia", "quebrou": "defeito garantia",
    "estragou": "defeito garantia", "promocao": "promocoes desconto", "desconto": "desconto promocoes",
    "black": "black friday promocoes", "acessorio": "acessorios", "acessorios": "acessorios escopo",
    "corda": "cordas acessorios", "palheta": "palhetas acessorios", "amplificador": "amplificadores acessorios",
    "pedal": "pedais acessorios", "dados": "dados privacidade lgpd", "privacidade": "privacidade lgpd",
    "excluir": "exclusao dados", "reclamacao": "reclamacao", "reclamar": "reclamacao",
    "frete": "frete entregas envios cidades", "cidade": "cidades envios", "interior": "cidades envios",
    "vende": "comercializamos trabalhamos exclusivamente", "vendem": "comercializamos trabalhamos exclusivamente",
    "vender": "comercializamos trabalhamos", "venda": "comercializamos",
}

RADICAL = 5      # prefixo usado como radical
K1, B = 1.5, 0.75


def radicais(texto: str, expandir: bool = False) -> list[str]:
    termos = []
    for t in normalizar(texto).split():
        if t in PALAVRAS_VAZIAS or len(t) < 2:
            continue
        termos.append(t)
        if expandir and t in SINONIMOS:
            termos.extend(SINONIMOS[t].split())
    return [t[:RADICAL] for t in termos]


@dataclass(frozen=True)
class Trecho:
    secao: str       # "§4.1"
    titulo: str      # "Direito de Arrependimento (Compras Online)"
    texto: str

    def citar(self) -> str:
        return f"{self.secao} {self.titulo}"


class Manual:
    def __init__(self, texto_md: str):
        self.trechos = self._dividir(texto_md)
        self.secoes = self._indice(texto_md)
        self._docs = [Counter(radicais(f"{t.titulo} {t.titulo} {t.texto}")) for t in self.trechos]
        self._tam = [sum(d.values()) for d in self._docs]
        self._media = sum(self._tam) / len(self._tam)
        n = len(self._docs)
        df = Counter(term for d in self._docs for term in d)
        self._idf = {term: math.log(1 + (n - f + 0.5) / (f + 0.5)) for term, f in df.items()}

    @staticmethod
    def _limpar(md: str) -> str:
        return re.sub(r"<!--.*?-->", "", md, flags=re.S)

    def _dividir(self, md: str) -> list[Trecho]:
        trechos = []
        for bloco in re.split(r"(?m)^## ", self._limpar(md))[1:]:
            cab, _, corpo = bloco.partition("\n")
            m = re.match(r"§(\d+)\s+(.*)", cab.strip())
            num, titulo = m.group(1), m.group(2)
            partes = re.split(r"(?m)^### ", corpo)
            intro = partes[0].strip()
            subs = partes[1:]
            if not subs:
                trechos.append(Trecho(f"§{num}", titulo, intro))
                continue
            if intro:
                trechos.append(Trecho(f"§{num}", titulo, intro))
            for s in subs:
                scab, _, scorpo = s.partition("\n")
                sm = re.match(r"(\d+\.\d+)\s+(.*)", scab.strip())
                trechos.append(Trecho(f"§{sm.group(1)}", f"{sm.group(2)} ({titulo})", scorpo.strip()))
        return trechos

    def _indice(self, md: str) -> list[str]:
        return [f"§{m.group(1)} {m.group(2)}" for m in re.finditer(r"(?m)^## §(\d+)\s+(.*)$", self._limpar(md))]

    def pontuar(self, pergunta: str) -> list[tuple[float, Trecho]]:
        consulta = radicais(pergunta, expandir=True)
        res = []
        for doc, tam, trecho in zip(self._docs, self._tam, self.trechos):
            s = 0.0
            for q in consulta:
                f = doc.get(q, 0)
                if f:
                    s += self._idf[q] * f * (K1 + 1) / (f + K1 * (1 - B + B * tam / self._media))
            res.append((s, trecho))
        return sorted(res, key=lambda x: -x[0])

    def buscar(self, pergunta: str, limite: int = 3, minimo: float = 3.0) -> list[Trecho]:
        """Até `limite` trechos com pontuação >= `minimo`; lista vazia quando nada é relevante."""
        return [t for s, t in self.pontuar(pergunta)[:limite] if s >= minimo]


def carregar_manual(caminho: Path | str = MANUAL_PADRAO) -> Manual:
    return Manual(Path(caminho).read_text(encoding="utf-8"))
