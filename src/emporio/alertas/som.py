"""Som sintetizado, sem arquivo de áudio (SPEC-003 RA-02, RA-07).

Mesmos padrões do painel do Saúde Legal: [frequência Hz, início em s]. "normal" são duas notas curtas;
"vendedor" é uma tríade ascendente tocada duas vezes, mais longa e distinta, para o vendedor reconhecer
sem olhar a tela que há um cliente querendo falar agora.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Callable

PADROES: dict[str, list[tuple[float, float]]] = {
    "normal": [(880.0, 0.0), (1174.7, 0.16)],
    "vendedor": [(784.0, 0.0), (1046.5, 0.15), (1318.5, 0.30), (784.0, 0.52), (1046.5, 0.67), (1318.5, 0.82)],
}
DURACAO_NOTA_MS = 140


def _tocar_padrao(padrao: list[tuple[float, float]]) -> None:
    try:
        import winsound  # só existe no Windows
    except ImportError:
        winsound = None
    inicio = time.perf_counter()
    for hz, atraso in padrao:
        espera = atraso - (time.perf_counter() - inicio)
        if espera > 0:
            time.sleep(espera)
        if winsound is not None:
            winsound.Beep(int(hz), DURACAO_NOTA_MS)
        else:                                   # terminal: campainha (uma por nota)
            sys.stderr.write("\a")
            sys.stderr.flush()


class Tocador:
    """Toca um padrão em segundo plano (não bloqueia a conversa). `ligado=False` silencia."""

    def __init__(self, ligado: bool = True, executar: Callable[[list[tuple[float, float]]], None] | None = None):
        self.ligado = ligado
        self._executar = executar or _tocar_padrao

    def tocar(self, tipo: str) -> bool:
        if not self.ligado:
            return False
        padrao = PADROES.get(tipo, PADROES["normal"])
        threading.Thread(target=self._executar_seguro, args=(padrao,), daemon=True).start()
        return True

    def tocar_e_esperar(self, tipo: str) -> bool:
        """True só se o som de fato tocou (sem dispositivo, devolve False e o vigia avisa)."""
        if not self.ligado:
            return False
        return self._executar_seguro(PADROES.get(tipo, PADROES["normal"]))

    def _executar_seguro(self, padrao) -> bool:
        try:
            self._executar(padrao)
            return True
        except Exception:      # sem dispositivo de som: o aviso visual já cobre (RA-04)
            return False
