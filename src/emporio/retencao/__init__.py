"""Inatividade do cliente na janela de 24 h (SPEC-002).

Inspirado no agente de retenção do projeto Saúde Legal: a janela conta só da última mensagem do
cliente; em momentos de silêncio definidos, um agente decide ENVIAR, ESPERAR ou PARAR; bloqueios em
código valem antes do modelo e de novo antes do envio.
"""

from emporio.retencao.agente import Avaliacao, Retencao
from emporio.retencao.modelos import Acompanhamento, Status
from emporio.retencao.politica import ConfigRetencao

__all__ = ["Acompanhamento", "Avaliacao", "ConfigRetencao", "Retencao", "Status"]
