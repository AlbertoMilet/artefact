"""Alerta sonoro para o vendedor (SPEC-003), inspirado no aviso de novo caso do painel do Saúde Legal."""

from emporio.alertas.central import Alerta, CentralAlertas
from emporio.alertas.deteccao import pediu_vendedor
from emporio.alertas.som import PADROES, Tocador

__all__ = ["Alerta", "CentralAlertas", "PADROES", "Tocador", "pediu_vendedor"]
