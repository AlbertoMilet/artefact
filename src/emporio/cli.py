"""CLI do agente (SPEC-001 Fase 4).

    python -m emporio chat                 conversa interativa
    python -m emporio chat --debug         mostra tools chamadas, argumentos e resultado (mascarados)
    python -m emporio chat --fake          modo demonstração, sem chave nem modelo de linguagem
    python -m emporio chat -m "oi" -m "qual o endereço?"   mensagens em sequência, sem interação
    python -m emporio configurar           escolhe o modelo (deepseek, haiku, gpt-sol), raciocínio, retenção...
    python -m emporio vendedor             vigia de alertas para o vendedor, em outro terminal (SPEC-003)
    python -m emporio whatsapp conectar    conecta o WhatsApp da loja: login com Facebook e SMS (SPEC-004)
    python -m emporio origem links         links do WhatsApp com o emoji de cada canal; `origem relatorio` (SPEC-005)

Comandos durante a conversa: /novo (recomeça), /modelo [opção] (lista ou troca o modelo), /config, /som,
/sair (ou Ctrl+D / Ctrl+Z+Enter no Windows).
Com --retencao (SPEC-002): /esperar 30m | 4h | 1d simula o silêncio do cliente e mostra os lembretes;
/janela mostra a situação da janela de 24 h.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from emporio.agent import Agente, Conversa, RespostaTurno
from emporio import cli_config
from emporio.config import RAIZ, Config, montar_agente
from emporio.data import DadosIndisponiveis
from emporio.llm import LLMIndisponivel
from emporio.retencao import janela as janela_24h
from emporio.rules import origem as origem_lead
from emporio.rules.horario import FUSO

from emporio.agent.prompt import AVISO_PRIVACIDADE
from emporio.visual import Estilo, largura_terminal, recuar

estilo = Estilo()


def _cor(texto: str, papel: str = "suave") -> str:
    return estilo(texto, papel)


def _fala_da_lia(texto: str, rotulo: str = "", saida=None) -> str:
    """Prefixo da Lia, continuação alinhada e o aviso de privacidade em tom suave."""
    aviso = ""
    if texto.endswith(AVISO_PRIVACIDADE):
        texto, aviso = texto[: -len(AVISO_PRIVACIDADE)].rstrip(), AVISO_PRIVACIDADE
    largura = largura_terminal(saida)
    corpo = recuar(texto, largura)
    if aviso:
        recuo = " " * (len(rotulo) + 8)
        corpo += "\n" + recuo + estilo(recuar(aviso, largura).replace("\n", "\n" + recuo), "suave", italico=True)
    return f"{estilo.lia(rotulo)} {corpo}"


def configurar_log(pasta: Path) -> None:
    """Log JSON por turno (já mascarado pelo agente) em arquivo; nada de log no terminal."""
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in ("emporio.turno", ""):
        lg = logging.getLogger(nome)
        for antigo in [x for x in lg.handlers if getattr(x, "_emporio", False)]:
            lg.removeHandler(antigo)
            antigo.close()
    h = logging.FileHandler(pasta / "emporio.jsonl", encoding="utf-8")
    h.setFormatter(logging.Formatter("%(message)s"))
    h._emporio = True
    turno = logging.getLogger("emporio.turno")
    turno.setLevel(logging.INFO)
    turno.addHandler(h)
    turno.propagate = False
    avisos = logging.FileHandler(pasta / "avisos.log", encoding="utf-8")
    avisos.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    avisos._emporio = True
    raiz = logging.getLogger()
    raiz.setLevel(logging.WARNING)
    raiz.addHandler(avisos)


def mostrar(resp: RespostaTurno, debug: bool, saida=None) -> None:
    saida = saida or sys.stdout
    if debug:
        if resp.origem:
            o = origem_lead.POR_CHAVE[resp.origem]
            print(estilo.rastro("origem", f"{o.marcador} {o.nome} · marcador removido antes do modelo"), file=saida)
        for e in resp.rastro:
            status = None if not e.erro else f"erro: {e.erro}"
            print(estilo.rastro("tool", f"{e.tool}({e.argumentos}) · {e.duracao_ms} ms" + ("" if e.erro else " · ok"),
                                erro=status), file=saida)
            print(estilo.rastro("", e.resultado), file=saida)
        turno = f"{resp.latencia_s:.1f} s · {resp.tokens_entrada}+{resp.tokens_saida} tokens · US$ {resp.custo_usd:.5f}"
        print(estilo.rastro("turno", turno, erro=f"resposta segura: {resp.motivo_segura}" if resp.segura else None),
              file=saida)
    print(f"{_fala_da_lia(resp.texto, saida=saida)}\n", file=saida)


DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _quando(dt) -> str:
    local = dt.astimezone(FUSO)
    return f"{DIAS[local.weekday()]} {local:%d/%m %H:%M}"


def duracao(texto: str) -> timedelta | None:
    m = re.fullmatch(r"\s*(\d+)\s*(m|min|h|d)?\s*", texto.lower())
    if not m:
        return None
    n, unidade = int(m.group(1)), m.group(2) or "m"
    return {"m": timedelta(minutes=n), "min": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[unidade]


def esperar(agente: Agente, conversa: Conversa, arg: str, debug: bool) -> None:
    """Avança o relógio simulado e roda as avaliações de inatividade que vencerem no caminho."""
    delta = duracao(arg)
    if delta is None:
        print(_cor("Uso: /esperar 30m | 4h | 1d\n"))
        return
    relogio, ret = agente.toolbox.relogio, agente.retencao
    if not hasattr(relogio, "ir_para"):
        print(_cor("(relógio não ajustável nesta configuração)\n"))
        return
    destino = relogio() + delta
    if ret is None or not ret.cfg.ativa:
        relogio.ir_para(destino)
        print(_cor(f"(+{arg}: agora {_quando(destino)}; retenção desligada, use --retencao)\n"))
        return
    ac = conversa.acompanhamento
    for _ in range(30):
        if ac.proxima_avaliacao is None or ac.proxima_avaliacao > destino:
            break
        relogio.ir_para(max(ac.proxima_avaliacao, relogio()))
        av = ret.avaliar(ac, conversa.historico, relogio())
        if av is None:
            break
        if debug or av.acao != "ENVIAR":
            print(estilo.rastro("retenção", f"{_quando(av.quando)} · {av.acao}: {av.motivo} -> {av.status}"))
        if av.mensagem:
            print(f"{_fala_da_lia(av.mensagem, f' (lembrete, {_quando(av.quando)})')}\n")
    relogio.ir_para(destino)
    print(_cor(f"(agora {_quando(destino)}; {janela_24h.rotulo(ac.ultima_msg_cliente, destino)})\n"))


def mostrar_janela(agente: Agente, conversa: Conversa) -> None:
    ac, agora = conversa.acompanhamento, agente.toolbox.relogio()
    proxima = _quando(ac.proxima_avaliacao) if ac.proxima_avaliacao else "nenhuma"
    limite = ""
    if agente.retencao is not None and ac.ultima_msg_cliente is not None:
        from emporio.retencao.politica import limite_envio
        limite = f" (lembretes só até {_quando(limite_envio(ac, agente.retencao.cfg))})"
    print(_cor(f"{janela_24h.rotulo(ac.ultima_msg_cliente, agora)}{limite} | acompanhamento: {ac.status.value}"
               f"{' (' + ac.motivo + ')' if ac.motivo else ''} | lembretes neste silêncio: {len(ac.lembretes)} | "
               f"próxima avaliação: {proxima}\n"))


def comando(agente: Agente, conversa: Conversa, texto: str, debug: bool, config: Config | None) -> bool:
    """Comandos do chat que não vão para o modelo. True se o texto era um comando."""
    t = texto.strip()
    baixo = t.lower()
    if baixo.startswith("/esperar"):
        esperar(agente, conversa, t[len("/esperar"):], debug)
    elif baixo == "/janela":
        mostrar_janela(agente, conversa)
    elif baixo.startswith("/modelo"):
        print(_cor(cli_config.comando_modelo(agente, config or Config(), t[len("/modelo"):]) + "\n"))
    elif baixo == "/som":
        central = agente.alertas
        if central is None:
            print(_cor("(alertas desligados nesta configuração)\n"))
        else:
            central.tocador.ligado = not central.tocador.ligado
            estado = "ligado" if central.tocador.ligado else "desligado (o aviso visual continua)"
            print(_cor(f"Som dos alertas neste chat: {estado}. O vigia (python -m emporio vendedor) tem o "
                       f"próprio controle (--sem-som).\n"))
    elif baixo == "/config":
        print(_cor(cli_config.comando_config(agente, config or Config()) + "\n"))
    else:
        return False
    return True


def conversar(agente: Agente, mensagens: list[str] | None, debug: bool, config: Config | None = None) -> int:
    conversa: Conversa = agente.nova_conversa()
    if mensagens:
        for m in mensagens:
            if comando(agente, conversa, m, debug, config):
                continue
            print(f"{estilo.cliente()} {m}")
            mostrar(agente.responder(conversa, m), debug)
        return 0
    print(estilo.banner(agente.llm.modelo))
    while True:
        try:
            texto = input(f"{estilo.cliente()} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not texto:
            continue
        if texto.lower() in ("/sair", "sair", "/exit", "/quit"):
            return 0
        if comando(agente, conversa, texto, debug, config):
            continue
        if texto.lower() == "/novo":
            conversa = agente.nova_conversa()
            print(_cor("(nova conversa)\n"))
            continue
        mostrar(agente.responder(conversa, texto), debug)


def aviso_vendedor(alerta) -> None:
    """Aviso visual no terminal do chat (SPEC-003 RA-04): sai sempre, com ou sem som."""
    extra = f" | conversa {alerta.conversa}" if alerta.tipo == "encaminhamento" else ""
    print(estilo.alerta(f"{alerta.aviso()}{extra}"))


def vendedor(argv: list[str]) -> int:
    """Vigia de alertas para o vendedor: observa a fila e toca o som (SPEC-003)."""
    from emporio.alertas import Tocador
    from emporio.alertas.central import caminho_fila, vigiar
    ap = argparse.ArgumentParser(prog="emporio vendedor", description="Vigia de alertas para o vendedor")
    ap.add_argument("--sem-som", action="store_true", help="só o aviso visual")
    ap.add_argument("--intervalo", type=float, default=2.0, help="segundos entre leituras da fila (padrão 2)")
    ap.add_argument("--testar", action="store_true", help="toca os dois padrões e sai")
    a = ap.parse_args(argv)
    config = Config.do_ambiente()
    tocador = Tocador(ligado=config.alerta_sonoro and not a.sem_som)
    if a.testar:
        for tipo, nome in (("normal", "encaminhamento (duas notas)"), ("vendedor", "pedido de vendedor (tríade x2)")):
            print(f"Tocando: {nome}" + ("" if tocador.ligado else " (som desligado)"))
            tocador.tocar_e_esperar(tipo)
        return 0
    tty = sys.stdout.isatty()

    def mostrar(linha: str) -> None:
        if linha.startswith(chr(27) + "]0;"):
            if tty:
                sys.stdout.write(linha)
                sys.stdout.flush()
            return
        print(_cor(linha, "alerta") if "]" in linha[:8] else linha, flush=True)

    try:
        vigiar(caminho_fila(), tocador, mostrar, a.intervalo)
    except KeyboardInterrupt:
        print()
    return 0


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["configurar"]:
        return cli_config.configurar(argv[1:])
    if argv[:1] == ["vendedor"]:
        return vendedor(argv[1:])
    if argv[:1] == ["whatsapp"]:
        from emporio import cli_whatsapp
        return cli_whatsapp.main(argv[1:])
    if argv[:1] == ["origem"]:
        from emporio import cli_origem
        return cli_origem.main(argv[1:])
    ap = argparse.ArgumentParser(prog="emporio", description="Agente de atendimento da Empório da Música")
    sub = ap.add_subparsers(dest="comando", required=True)
    sub.add_parser("configurar", help="configura o agente: modelo (deepseek, haiku, gpt-sol), raciocínio, retenção")
    sub.add_parser("vendedor", help="vigia de alertas para o vendedor (outro terminal)")
    sub.add_parser("whatsapp", help="conecta o WhatsApp da loja: login com Facebook e código por SMS (SPEC-004)")
    sub.add_parser("origem", help="links por canal e relatório de origem dos leads (SPEC-005)")
    chat = sub.add_parser("chat", help="conversar com o agente")
    chat.add_argument("--debug", action="store_true", help="mostra o rastro de tools e fontes")
    chat.add_argument("--fake", action="store_true", help="modo demonstração sem modelo (LLM_PROVIDER=fake)")
    chat.add_argument("--modelo", help="deepseek, haiku, gpt-sol ou slug do OpenRouter (só nesta execução)")
    chat.add_argument("-m", "--mensagem", action="append", help="mensagem não interativa (pode repetir; aceita /esperar e /janela)")
    chat.add_argument("--retencao", action="store_true", help="liga a retenção por inatividade (SPEC-002)")
    chat.add_argument("--sem-som", action="store_true", help="alertas para o vendedor só com aviso visual (SPEC-003)")
    chat.add_argument("--som-no-chat", action="store_true",
                      help="toca o alerta também no chat (padrão: só o vigia toca, para não soar em dobro)")
    a = ap.parse_args(argv)

    configurar_log(RAIZ / "logs")
    config = Config.do_ambiente()
    if a.fake:
        config = replace(config, llm_provider="fake")
    if a.modelo:
        try:
            config = replace(config, openrouter_model=cli_config.escolher_modelo(a.modelo))
        except ValueError as e:
            print(f"Erro: {e}", file=sys.stderr)
            return 2
    if a.retencao:
        config = replace(config, retencao=replace(config.retencao, ativa=True))
    if a.sem_som:
        config = replace(config, alerta_sonoro=False)
    if a.som_no_chat:
        config = replace(config, som_no_chat=True)
    try:
        agente = montar_agente(config)
    except DadosIndisponiveis as e:
        print(f"Não foi possível carregar os dados da loja: {e}", file=sys.stderr)
        return 2
    except LLMIndisponivel as e:
        print(f"LLM indisponível: {e}\nConfigure OPENROUTER_API_KEY no .env (veja .env.example) "
              "ou rode em modo demonstração: python -m emporio chat --fake", file=sys.stderr)
        return 2
    if agente.alertas is not None:
        agente.alertas.avisar = aviso_vendedor
    if a.debug:
        print(_cor(f"[modelo: {agente.llm.modelo} | ZDR obrigatório | dados: {config.data_dir}]"))
    return conversar(agente, a.mensagem, a.debug, config)


if __name__ == "__main__":
    sys.exit(main())
