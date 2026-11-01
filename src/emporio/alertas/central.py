"""Central de alertas: decide o que alertar, grava na fila do vendedor e toca o som (SPEC-003).

A fila (`logs/alertas.jsonl`, uma linha JSON por alerta, mascarada) é o equivalente à fila de
encaminhamentos do Saúde Legal: o chat escreve; o vigia (`python -m emporio vendedor`) lê.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from emporio.alertas.deteccao import pediu_vendedor
from emporio.alertas.som import Tocador
from emporio.rules.verificacao import mascarar_texto

JANELA_REPETICAO = timedelta(minutes=10)          # RA-03
ROTULOS = {"reclamacao": "reclamação", "devolucao": "devolução", "troca": "troca",
           "atendimento_humano": "atendimento humano", "outro": "solicitação"}


@dataclass(frozen=True)
class Alerta:
    tipo: str                 # "pedido_vendedor" ou "encaminhamento"
    motivo: str
    conversa: str
    quando: str               # ISO 8601
    protocolo: str | None = None
    trecho: str = ""          # mensagem do cliente, mascarada e curta
    tocar: bool = True        # False: vai para a fila sem tocar de novo (RA-03)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def padrao(self) -> str:
        return "vendedor" if self.tipo == "pedido_vendedor" else "normal"

    def aviso(self) -> str:
        if self.tipo == "pedido_vendedor":
            return "🙋 Cliente pediu um vendedor: quer falar agora."
        return f"📋 Nova solicitação encaminhada à equipe: {self.motivo}" + (f" ({self.protocolo})" if self.protocolo else "") + "."


def caminho_fila() -> Path:
    padrao = Path(__file__).resolve().parents[3] / "logs" / "alertas.jsonl"
    return Path(os.getenv("ALERTAS_FILA", str(padrao)))


class CentralAlertas:
    def __init__(self, tocador: Tocador | None = None, fila: Path | None = None,
                 avisar: Callable[[Alerta], None] | None = None):
        self.tocador = tocador or Tocador()
        self.fila = Path(fila) if fila else caminho_fila()
        self.avisar = avisar                         # aviso visual no terminal do chat (RA-04)
        self._ultimo_pedido: dict[str, datetime] = {}
        self._trava = threading.Lock()

    def avaliar_turno(self, conversa: str, texto_cliente: str, rastro: list, agora: datetime) -> list[Alerta]:
        """Eventos do turno: pedido explícito na mensagem e solicitações gravadas pela tool."""
        alertas: list[Alerta] = []
        trecho = mascarar_texto(" ".join(texto_cliente.split()))[:160]
        recente = self._ultimo_pedido.get(conversa)
        pedido_recente = recente is not None and agora - recente < JANELA_REPETICAO
        if pediu_vendedor(texto_cliente):
            if not pedido_recente:
                alertas.append(Alerta("pedido_vendedor", "cliente pediu atendimento humano", conversa,
                                      agora.isoformat(), trecho=trecho))
                # A janela conta do último ALERTA: quem insiste a cada 5 min volta a alertar após 10 min
                self._ultimo_pedido[conversa] = agora
            pedido_recente = True
        for evento in rastro:
            if evento.tool != "registrar_solicitacao" or evento.erro:
                continue
            try:
                resultado = json.loads(evento.completo or "{}")
                args = json.loads(evento.argumentos or "{}")
            except json.JSONDecodeError:
                continue
            if not resultado.get("gravado"):
                continue
            tipo = args.get("tipo", "outro")
            alertas.append(Alerta("encaminhamento", ROTULOS.get(tipo, tipo), conversa, agora.isoformat(),
                                  protocolo=resultado.get("protocolo_simulado"), trecho=trecho,
                                  tocar=not (tipo == "atendimento_humano" and pedido_recente)))
        return alertas

    def emitir(self, alertas: list[Alerta]) -> None:
        if not alertas:
            return
        with self._trava:
            self.fila.parent.mkdir(parents=True, exist_ok=True)
            with self.fila.open("a", encoding="utf-8") as f:
                for a in alertas:
                    f.write(json.dumps(asdict(a), ensure_ascii=False) + "\n")
        sonoros = [a for a in alertas if a.tocar]
        if sonoros:
            # RA-02: com os dois no mesmo turno, vale o padrão do pedido explícito
            self.tocador.tocar("vendedor" if any(a.padrao == "vendedor" for a in sonoros) else "normal")
        if self.avisar:
            for a in alertas:
                self.avisar(a)


# ---------------------------------------------------------------- vigia do vendedor

def ler_fila(fila: Path) -> list[dict]:
    if not fila.is_file():
        return []
    linhas = []
    for linha in fila.read_text(encoding="utf-8").splitlines():
        try:
            linhas.append(json.loads(linha))
        except json.JSONDecodeError:
            continue
    return linhas


def vigiar(fila: Path, tocador: Tocador, mostrar: Callable[[str], None], intervalo_s: float = 2.0,
           ciclos: int | None = None, dormir: Callable[[float], None] = time.sleep) -> int:
    """Observa a fila e avisa os alertas novos (RA-06). Devolve quantos alertas novos foram avisados."""
    vistos = {a.get("id") for a in ler_fila(fila)}           # primeira passada só registra
    mostrar(f"Vigiando {fila} ({len(vistos)} alerta(s) já existente(s) ignorado(s)). Ctrl+C para sair.")
    avisados = 0
    n = 0
    while ciclos is None or n < ciclos:
        n += 1
        dormir(intervalo_s)
        novos = [a for a in ler_fila(fila) if a.get("id") not in vistos]
        if not novos:
            continue
        vistos.update(a.get("id") for a in novos)
        sonoros = [a for a in novos if a.get("tocar", True)]
        pedido = any(a.get("tipo") == "pedido_vendedor" for a in sonoros)
        tocou = tocador.tocar_e_esperar("vendedor" if pedido else "normal") if sonoros else False
        for a in novos:
            hora = a.get("quando", "")[11:16]
            alerta = Alerta(**{k: a[k] for k in ("tipo", "motivo", "conversa", "quando") if k in a},
                            protocolo=a.get("protocolo"))
            linha = f"[{hora}] {alerta.aviso()} conversa {a.get('conversa')}"
            if a.get("trecho"):
                linha += f' | "{a["trecho"]}"'
            mostrar(linha)
        if sonoros and not tocou:
            mostrar("(som desligado: só o aviso visual)")
        mostrar(f"\033]0;({len(novos)}) Empório: alerta para o vendedor\a")   # título do terminal
        avisados += len(novos)
    return avisados
