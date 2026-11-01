"""CLI da conexão do WhatsApp da loja (SPEC-004).

    python -m emporio whatsapp conectar [--simulado] [--metodo SMS|VOICE]   guiado e retomável
    python -m emporio whatsapp status                                        etapa e próxima ação
    python -m emporio whatsapp reenviar-codigo [--simulado]                  novo código por SMS
    python -m emporio whatsapp desconectar                                   apaga a conexão salva
    python -m emporio whatsapp gerar-chave                                   chave Fernet para WHATSAPP_CHAVE_CIFRA

Modo real: META_APP_ID, META_APP_SECRET (app da Meta com o produto WhatsApp e Facebook Login) e, opcionais,
META_REDIRECT_URI (padrão http://localhost:8765/callback) e META_GRAPH_VERSION (padrão v25.0).
"""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from dotenv import load_dotenv

from emporio.whatsapp import conexao as arq
from emporio.whatsapp import regras
from emporio.whatsapp.conexao import Etapa
from emporio.whatsapp.fluxo import EtapaInvalida, Onboarding
from emporio.whatsapp.meta import ErroMeta, GraphMeta
from emporio.whatsapp.oauth_local import aguardar_retorno
from emporio.whatsapp.simulado import ProvedorSimulado

RAIZ = Path(__file__).resolve().parents[2]
REDIRECT_PADRAO = "http://localhost:8765/callback"
CODIGO_OAUTH_SIMULADO = "codigo-oauth-simulado"


def provedor(simulado: bool):
    if simulado:
        return ProvedorSimulado()
    return GraphMeta(os.getenv("META_APP_ID", "").strip(), os.getenv("META_APP_SECRET", "").strip(),
                     os.getenv("META_REDIRECT_URI", REDIRECT_PADRAO).strip(),
                     os.getenv("META_GRAPH_VERSION", "v25.0").strip())


def resumo(c) -> str:
    linhas = [f"Etapa: {c.etapa.value}"]
    if c.numero_exibicao:
        linhas.append(f"Número: {c.numero_exibicao} ({c.nome_verificado or 'sem nome'})")
    if c.waba_id:
        linhas.append(f"Conta do WhatsApp Business (WABA): {c.waba_id}")
    linhas.append(f"Token: {'salvo cifrado' if c.token_cifrado else 'não salvo'}"
                  + (f", expira em {c.token_expira_em[:10]}" if c.token_expira_em else ""))
    return "\n".join(linhas)


def _login(ob: Onboarding, simulado: bool) -> None:
    state = regras.novo_state()
    if simulado:
        print("Login com Facebook (simulado): autorização concedida.")
        code, recebido, erro = CODIGO_OAUTH_SIMULADO, state, None
    else:
        url = ob.p.url_login(state)
        print("Abrindo o navegador para o login com Facebook. Se não abrir, acesse:\n" + url)
        code, recebido, erro = aguardar_retorno(url, ob.p.redirect_uri)
    if erro or not code:
        raise EtapaInvalida(f"login não concluído: {erro or 'sem código de autorização'}")
    wabas = ob.autenticar(code, recebido, state)
    print(f"Login concluído. Contas do WhatsApp Business autorizadas: {', '.join(wabas)}")


def _escolher_numero(ob: Onboarding) -> None:
    numeros = ob.numeros()
    print("Números da conta:")
    for i, n in enumerate(numeros, start=1):
        print(f"  {i}) {n.exibicao}  {n.nome_verificado}  [{n.verificacao or '?'} / {n.status or '?'}]")
    print("  n) cadastrar um número novo")
    op = input("Escolha: ").strip().lower()
    if op == "n":
        numero = input("Número da loja com DDD (ex.: (67) 99999-0000): ")
        nome = input("Nome de exibição do negócio (ex.: Empório da Música): ")
        ob.cadastrar_numero(numero, nome)
    elif op.isdigit() and 1 <= int(op) <= len(numeros):
        ob.escolher_numero(numeros[int(op) - 1])
    else:
        print("Opção inválida.")


def conectar(simulado: bool, metodo: str) -> int:
    ob = Onboarding(provedor(simulado))
    print(resumo(ob.c) + f"\nPróxima ação: {ob.proxima_acao()}\n")
    if ob.precisa_login():
        _login(ob, simulado)
    while ob.c.etapa != Etapa.CONECTADO:
        try:
            if ob.c.etapa == Etapa.AUTENTICADO:
                _escolher_numero(ob)
            elif ob.c.etapa == Etapa.NUMERO_ESCOLHIDO:
                ob.pedir_codigo(metodo)
                via = "SMS" if metodo.upper() == "SMS" else "ligação"
                print(f"Código de confirmação enviado por {via} para {ob.c.numero_exibicao}.")
                if simulado:
                    print(f"  (simulado: o SMS diria {ob.p.ultimo_codigo})")
            elif ob.c.etapa == Etapa.CODIGO_ENVIADO:
                codigo = input("Código de 6 dígitos (ou r para reenviar): ").strip()
                if codigo.lower() == "r":
                    ob.pedir_codigo(metodo)
                    print("Novo código enviado." + (f" (simulado: {ob.p.ultimo_codigo})" if simulado else ""))
                    continue
                ob.confirmar_codigo(codigo)
                print("Número confirmado.")
            elif ob.c.etapa == Etapa.VERIFICADO:
                pin = getpass.getpass("Crie (ou informe) o PIN de duas etapas, 6 dígitos (não é salvo): ")
                ob.registrar(pin)
                print("Número registrado na WhatsApp Cloud API.")
            elif ob.c.etapa == Etapa.REGISTRADO:
                ob.assinar_webhooks()
                print("Webhooks assinados.")
        except (ErroMeta, EtapaInvalida, ValueError) as e:
            print(f"  {e}")
            if isinstance(e, EtapaInvalida) and "login" in str(e):
                return 2
        except (EOFError, KeyboardInterrupt):
            print(f"\nInterrompido. Etapa salva: {ob.c.etapa.value}. Rode `whatsapp conectar` para continuar.")
            return 1
    for aviso in ob.avisos:
        print(f"Aviso: {aviso}")
    print("\nWhatsApp da loja conectado.\n" + resumo(ob.c))
    return 0


def main(argv: list[str]) -> int:
    load_dotenv(RAIZ / ".env")
    ap = argparse.ArgumentParser(prog="emporio whatsapp", description="Conecta o WhatsApp da loja (SPEC-004)")
    sub = ap.add_subparsers(dest="acao", required=True)
    for nome, ajuda in (("conectar", "login com Facebook, código por SMS e registro"),
                        ("reenviar-codigo", "envia outro código de confirmação")):
        s = sub.add_parser(nome, help=ajuda)
        s.add_argument("--simulado", action="store_true", help="sem Meta e sem SMS de verdade")
        s.add_argument("--metodo", default="SMS", choices=["SMS", "VOICE", "sms", "voice"])
    sub.add_parser("status", help="etapa atual e próxima ação")
    sub.add_parser("desconectar", help="apaga a conexão salva neste computador")
    sub.add_parser("gerar-chave", help="gera uma chave Fernet para WHATSAPP_CHAVE_CIFRA")
    a = ap.parse_args(argv)
    try:
        if a.acao == "gerar-chave":
            print("Coloque no .env:\nWHATSAPP_CHAVE_CIFRA=" + arq.gerar_chave())
            return 0
        if a.acao == "status":
            c = arq.carregar()
            print(resumo(c) + f"\nPróxima ação: {Onboarding(ProvedorSimulado(), c, salvar=False).proxima_acao()}")
            for linha in c.historico[-8:]:
                print(f"  {linha}")
            return 0
        if a.acao == "desconectar":
            print("Conexão apagada." if arq.apagar() else "Não havia conexão salva.")
            return 0
        if a.acao == "reenviar-codigo":
            ob = Onboarding(provedor(a.simulado))
            ob.pedir_codigo(a.metodo)
            print("Novo código enviado.")
            return 0
        return conectar(a.simulado, a.metodo)
    except (ErroMeta, EtapaInvalida, ValueError) as e:
        print(f"Erro: {e}")
        return 2
