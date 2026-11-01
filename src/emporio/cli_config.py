"""Configuração do agente pelo CLI: `python -m emporio configurar` e os comandos /modelo e /config do chat.

    python -m emporio configurar                         menu interativo
    python -m emporio configurar --mostrar               mostra a configuração efetiva
    python -m emporio configurar --modelo haiku --raciocinio ligado --retencao ligada
    python -m emporio configurar --data-referencia 2026-03-25T10:00   (ou "nenhuma" para o relógio real)
    python -m emporio configurar --redefinir             apaga as preferências salvas

As escolhas ficam em `.emporio.json` (fora do git) e valem para as próximas conversas (ver preferencias.py).
"""

from __future__ import annotations

import argparse
from datetime import datetime

from emporio import modelos, preferencias
from emporio.config import Config, montar_llm
from emporio.llm import LLMIndisponivel
from emporio.llm.openrouter import parametros_zdr

LIGADO = {"ligado", "ligada", "sim", "s", "true", "on", "1"}
DESLIGADO = {"desligado", "desligada", "nao", "não", "n", "false", "off", "0"}


def bool_pt(texto: str) -> bool:
    t = texto.strip().lower()
    if t in LIGADO:
        return True
    if t in DESLIGADO:
        return False
    raise ValueError(f"use ligado ou desligado (recebido: {texto!r})")


def checar_zdr(slug: str) -> str:
    """Confere, na lista pública do OpenRouter, se o modelo tem endpoint ZDR com tools."""
    params = parametros_zdr(slug)
    if params is None:
        return "não foi possível consultar a lista ZDR agora (o agente confere de novo ao iniciar)"
    if not params:
        return "ATENÇÃO: sem endpoint ZDR com tools; o agente vai recusar as chamadas"
    return "endpoint ZDR com tools disponível"


def resumo(config: Config, prefs: dict, trocado_na_conversa: bool = False) -> str:
    def origem(chave: str) -> str:
        if chave == "modelo" and trocado_na_conversa:
            return " (trocado nesta conversa com /modelo)"
        return " (preferência salva)" if chave in prefs else ""
    ref = config.data_referencia.strftime("%d/%m/%Y %H:%M") if config.data_referencia else "nenhuma (relógio real)"
    return "\n".join([
        f"  Modelo:                 {modelos.descrever(config.openrouter_model)}{origem('modelo')}",
        f"  Raciocínio estendido:   {'ligado' if config.raciocinio else 'desligado'}{origem('raciocinio')}",
        f"  Retenção (inatividade): {'ligada' if config.retencao.ativa else 'desligada'}{origem('retencao')}",
        f"  Data de referência:     {ref}{origem('data_referencia')}",
        f"  Provedor do LLM:        {config.llm_provider} (sempre com Zero Data Retention)",
        f"  Chave do OpenRouter:    {'configurada' if config.openrouter_api_key else 'ausente (use --fake ou preencha o .env)'}",
        f"  Arquivo de preferências: {preferencias.caminho()}",
    ])


def listar_modelos(atual: str | None = None) -> str:
    linhas = []
    for i, o in enumerate(modelos.OPCOES, start=1):
        marca = "*" if o.slug == atual else " "
        linhas.append(f" {marca}{i}) {o.apelido:9} {o.nome}: {o.resumo}")
    return "\n".join(linhas)


def escolher_modelo(texto: str) -> str:
    """Número da lista, apelido ou slug -> slug."""
    t = texto.strip()
    if t.isdigit() and 1 <= int(t) <= len(modelos.OPCOES):
        return modelos.OPCOES[int(t) - 1].slug
    return modelos.resolver(t)


# ---------------------------------------------------------------- python -m emporio configurar

def configurar(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="emporio configurar", description="Configura o agente (salvo em .emporio.json)")
    ap.add_argument("--modelo", help=f"{', '.join(o.apelido for o in modelos.OPCOES)} ou slug do OpenRouter")
    ap.add_argument("--raciocinio", help="ligado ou desligado")
    ap.add_argument("--retencao", help="ligada ou desligada")
    ap.add_argument("--data-referencia", help='ISO 8601 (ex.: 2026-03-25T10:00) ou "nenhuma"')
    ap.add_argument("--mostrar", action="store_true", help="mostra a configuração efetiva")
    ap.add_argument("--redefinir", action="store_true", help="apaga as preferências salvas")
    ap.add_argument("--sem-verificar", action="store_true", help="não consulta a lista ZDR ao escolher o modelo")
    a = ap.parse_args(argv)

    if a.redefinir:
        print("Preferências apagadas." if preferencias.redefinir() else "Não havia preferências salvas.")
        return 0
    prefs = preferencias.carregar()
    if a.mostrar:
        print("Configuração efetiva do agente:\n" + resumo(Config.do_ambiente(), prefs))
        return 0
    try:
        if any(v is not None for v in (a.modelo, a.raciocinio, a.retencao, a.data_referencia)):
            if a.modelo is not None:
                prefs["modelo"] = escolher_modelo(a.modelo)
                if not a.sem_verificar:
                    print(f"{modelos.descrever(prefs['modelo'])}: {checar_zdr(prefs['modelo'])}")
            if a.raciocinio is not None:
                prefs["raciocinio"] = bool_pt(a.raciocinio)
            if a.retencao is not None:
                prefs["retencao"] = bool_pt(a.retencao)
            if a.data_referencia is not None:
                if a.data_referencia.strip().lower() in ("nenhuma", "real", ""):
                    prefs.pop("data_referencia", None)
                else:
                    datetime.fromisoformat(a.data_referencia)
                    prefs["data_referencia"] = a.data_referencia
        else:
            prefs = menu(prefs, verificar=not a.sem_verificar)
            if prefs is None:
                print("Nada foi salvo.")
                return 0
    except ValueError as e:
        print(f"Erro: {e}")
        return 2
    arq = preferencias.salvar(prefs)
    print(f"Salvo em {arq}.\n" + resumo(Config.do_ambiente(), preferencias.carregar()))
    return 0


def menu(prefs: dict, verificar: bool = True) -> dict | None:
    """Menu interativo. Devolve as preferências para salvar, ou None para sair sem salvar."""
    prefs = dict(prefs)
    while True:
        config = Config.do_ambiente().com_preferencias(prefs)
        print("\nConfiguração do agente (salva em .emporio.json)\n" + resumo(config, prefs))
        print("\n  1) Modelo   2) Raciocínio   3) Retenção   4) Data de referência   5) Salvar e sair   0) Sair sem salvar")
        try:
            op = input("Opção: ").strip()
        except EOFError:
            return None
        try:
            if op == "1":
                print(listar_modelos(config.openrouter_model))
                prefs["modelo"] = escolher_modelo(input("Modelo (número ou apelido): "))
                if verificar:
                    print(f"  {modelos.descrever(prefs['modelo'])}: {checar_zdr(prefs['modelo'])}")
            elif op == "2":
                prefs["raciocinio"] = bool_pt(input("Raciocínio estendido (ligado/desligado): "))
            elif op == "3":
                prefs["retencao"] = bool_pt(input("Retenção por inatividade (ligada/desligada): "))
            elif op == "4":
                v = input('Data de referência (ex.: 2026-03-25T10:00, ou "nenhuma"): ').strip()
                if v.lower() in ("nenhuma", "real", ""):
                    prefs.pop("data_referencia", None)
                else:
                    datetime.fromisoformat(v)
                    prefs["data_referencia"] = v
            elif op == "5":
                return prefs
            elif op == "0":
                return None
            else:
                print("  Opção inválida.")
        except ValueError as e:
            print(f"  {e}")
        except EOFError:
            return None


# ---------------------------------------------------------------- comandos do chat

def comando_config(agente, config: Config) -> str:
    from dataclasses import replace
    efetiva = replace(config, openrouter_model=agente.llm.modelo,
                      retencao=replace(config.retencao, ativa=bool(agente.retencao and agente.retencao.cfg.ativa)))
    trocado = config.llm_provider == "openrouter" and modelos.resolver(config.openrouter_model) != agente.llm.modelo
    return "Configuração desta conversa:\n" + resumo(efetiva, preferencias.carregar(), trocado)


def comando_modelo(agente, config: Config, arg: str) -> str:
    """/modelo sem argumento lista as opções; /modelo <número|apelido|slug> troca o modelo desta conversa."""
    if not arg.strip():
        return f"Modelo atual: {modelos.descrever(agente.llm.modelo)}\n{listar_modelos(agente.llm.modelo)}\n" \
               "Use /modelo <número ou apelido> para trocar nesta conversa (para salvar: python -m emporio configurar)."
    if config.llm_provider != "openrouter":
        return "No modo demonstração (--fake) não há modelo de linguagem para trocar."
    try:
        slug = escolher_modelo(arg)
        from dataclasses import replace
        novo = montar_llm(replace(config, openrouter_model=slug))
    except (ValueError, LLMIndisponivel) as e:
        return f"Não foi possível trocar: {e}"
    if getattr(novo, "suportados", None) == set():
        return f"{modelos.descrever(slug)} não tem endpoint ZDR com tools; modelo mantido."
    agente.llm = novo
    if agente.retencao is not None:
        agente.retencao.llm = novo
        agente.retencao.modo_fixo = novo.modelo.startswith("demo/")
    return f"Modelo trocado para {modelos.descrever(slug)} nesta conversa (ZDR obrigatório)."
