"""Verificação do dono do pedido e máscara de dados pessoais (RN-08, RN-09, RN-24; §9).

A verificação confere o cadastro; não prova que quem conversa é o dono (simulação, README).
"""

from __future__ import annotations

import re

from emporio.data.models import Cliente


def _digitos(texto: str) -> str:
    d = re.sub(r"\D", "", texto)
    if d.startswith("55") and len(d) in (12, 13):   # +55 DDD número
        d = d[2:]
    return d


def verificar_dono(cliente: Cliente, informado: str) -> bool:
    """Telefone (com ou sem DDD, com ou sem +55) ou e-mail que confere com o cadastro."""
    informado = (informado or "").strip()
    if not informado:
        return False
    if "@" in informado:
        return informado.casefold() == cliente.email.strip().casefold()
    dig, cad = _digitos(informado), _digitos(cliente.phone)
    if len(dig) < 8:
        return False
    return dig == cad or (len(dig) in (8, 9) and cad.endswith(dig))


def cliente_do_telefone(clientes, telefone: str | None):
    """Cliente cujo telefone do cadastro é exatamente o número do remetente no WhatsApp (SPEC-011 RP-02, RP-03).

    `clientes`: iterável de Cliente. Exige DDD + número (sem o +55); sufixo não basta. Nenhum ou mais de um
    cliente com o número: None."""
    dig = _digitos(telefone or "")
    if len(dig) < 10:
        return None
    achados = [c for c in clientes if _digitos(c.phone) == dig]
    return achados[0] if len(achados) == 1 else None


def mascarar_telefone(telefone: str) -> str:
    """'(67) 99654-7821' -> '(67) 9****-7821'."""
    d = _digitos(telefone)
    if len(d) < 8:
        return "<telefone>"
    ddd, numero = (d[:2], d[2:]) if len(d) >= 10 else ("", d)
    mascarado = numero[0] + "*" * (len(numero) - 5) + "-" + numero[-4:]
    return f"({ddd}) {mascarado}" if ddd else mascarado


def mascarar_email(email: str) -> str:
    """'anacarol.ferreira@coldmail.com' -> 'a***@coldmail.com'."""
    if "@" not in email:
        return "<e-mail>"
    usuario, dominio = email.split("@", 1)
    return f"{usuario[:1]}***@{dominio}"


_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
# Telefone com DDD (com ou sem +55, parênteses e separadores) ou só o número local (8 ou 9 dígitos,
# formatos aceitos por verificar_dono). Os limites (?<![\w-]) e (?![\w-]) impedem casar dentro de
# identificadores como o protocolo "SIM-20260325-0001" ou o rastreio "BRJL5544332BR".
_RE_TELEFONE = re.compile(
    r"(?<![\w-])(?:"
    r"(?:\+?55[\s.]?)?\(?\d{2}\)?[\s.]?9?[\s.]?\d{4}[-\s.]?\d{4}"   # com DDD (separador: espaço, ponto, hífen)
    r"|9?\d{4}[-\s.]\d{4}"                              # local com separador
    r"|9\d{8}"                                          # celular local sem separador
    r"|[2-5]\d{7}"                                      # fixo local sem separador (fixos começam com 2 a 5)
    r")(?![\w-])")


# CPF e CEP formatados (SPEC-012 RL-08), com os mesmos limites do telefone
_RE_CPF = re.compile(r"(?<![\w.-])\d{3}\.\d{3}\.\d{3}-(\d{2})(?![\w-])")
_RE_CEP = re.compile(r"(?<![\w-])(\d{2})\d{3}-\d{3}(?![\w-])")
_RE_CEP_SEM_HIFEN = re.compile(r"(?i)(\bcep\s*:?\s*)(\d{2})\d{6}(?![\w-])")      # só depois da palavra CEP

# Contatos públicos da loja: não são dado pessoal e não são mascarados (só os exatos)
CONTATOS_PUBLICOS_DIGITOS = {"6733414444", "6733214500"}
CEPS_PUBLICOS = {"79202-333", "79202333"}         # endereço da loja
EMAILS_PUBLICOS = {"contato@emporiodamusica.com.br", "contato@empóriodamusica.com.br"}


def mascarar_texto(texto: str) -> str:
    """Mascara e-mails, telefones, CPF e CEP de clientes em texto livre (logs, --debug, histórico, exportações)."""
    def email(m):
        e = m.group()
        nucleo = e.rstrip(".")                 # ponto final da frase não faz parte do e-mail
        sufixo = e[len(nucleo):]
        return e if nucleo.lower() in EMAILS_PUBLICOS else mascarar_email(nucleo) + sufixo

    def tel(m):
        return m.group() if _digitos(m.group()) in CONTATOS_PUBLICOS_DIGITOS else mascarar_telefone(m.group())

    def cep(m):
        return m.group() if m.group() in CEPS_PUBLICOS else f"{m.group(1)}***-***"

    texto = _RE_CPF.sub(lambda m: f"***.***.***-{m.group(1)}", texto)
    texto = _RE_CEP.sub(cep, texto)
    texto = _RE_CEP_SEM_HIFEN.sub(lambda m: m.group() if m.group()[len(m.group(1)):] in CEPS_PUBLICOS
                                  else f"{m.group(1)}{m.group(2)}***-***", texto)
    return _RE_TELEFONE.sub(tel, _RE_EMAIL.sub(email, texto))
