"""Sobe a interface web do atendimento (SPEC-006).

    python -m emporio                  abre a interface em http://127.0.0.1:8000
    python -m emporio ui --fake        modo demonstração, sem chave nem modelo de linguagem
    python -m emporio ui --porta 8080 --sem-navegador
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from dataclasses import replace

from emporio.config import Config, montar_agente
from emporio.data import DadosIndisponiveis
from emporio.llm import LLMIndisponivel


LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="emporio ui", description="Interface web do atendimento (SPEC-006)")
    ap.add_argument("--fake", action="store_true", help="modo demonstração sem modelo (LLM_PROVIDER=fake)")
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1", help="padrão: só este computador")
    ap.add_argument("--sem-navegador", action="store_true", help="não abre o navegador")
    ap.add_argument("--https-proxy", action="store_true",
                    help="há um proxy com HTTPS na frente: obrigatório fora deste computador (SPEC-013)")
    a = ap.parse_args(argv)
    loopback = a.host in LOOPBACK
    if not loopback and not a.https_proxy:
        print(f"Erro: --host {a.host} expõe o painel na rede em HTTP puro (senha e cookie em claro). "
              "Use um proxy com HTTPS na frente e passe --https-proxy, ou fique em 127.0.0.1.", file=sys.stderr)
        return 2
    config = Config.do_ambiente()
    if a.fake:
        config = replace(config, llm_provider="fake")
    try:
        agente = montar_agente(config)
    except DadosIndisponiveis as e:
        print(f"Não foi possível carregar os dados da loja: {e}", file=sys.stderr)
        return 2
    except LLMIndisponivel as e:
        print(f"LLM indisponível: {e}\nConfigure OPENROUTER_API_KEY no .env (veja .env.example) "
              "ou rode em modo demonstração: python -m emporio ui --fake", file=sys.stderr)
        return 2
    import uvicorn

    from emporio.web import criar_app
    from emporio.web.auth import carregar_usuarios, segredo_da_sessao
    try:
        usuarios = carregar_usuarios()
        _, segredo_fixo = segredo_da_sessao()
    except ValueError as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 2
    if not usuarios and not loopback:
        print("Erro: o login de demonstração (senha na tela) só vale neste computador. "
              "Crie um usuário com `python -m emporio usuario criar seu_nome`.", file=sys.stderr)
        return 2
    if not usuarios:
        print("Sem usuários em EMPORIO_USUARIOS: " + ("entre com demo / demo1234 (só no modo demonstração)."
              if a.fake else "crie um com `python -m emporio usuario criar seu_nome`."))
    if not segredo_fixo:
        print("Sem EMPORIO_SEGREDO_SESSAO: as sessões caem quando o servidor reinicia "
              "(`python -m emporio usuario segredo`).")
    url = f"http://{a.host}:{a.porta}"
    print(f"Empório da Música: atendimento em {url} (modelo {agente.llm.modelo}, ZDR obrigatório). Ctrl+C encerra.")
    if not a.sem_navegador:
        threading.Timer(1.2, webbrowser.open, args=(url,)).start()
    uvicorn.run(criar_app(agente, config, cookies_seguros=a.https_proxy), host=a.host, port=a.porta,
                log_level="warning", proxy_headers=a.https_proxy,
                # de quem aceitar X-Forwarded-*: o proxy HTTPS (num contêiner, o Traefik do Easypanel)
                forwarded_allow_ips=os.getenv("EMPORIO_PROXY_IPS", "127.0.0.1"))
    return 0
