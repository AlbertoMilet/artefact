"""Modelos oferecidos no CLI, todos via OpenRouter com Zero Data Retention (D-02).

Cada opção foi conferida na lista pública de endpoints ZDR com suporte a tools
(`GET https://openrouter.ai/api/v1/endpoints/zdr`) em 01/11/2026. Outro slug do OpenRouter também é
aceito, mas só funciona se tiver endpoint ZDR (o cliente recusa sem fallback).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpcaoModelo:
    apelido: str
    slug: str
    nome: str
    resumo: str


OPCOES: tuple[OpcaoModelo, ...] = (
    OpcaoModelo("deepseek", "deepseek/deepseek-v4.1-flash", "DeepSeek V4.1 Flash",
                "padrão (D-10): tom mais próximo da loja, o mais rápido e o mais barato; mais de 30 endpoints ZDR"),
    OpcaoModelo("haiku", "anthropic/claude-haiku-5.5", "Claude Haiku 5.5",
                "cuidadoso e correto; mais lento que o DeepSeek; ZDR via Amazon Bedrock e Google"),
    OpcaoModelo("gpt-sol", "openai/gpt-6.1-sol", "GPT-6.1 Sol",
                "modelo maior da OpenAI; o mais caro das três opções (cerca de 50x o DeepSeek); ZDR só via Azure"),
)

PADRAO = OPCOES[0]


def por_apelido(apelido: str) -> OpcaoModelo | None:
    a = apelido.strip().lower()
    return next((o for o in OPCOES if o.apelido == a), None)


def por_slug(slug: str) -> OpcaoModelo | None:
    return next((o for o in OPCOES if o.slug == slug), None)


def resolver(nome: str) -> str:
    """Apelido ("haiku") ou slug do OpenRouter ("anthropic/claude-haiku-5.5") -> slug."""
    nome = (nome or "").strip()
    if not nome:
        return PADRAO.slug
    if opcao := por_apelido(nome):
        return opcao.slug
    if "/" in nome:
        return nome
    validos = ", ".join(o.apelido for o in OPCOES)
    raise ValueError(f"modelo desconhecido: {nome!r}. Use {validos} ou um slug do OpenRouter (provedor/modelo)")


def descrever(slug: str) -> str:
    o = por_slug(slug)
    return f"{o.apelido} ({o.nome})" if o else slug
