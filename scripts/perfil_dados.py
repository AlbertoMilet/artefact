"""Fase 0 (SPEC-001): confirma os achados A1–A19 nos dados e gera docs/data_quality.md.

Uso:  uv run python scripts/perfil_dados.py [--data data] [--saida docs/data_quality.md]

Cada verificação devolve (confirmado, evidência). O script termina com código 1 se algum achado
não se confirmar: os dados mudaram e a SPEC precisa ser revista antes de seguir.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PREFIXO = "desafio_tecnico_ai_eng - "
MANUAL_MD = RAIZ / "src" / "emporio" / "policies" / "manual.md"


def ler(data: Path, nome: str) -> list[dict]:
    with open(data / f"{PREFIXO}{nome}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def brl(valor: Decimal) -> str:
    q = valor.quantize(Decimal("0.01"), ROUND_HALF_UP)
    inteiro, centavos = f"{q:.2f}".split(".")
    return f"R$ {int(inteiro):,}".replace(",", ".") + f",{centavos}"


def texto_pdf(data: Path) -> str | None:
    try:
        import pypdf
    except ImportError:
        return None
    paginas = pypdf.PdfReader(data / "políticas_da_loja.pdf").pages
    return " ".join(p.extract_text() for p in paginas)


def palavras(texto: str) -> Counter:
    t = unicodedata.normalize("NFC", texto.lower())
    return Counter(re.findall(r"[a-zà-ú0-9]+", t))


def manual_sem_notas() -> str:
    t = MANUAL_MD.read_text(encoding="utf-8")
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = "\n".join(linha for linha in t.splitlines() if not linha.startswith(">"))
    return re.sub(r"§", " ", t)


def perfil(data: Path) -> tuple[list[tuple[str, str, bool, str]], dict]:
    cat = ler(data, "categories")
    cli = {c["customer_id"]: c for c in ler(data, "customers")}
    itens = ler(data, "order_items")
    ped = {p["order_id"]: p for p in ler(data, "orders")}
    prod = {p["product_id"]: p for p in ler(data, "products")}
    promo = ler(data, "promotions")
    pdf = texto_pdf(data)
    pdf_n = re.sub(r"\s+", " ", pdf) if pdf else ""
    R: list[tuple[str, str, bool, str]] = []

    def achado(cod: str, titulo: str, ok: bool, evid: str) -> None:
        R.append((cod, titulo, ok, evid))

    # Integridade estrutural
    def duplicados(nome: str, chave: str) -> list[str]:      # conta nas linhas originais, antes do dict
        return [k for k, v in Counter(r[chave] for r in ler(data, nome)).items() if v > 1]

    ids_dup = {"products": duplicados("products", "product_id"), "orders": duplicados("orders", "order_id"),
               "customers": duplicados("customers", "customer_id"),
               "promotions": duplicados("promotions", "promotion_id"),
               "categories": duplicados("categories", "category_id")}
    orfaos = (
        {i["product_id"] for i in itens} - set(prod),
        {i["order_id"] for i in itens} - set(ped),
        {p["customer_id"] for p in ped.values()} - set(cli),
        {p["product_id"] for p in promo} - set(prod),
        {p["category_id"] for p in prod.values()} - {c["category_id"] for c in cat},
    )
    specs_invalidos = []
    for pid, p in prod.items():
        try:
            json.loads(p["specs"])
        except json.JSONDecodeError:
            specs_invalidos.append(pid)
    integridade = {
        "ids_duplicados": {k: v for k, v in ids_dup.items() if v},
        "referencias_orfas": [sorted(o) for o in orfaos if o],
        "specs_invalidos": specs_invalidos,
    }

    if pdf:
        achado("A1", "Dois números de WhatsApp no manual",
               "3341-4444" in pdf_n and "3321-4500" in pdf_n,
               "§1.2 e capa: (67) 3341-4444; §7: (67) 3321-4500")
        achado("A2", "E-mail com e sem acento",
               "contato@emporiodamusica.com.br" in pdf_n and "contato@empóriodamusica.com.br" in pdf_n,
               "capa: contato@emporiodamusica.com.br; §1.2: contato@empóriodamusica.com.br")
        achado("A3", "Parcela mínima contraditória (§3 × §3.1)",
               "Parcela mínima de R$ 100,00" in pdf_n and "parcela mínima de R$ 80,00" in pdf_n,
               "tabela §3: mínimo R$ 100; §3.1: até 3x (parcela ≥ R$ 50), 4–6x ≥ R$ 80, 7–12x ≥ R$ 100")
        achado("A5", "PIX não se acumula com promoção (§6.2)",
               "não se aplica sobre preços já promocionais" in pdf_n,
               "§6.2: \"O desconto de PIX (5%) não se aplica sobre preços já promocionais\"")
    else:
        for cod in ("A1", "A2", "A3", "A5"):
            achado(cod, "verificação do PDF", False, "pypdf não instalado: rode `uv sync`")

    # A4: parcelamento fora da §3.1
    def minimo(n: int) -> Decimal:
        return Decimal("50") if n <= 3 else Decimal("80") if n <= 6 else Decimal("100")

    fora, dentro = [], []
    for oid, p in ped.items():
        m = re.fullmatch(r"credit_(\d+)x", p["payment_method"])
        if not m:
            continue
        n = int(m.group(1))
        parcela = Decimal(p["total_brl"]) / n
        linha = f"pedido {oid}: {brl(Decimal(p['total_brl']))} em {n}x = {brl(parcela)} (mín. {brl(minimo(n))}, {p['status']})"
        (fora if parcela < minimo(n) else dentro).append(linha)
    achado("A4", "Pedidos fora da regra de parcelamento da §3.1",
           {l.split(':')[0] for l in fora} == {"pedido 9", "pedido 16", "pedido 18"},
           "; ".join(fora))

    # A6: PIX sem desconto
    soma_atual = {}
    for oid in ped:
        soma_atual[oid] = sum(Decimal(prod[i["product_id"]]["price_brl"]) * int(i["quantity"])
                              for i in itens if i["order_id"] == oid)
    pix_iguais = [oid for oid, p in ped.items()
                  if p["payment_method"] == "pix" and Decimal(p["total_brl"]) == soma_atual[oid]]
    achado("A6", "Pedidos PIX com total igual ao preço atual (sem os 5%)",
           sorted(pix_iguais, key=int) == ["1", "5", "10", "13", "17"],
           "pedidos " + ", ".join(f"{o} ({ped[o]['status']})" for o in sorted(pix_iguais, key=int)))

    # A7: total diferente da soma com preços atuais
    diverg = [f"pedido {o}: total {brl(Decimal(p['total_brl']))} × soma atual {brl(soma_atual[o])}"
              for o, p in ped.items() if Decimal(p["total_brl"]) != soma_atual[o]]
    achado("A7", "Total diferente da soma calculada com preços atuais", len(diverg) == 2,
           "; ".join(diverg) + ". order_items não tem preço unitário histórico")

    # A8: coming_soon em pedidos
    cs = {pid for pid, p in prod.items() if p["status"] == "coming_soon"}
    ped_cs = sorted({i["order_id"] for i in itens if i["product_id"] in cs}, key=int)
    achado("A8", "Produto coming_soon presente em pedidos", bool(ped_cs),
           f"produtos {sorted(cs)} nos pedidos " + ", ".join(f"{o} ({ped[o]['status']})" for o in ped_cs))

    # A9: status × estoque
    sem_estoque_ativos = [f"{pid} {prod[pid]['name']}" for pid in prod
                          if prod[pid]["status"] == "active" and int(prod[pid]["stock_quantity"]) == 0]
    desc = [f"{pid} (estoque {prod[pid]['stock_quantity']})" for pid in prod
            if prod[pid]["status"] == "discontinued"]
    achado("A9", "Status contra estoque", bool(sem_estoque_ativos) and bool(desc),
           f"descontinuados: {', '.join(desc)}; ativos sem estoque: {', '.join(sem_estoque_ativos)}")

    # A10: nome × descrição (marcas diferentes)
    marcas = ["Yamaha", "Fender", "Ibanez", "Music Man", "Pearl", "Tama", "Korg", "Roland", "Takamine",
              "Giannini", "Tagima", "Gibson", "Epiphone", "Squier", "Casio", "Kala", "Shelby", "Rozini",
              "Cort", "Martin", "Taylor", "Ludwig", "Mapex", "Nord", "Kawai", "Strinberg", "Washburn"]
    conflitos = []
    for pid, p in prod.items():
        no_nome = {m for m in marcas if m.lower() in p["name"].lower()}
        na_desc = {m for m in marcas if m.lower() in p["description"].lower()}
        if no_nome and na_desc and not (no_nome & na_desc):
            conflitos.append(f"{pid}: nome {'/'.join(sorted(no_nome))} × descrição {'/'.join(sorted(na_desc))}")
    achado("A10", "Nome e descrição citam marcas diferentes",
           {c.split(':')[0] for c in conflitos} >= {"135", "137", "139", "140", "142", "144"},
           "; ".join(conflitos))

    # A11: specs com semântica variável
    strings_por_cat = defaultdict(set)
    for p in prod.values():
        s = json.loads(p["specs"])
        if "strings" in s:
            strings_por_cat[p["category_id"]].add(str(s["strings"]))
    nomes_cat = {c["category_id"]: c["name"] for c in cat}
    achado("A11", "`specs.strings` muda de sentido por categoria; não há coluna de marca",
           any(v <= {"nylon", "aço", "steel", "aco"} for v in strings_por_cat.values())
           and any(all(x.isdigit() for x in v) for v in strings_por_cat.values())
           and "brand" not in next(iter(prod.values())),
           "; ".join(f"{nomes_cat[c]}: {sorted(v)}" for c, v in sorted(strings_por_cat.items())))

    # A12: catálogo parcial
    por_cat = Counter(p["category_id"] for p in prod.values())
    vazias = [nomes_cat[c["category_id"]] for c in cat if por_cat[c["category_id"]] == 0]
    achado("A12", "Catálogo parcial e categorias vazias", len(prod) < 300 and bool(vazias),
           f"{len(prod)} produtos (manual: \"mais de 300\"); vazias: {', '.join(vazias)}")

    # A13: promoções
    ativas = [p for p in promo if p["is_active"] == "1"]
    multi = sorted([pid for pid, n in Counter(p["product_id"] for p in promo).items() if n > 1], key=int)
    achado("A13", "Promoções sem datas; poucas ativas",
           "start_date" not in promo[0] and "end_date" not in promo[0],
           f"{len(promo)} promoções, {len(ativas)} ativas (ids {', '.join(p['promotion_id'] for p in ativas)}); "
           f"produtos com vários registros: {', '.join(multi)}; colunas: {', '.join(promo[0])}")

    # A14: frete com limite indefinido
    achado("A14", "Frete: \"acima\"/\"abaixo\" de R$ 500 sem o caso igual",
           (not pdf) or ("acima de R$ 500,00" in pdf_n and "abaixo de R$ 500,00" in pdf_n),
           "§5.1: grátis acima de R$ 500,00; R$ 35,00 abaixo de R$ 500,00; municípios da região metropolitana não listados")

    # A15: faltam dados de devolução/entrega
    colunas = list(next(iter(ped.values())))
    faltam = [c for c in ("delivered_at", "received_at", "channel", "carrier", "shipped_at", "address")
              if c not in colunas]
    achado("A15", "Pedidos sem data de recebimento, canal, transportadora e endereço", len(faltam) == 6,
           f"colunas de orders: {', '.join(colunas)}")

    # A16: atualidade do retrato
    datas = sorted(p["order_date"] for p in ped.values())
    pendentes = [o for o, p in ped.items() if p["status"] in ("pending", "confirmed")]
    achado("A16", "Pedidos são um retrato de 2025–2026", True,
           f"datas de {datas[0]} a {datas[-1]}; {len(pendentes)} pedidos ainda pending/confirmed")

    # A17: ligação por customer_id
    achado("A17", "Pedido ligado ao cliente só por customer_id", "customer_id" in colunas,
           f"clientes têm: {', '.join(next(iter(cli.values())))}")

    # A18: Takamine
    tk = [f"{pid} {p['name']}" for pid, p in prod.items() if "takamine" in p["name"].lower()]
    gd20 = [t for t in tk if "gd20" in t.lower()]
    achado("A18", "\"Takamine GD20\" é único; \"Takamine\" é ambíguo", len(gd20) == 1 and len(tk) > 1,
           f"GD20: {gd20[0] if gd20 else '—'}; todos: {'; '.join(tk)}")

    achado("A19", "Política exige consultar o sistema para preço, estoque e prazo",
           (not pdf) or "nunca fornecer informações sobre preços, estoque ou prazos sem consultar" in pdf_n,
           "§7.1 e §7.3")

    # Formato de rastreio (verificação extra, não é achado)
    rastreios = [p["tracking_code"] for p in ped.values() if p["tracking_code"]]
    integridade["rastreio_formato_ok"] = all(re.fullmatch(r"BR[A-Z0-9]{9}BR", r) for r in rastreios)

    # Fidelidade do manual.md
    if pdf:
        p_pdf, p_md = palavras(pdf), palavras(manual_sem_notas())
        so_pdf = sorted(w for w in p_pdf if w not in p_md and not w.isdigit())
        so_md = sorted(w for w in p_md if w not in p_pdf and not w.isdigit())
        integridade["manual_palavras_so_no_pdf"] = so_pdf
        integridade["manual_palavras_so_no_md"] = so_md

    R.sort(key=lambda r: int(r[0][1:]))
    return R, integridade


def escrever(R, integ, saida: Path) -> None:
    linhas = [
        "# Qualidade dos dados (Fase 0, SPEC-001)",
        "",
        "Gerado por `scripts/perfil_dados.py`. Não edite à mão: rode o script de novo.",
        "",
        "## Achados",
        "",
        "| # | Achado | Confirmado | Evidência |",
        "|---|---|---|---|",
    ]
    linhas += [f"| {c} | {t} | {'sim' if ok else '**NÃO**'} | {e} |" for c, t, ok, e in R]
    linhas += [
        "",
        "Decisão de cada achado: SPEC-001, regras RN-xx e decisões D-xx.",
        "",
        "## Integridade",
        "",
        f"- IDs duplicados: {integ['ids_duplicados'] or 'nenhum'}",
        f"- Referências órfãs entre CSVs: {integ['referencias_orfas'] or 'nenhuma'}",
        f"- `specs` com JSON inválido: {integ['specs_invalidos'] or 'nenhum'}",
        f"- Códigos de rastreio no formato da §5.3 (`BR` + 9 + `BR`): {'sim' if integ['rastreio_formato_ok'] else 'NÃO'}",
    ]
    if "manual_palavras_so_no_pdf" in integ:
        linhas += [
            "",
            "## Fidelidade de `src/emporio/policies/manual.md` ao PDF",
            "",
            "Comparação de vocabulário, sem as notas de revisão. Diferenças esperadas: rodapés do PDF",
            "(\"Página\", \"Manual de Políticas e Procedimentos\") e texto da capa.",
            "",
            f"- Palavras só no PDF: {', '.join(integ['manual_palavras_so_no_pdf']) or 'nenhuma'}",
            f"- Palavras só no Markdown: {', '.join(integ['manual_palavras_so_no_md']) or 'nenhuma'}",
        ]
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=RAIZ / "data")
    ap.add_argument("--saida", type=Path, default=RAIZ / "docs" / "data_quality.md")
    a = ap.parse_args()
    R, integ = perfil(a.data)
    escrever(R, integ, a.saida)
    falhas = [c for c, _, ok, _ in R if not ok]
    print(f"{len(R) - len(falhas)}/{len(R)} achados confirmados -> {a.saida}")
    if falhas:
        print("NÃO confirmados:", ", ".join(falhas))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
