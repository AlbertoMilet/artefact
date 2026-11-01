"""CLI da conexão do WhatsApp da loja (SPEC-004).

    python -m emporio whatsapp conectar [--simulado] [--metodo SMS|VOICE]   guiado e retomável
    python -m emporio whatsapp status [--simulado]                           etapa e próxima ação
    python -m emporio whatsapp reenviar-codigo [--simulado]                  novo código por SMS
    python -m emporio whatsapp desconectar [--simulado]                      apaga a conexão salva
    python -m emporio whatsapp gerar-chave                                   chave Fernet para WHATSAPP_CHAVE_CIFRA

Modo real: META_APP_ID, META_APP_SECRET (app da Meta com o produto WhatsApp e Facebook Login) e, opcionais,
META_REDIRECT_URI (padrão http://localhost:8765/callback), META_GRAPH_VERSION (padrão v25.0) e META_WABA_ID
(quando o login não informar a conta do WhatsApp Business). Real e simulado usam arquivos separados.
"""

from __future__ import annotations

import argparse
import getpass
import os
import warnings
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from emporio.whatsapp import conexao as arq
from emporio.whatsapp import regras
from emporio.whatsapp.conexao import ConexaoCorrompida, Etapa
from emporio.whatsapp.fluxo import EtapaInvalida, Onboarding, PrecisaLogin, _agora_fuso
from emporio.whatsapp.meta import ErroMeta, GraphMeta
from emporio.whatsapp.oauth_local import aguardar_retorno
from emporio.whatsapp.simulado import ProvedorSimulado

RAIZ = Path(__file__).resolve().parents[2]
REDIRECT_PADRAO = "http://localhost:8765/callback"
CODIGO_OAUTH_SIMULADO = "codigo-oauth-simulado"
CODIGO_SMS_SIMULADO = "123456"
ERROS_SEGUIDOS_MAX = 5


def provedor(simulado: bool):
    if simulado:
        return ProvedorSimulado(codigo_fixo=CODIGO_SMS_SIMULADO, estrito=False)
    redirect = os.getenv("META_REDIRECT_URI", REDIRECT_PADRAO).strip()
    regras.validar_redirect(redirect)
    return GraphMeta(os.getenv("META_APP_ID", "").strip(), os.getenv("META_APP_SECRET", "").strip(), redirect,
                     os.getenv("META_GRAPH_VERSION", "v25.0").strip())


def resumo(c) -> str:
    linhas = [f"Etapa: {c.etapa.value}" + (" (simulado)" if c.ambiente == "simulado" else "")]
    if c.numero_exibicao:
        linhas.append(f"Número: {c.numero_exibicao} ({c.nome_verificado or 'sem nome'})")
    if c.waba_id:
        linhas.append(f"Conta do WhatsApp Business (WABA): {c.waba_id}")
    linhas.append(f"Token: {'salvo cifrado' if c.token_cifrado else 'não salvo'}"
                  + (f", expira em {c.token_expira_em[:10]}" if c.token_expira_em else ""))
    return "\n".join(linhas)


def _escolher_waba(wabas: list[str]) -> str:
    print("Mais de uma conta do WhatsApp Business foi autorizada:")
    for i, w in enumerate(wabas, start=1):
        print(f"  {i}) {w}")
    op = input("Qual conta usar? ").strip()
    return wabas[int(op) - 1] if op.isdigit() and 1 <= int(op) <= len(wabas) else op


def _login(ob: Onboarding, simulado: bool) -> None:
    state = regras.novo_state()
    if simulado:
        print("Login com Facebook (simulado): autorização concedida.")
        code, recebido, erro = CODIGO_OAUTH_SIMULADO, state, None
    else:
        url = ob.p.url_login(state)
        print("Abrindo o navegador para o login com Facebook. Se não abrir, acesse:\n" + url)
        code, recebido, erro = aguardar_retorno(url, ob.p.redirect_uri, state)
    if erro or not code:
        raise EtapaInvalida(f"login não concluído: {erro or 'sem código de autorização'}")
    wabas = ob.autenticar(code, recebido, state, escolher_waba=_escolher_waba,
                          waba_reserva=os.getenv("META_WABA_ID", "").strip() or None)
    print(f"Login concluído. Conta do WhatsApp Business: {ob.c.waba_id} (autorizadas: {', '.join(wabas)})")


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
        raise ValueError("opção inválida")


def _ler_pin() -> str:
    """getpass que não consegue esconder a digitação vira erro: o PIN nunca é ecoado."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass("Crie (ou informe) o PIN de duas etapas, 6 dígitos (não é salvo): ")
        except getpass.GetPassWarning:
            raise EtapaInvalida("o PIN exige um terminal interativo que esconda a digitação") from None


def conectar(simulado: bool, metodo: str) -> int:
    ob = Onboarding(provedor(simulado), simulado=simulado)
    print(resumo(ob.c) + f"\nPróxima ação: {ob.proxima_acao()}\n")
    if ob.precisa_login():
        _login(ob, simulado)
    erros_seguidos = 0
    while ob.c.etapa != Etapa.ASSINADO:
        etapa = ob.c.etapa
        automatica = etapa in (Etapa.NUMERO_ESCOLHIDO, Etapa.REGISTRADO)
        try:
            if etapa == Etapa.AUTENTICADO:
                _escolher_numero(ob)
            elif etapa == Etapa.NUMERO_ESCOLHIDO:
                ob.pedir_codigo(metodo)
                via = "SMS" if metodo.upper() == "SMS" else "ligação"
                print(f"Código de confirmação enviado por {via} para {ob.c.numero_exibicao}.")
                if simulado:
                    print(f"  (simulado: o SMS diria {ob.p.ultimo_codigo})")
            elif etapa == Etapa.CODIGO_ENVIADO:
                codigo = input("Código de 6 dígitos (ou r para reenviar): ").strip()
                if codigo.lower() == "r":
                    ob.pedir_codigo(metodo)
                    print("Novo código enviado." + (f" (simulado: {ob.p.ultimo_codigo})" if simulado else ""))
                    continue
                ob.confirmar_codigo(codigo)
                print("Número confirmado.")
            elif etapa == Etapa.VERIFICADO:
                ob.registrar(_ler_pin())
                print("Número registrado na WhatsApp Cloud API.")
            elif etapa == Etapa.REGISTRADO:
                ob.assinar_webhooks()
                print("App assinado na conta do WhatsApp Business.")
            erros_seguidos = 0
        except PrecisaLogin as e:
            print(f"  {e}")
            return 2
        except (ErroMeta, EtapaInvalida, ValueError) as e:
            print(f"  {e}")
            erros_seguidos += 1
            if automatica or erros_seguidos >= ERROS_SEGUIDOS_MAX:
                # etapa automática não repete sozinha a chamada à Meta (revisão do Codex: loop sem fim)
                print(f"Parado na etapa {ob.c.etapa.value}. Corrija e rode `whatsapp conectar` para continuar.")
                return 2
        except (EOFError, KeyboardInterrupt):
            print(f"\nInterrompido. Etapa salva: {ob.c.etapa.value}. Rode `whatsapp conectar` para continuar.")
            return 1
    for aviso in ob.avisos:
        print(f"Aviso: {aviso}")
    print("\nNúmero registrado e app assinado. Para receber mensagens pelo WhatsApp falta o webhook HTTPS "
          "(fora do escopo do protótipo).\n" + resumo(ob.c))
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
    for nome, ajuda in (("status", "etapa atual e próxima ação"),
                        ("desconectar", "apaga a conexão salva neste computador")):
        s = sub.add_parser(nome, help=ajuda)
        s.add_argument("--simulado", action="store_true", help="a conexão do modo simulado")
    sub.add_parser("gerar-chave", help="gera uma chave Fernet para WHATSAPP_CHAVE_CIFRA")
    a = ap.parse_args(argv)
    try:
        if a.acao == "gerar-chave":
            print("Coloque no .env:\nWHATSAPP_CHAVE_CIFRA=" + arq.gerar_chave())
            return 0
        if a.acao == "status":
            c = arq.carregar(a.simulado)
            print(resumo(c))
            if c.token_expira_em and _agora_fuso() >= datetime.fromisoformat(c.token_expira_em):
                print("Atenção: o token expirou; rode `whatsapp conectar` para fazer o login de novo.")
            for linha in c.historico[-8:]:
                print(f"  {linha}")
            return 0
        if a.acao == "desconectar":
            print("Conexão apagada." if arq.apagar(a.simulado) else "Não havia conexão salva.")
            return 0
        if a.acao == "reenviar-codigo":
            ob = Onboarding(provedor(a.simulado), simulado=a.simulado)
            ob.pedir_codigo(a.metodo)
            print("Novo código enviado.")
            return 0
        return conectar(a.simulado, a.metodo)
    except (ErroMeta, EtapaInvalida, ValueError, ConexaoCorrompida) as e:
        print(f"Erro: {e}")
        return 2
