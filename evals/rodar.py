"""Roda os evals com o modelo real e gera docs/avaliacao.md (SPEC-001 Fase 5).

Uso:  uv run python -m evals.rodar [--modelo deepseek/deepseek-v4.1-flash] [--filtro preco] [--repeticoes 1]
Precisa de OPENROUTER_API_KEY. Toda chamada com ZDR (RN-23).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from emporio.config import MODELO_PADRAO, RAIZ, Config
from emporio.modelos import resolver
from evals.casos import CASOS, Caso
from emporio.rules.verificacao import mascarar_texto
from evals.nucleo import Resultado, rodar_caso


def rodar(config: Config, casos: list[Caso], repeticoes: int = 1, paralelo: int = 4) -> list[Resultado]:
    tarefas = [c for c in casos for _ in range(repeticoes)]
    with ThreadPoolExecutor(max_workers=paralelo) as ex:
        return list(ex.map(lambda c: rodar_caso(config, c), tarefas))


def relatorio(resultados: list[Resultado], modelo: str, duracao_s: float) -> str:
    por_cat: dict[str, list[Resultado]] = defaultdict(list)
    for r in resultados:
        por_cat[r.caso.categoria].append(r)
    total = len(resultados)
    ok = sum(r.passou for r in resultados)
    criticas = sum(bool(r.criticas) for r in resultados)
    custo = sum(r.custo_usd for r in resultados)
    lat = sum(r.latencia_s for r in resultados) / max(total, 1)
    tokens = sum(r.tokens for r in resultados) // max(total, 1)
    vazias = sum(r.vazias for r in resultados)
    linhas = [
        "# Avaliação do agente (Fase 5, SPEC-001)", "",
        f"Gerado por `uv run python -m evals.rodar` em {time.strftime('%Y-%m-%d %H:%M')}. "
        f"Modelo **`{modelo}`** via OpenRouter com Zero Data Retention. Relógio dos casos: quarta-feira, "
        "25/03/2026 10:00 (dentro do período dos pedidos), salvo indicação no caso.", "",
        f"**Resultado: {ok}/{total} casos aprovados ({ok / max(total, 1):.0%}); "
        f"{criticas} com falha crítica.** Latência média por conversa {lat:.1f} s; {tokens} tokens por conversa; "
        f"{vazias} respostas vazias do modelo (tratadas com nova tentativa); custo total US$ {custo:.4f}; "
        f"duração {duracao_s:.0f} s.", "",
        "Falha crítica: valor em R$ que não veio de nenhuma tool nem do cliente, telefone ou e-mail de cliente na "
        "resposta, promessa de ação que o agente não executa (reservar, cancelar) ou negar uma categoria que a loja "
        "vende. Os demais critérios de cada caso estão em `evals/casos.py`.", "",
        "| Categoria | Aprovados | Falha crítica |", "|---|---|---|",
    ]
    for cat, rs in por_cat.items():
        linhas.append(f"| {cat} | {sum(r.passou for r in rs)}/{len(rs)} | {sum(bool(r.criticas) for r in rs)} |")
    linhas += ["", "## Casos", "", "| Caso | Critério | Resultado | Tools | Detalhe |", "|---|---|---|---|---|"]
    for r in resultados:
        detalhe = "; ".join(r.criticas + r.falhas + ([r.erro] if r.erro else [])) or "—"
        linhas.append(f"| `{r.caso.id}` | {r.caso.criterio or '—'} | {'ok' if r.passou else '**falhou**'} | "
                      f"{', '.join(dict.fromkeys(r.tools)) or '—'} | {detalhe.replace('|', '/')} |")
    falhos = [r for r in resultados if not r.passou]
    if falhos:
        linhas += ["", "## Conversas que falharam", ""]
        for r in falhos:
            linhas += [f"### `{r.caso.id}`", ""]
            for turno, resp in zip(r.caso.turnos, r.respostas):     # respostas já mascaradas
                linhas += [f"**Cliente:** {mascarar_texto(turno)}", "",
                           "**Lia:** " + mascarar_texto(resp).replace("\n", "\n> "), ""]
    return "\n".join(linhas) + "\n"


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default=MODELO_PADRAO)
    ap.add_argument("--filtro", help="parte do id ou da categoria")
    ap.add_argument("--repeticoes", type=int, default=1)
    ap.add_argument("--saida", type=Path, default=RAIZ / "docs" / "avaliacao.md")
    ap.add_argument("--raciocinio", choices=["ligado", "desligado"], help="sobrescreve LLM_RACIOCINIO")
    a = ap.parse_args()
    config = replace(Config.do_ambiente(usar_preferencias=False), llm_provider="openrouter",
                     openrouter_model=resolver(a.modelo))
    if a.raciocinio:
        config = replace(config, raciocinio=a.raciocinio == "ligado")
    if not config.openrouter_api_key:
        print("Defina OPENROUTER_API_KEY no .env.")
        return 2
    casos = [c for c in CASOS if not a.filtro or a.filtro in c.id or a.filtro == c.categoria]
    t0 = time.perf_counter()
    resultados = rodar(config, casos, a.repeticoes)
    for r in resultados:
        marca = "ok " if r.passou else ("CRÍTICA" if r.criticas else "falhou")
        print(f"{marca:8} {r.caso.id:28} {r.latencia_s:5.1f}s  {'; '.join(r.criticas + r.falhas)[:110]}")
    a.saida.write_text(relatorio(resultados, a.modelo, time.perf_counter() - t0), encoding="utf-8")
    ok = sum(r.passou for r in resultados)
    print(f"\n{ok}/{len(resultados)} aprovados; {sum(bool(r.criticas) for r in resultados)} com falha crítica -> {a.saida}")
    return 0 if ok == len(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
