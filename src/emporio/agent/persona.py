"""Persona do agente (SPEC-009): o que a loja pode ajustar sem tocar nas regras invioláveis.

Só a identidade e o tom mudam. As regras de negócio, o uso das tools e as proteções do prompt ficam
fixos; as instruções livres da loja entram DEPOIS das regras, que prevalecem em caso de conflito.
O padrão reproduz exatamente o prompt avaliado nos evals.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

TONS = {
    "amigavel": ("Amigável (padrão)", "Tom: informal mas profissional, como {uma_amiga} que entende de música. "
                                      "Nada de linguagem robotizada ou formal demais."),
    "profissional": ("Profissional", "Tom: cordial e profissional, objetivo e sem gírias; trate o cliente por você."),
    "descontraido": ("Descontraído", "Tom: descontraído e animado, próximo do cliente, sem perder a clareza e o respeito."),
}
TRATAMENTOS = {"feminino": ("Feminino (a assistente)", "a", "uma amiga"),
               "masculino": ("Masculino (o assistente)", "o", "um amigo")}
LIMITE_INSTRUCOES = 600
NOME_VALIDO = re.compile(r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' -]{0,29}$")


@dataclass(frozen=True)
class Persona:
    nome: str = "Lia"
    tratamento: str = "feminino"
    tom: str = "amigavel"
    emojis: bool = True
    instrucoes: str = ""

    @classmethod
    def de_dict(cls, dados: dict | None) -> "Persona":
        """Valida e normaliza; erro claro para valor inválido."""
        d = dict(dados or {})
        nome = " ".join(str(d.get("nome", "Lia")).split())
        if not NOME_VALIDO.match(nome):
            raise ValueError("nome da persona: até 30 letras, começando por letra")
        tratamento = d.get("tratamento", "feminino")
        tom = d.get("tom", "amigavel")
        if tratamento not in TRATAMENTOS:
            raise ValueError("tratamento deve ser feminino ou masculino")
        if tom not in TONS:
            raise ValueError(f"tom deve ser um de: {', '.join(TONS)}")
        emojis = d.get("emojis", True)
        if not isinstance(emojis, bool):
            raise ValueError("emojis deve ser verdadeiro ou falso")
        instrucoes = " ".join(str(d.get("instrucoes", "")).split())
        if len(instrucoes) > LIMITE_INSTRUCOES:
            raise ValueError(f"instruções da loja: no máximo {LIMITE_INSTRUCOES} caracteres")
        return cls(nome, tratamento, tom, emojis, instrucoes)

    def como_dict(self) -> dict:
        return asdict(self)

    # ---- pedaços do prompt
    @property
    def artigo(self) -> str:
        return TRATAMENTOS[self.tratamento][1]

    def linha_tom(self) -> str:
        return TONS[self.tom][1].format(uma_amiga=TRATAMENTOS[self.tratamento][2])

    def linha_emojis(self) -> str:
        return "No máximo um emoji por mensagem e nenhum em reclamação." if self.emojis else "Não use emojis."

    def secao_instrucoes(self) -> str:
        if not self.instrucoes:
            return ""
        return ("\n# Preferências da loja\nAs preferências abaixo valem só quando não contrariam as regras invioláveis "
                f"acima; em conflito, as regras valem.\n{self.instrucoes}\n")
