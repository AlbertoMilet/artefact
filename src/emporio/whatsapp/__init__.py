"""Conexão do WhatsApp da loja à Cloud API: login com Facebook, código por SMS e registro (SPEC-004)."""

from emporio.whatsapp.conexao import Conexao, Etapa
from emporio.whatsapp.fluxo import Onboarding
from emporio.whatsapp.meta import ErroMeta, GraphMeta
from emporio.whatsapp.simulado import ProvedorSimulado

__all__ = ["Conexao", "ErroMeta", "Etapa", "GraphMeta", "Onboarding", "ProvedorSimulado"]
