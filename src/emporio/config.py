"""Configuração por variáveis de ambiente (.env) e montagem do agente (SPEC-001 §5)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from emporio.agent import Agente
from emporio.data import carregar
from emporio.llm import FakeLLMClient, LLMClient, OpenRouterClient
from emporio.policies import carregar_manual
from emporio.rules.horario import FUSO, relogio_fixo, relogio_real
from emporio.tools import Toolbox

RAIZ = Path(__file__).resolve().parents[2]
MODELO_PADRAO = "deepseek/deepseek-v4.1-flash"     # D-10


@dataclass(frozen=True)
class Config:
    llm_provider: str = "openrouter"
    openrouter_api_key: str = ""
    openrouter_model: str = MODELO_PADRAO
    data_dir: Path = RAIZ / "data"
    data_referencia: datetime | None = None
    max_tool_calls: int = 5
    turn_timeout_s: float = 30
    history_window: int = 10
    tickets_path: Path = RAIZ / "tickets.jsonl"

    @classmethod
    def do_ambiente(cls, env_file: Path | None = RAIZ / ".env") -> "Config":
        if env_file:
            load_dotenv(env_file)
        ref = os.getenv("DATA_REFERENCIA")
        dt = None
        if ref:
            dt = datetime.fromisoformat(ref)
            dt = dt if dt.tzinfo else dt.replace(tzinfo=FUSO)
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "openrouter").strip().lower(),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
            openrouter_model=os.getenv("OPENROUTER_MODEL", MODELO_PADRAO).strip(),
            data_dir=Path(os.getenv("EMPORIO_DATA_DIR", str(RAIZ / "data"))),
            data_referencia=dt,
            max_tool_calls=int(os.getenv("MAX_TOOL_CALLS", "5")),
            turn_timeout_s=float(os.getenv("TURN_TIMEOUT_S", "30")),
            history_window=int(os.getenv("HISTORY_WINDOW", "10")),
            tickets_path=Path(os.getenv("TICKETS_PATH", str(RAIZ / "tickets.jsonl"))),
        )


def montar_llm(config: Config) -> LLMClient:
    if config.llm_provider == "fake":
        from emporio.llm.demo import DemoLLMClient
        return DemoLLMClient()
    if config.llm_provider == "openrouter":
        return OpenRouterClient(config.openrouter_api_key, config.openrouter_model, timeout=config.turn_timeout_s)
    raise ValueError(f"LLM_PROVIDER desconhecido: {config.llm_provider!r} (use openrouter ou fake)")


def montar_agente(config: Config | None = None, llm: LLMClient | None = None) -> Agente:
    config = config or Config.do_ambiente()
    relogio = relogio_fixo(config.data_referencia) if config.data_referencia else relogio_real
    toolbox = Toolbox(carregar(config.data_dir), carregar_manual(), relogio, tickets_path=config.tickets_path)
    return Agente(llm or montar_llm(config), toolbox, config.max_tool_calls, config.turn_timeout_s,
                  config.history_window)


__all__ = ["Config", "FakeLLMClient", "montar_agente", "montar_llm"]
