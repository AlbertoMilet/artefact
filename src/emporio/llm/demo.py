"""Modo demonstração sem chave (LLM_PROVIDER=fake). NÃO é um modelo de linguagem.

Roteia por palavras-chave para as tools reais e monta a resposta a partir do JSON devolvido. Serve
para o avaliador ver as tools e as regras funcionando sem OPENROUTER_API_KEY. A qualidade de
conversa do agente só aparece com o modelo real (README, "Exemplos").
"""

from __future__ import annotations

import json
import re

from emporio.alertas.deteccao import pediu_vendedor
from emporio.data.normalize import normalizar
from emporio.llm.base import RespostaLLM
from emporio.llm.fake import chamar, responder

AVISO = "_(modo demonstração, sem modelo de linguagem)_"
# Palavras da pergunta que não descrevem o produto ("quais opções de violões disponíveis custando...")
PALAVRAS_DE_PERGUNTA = set("""
a o as os um uma uns umas de da do das dos e em no na nos nas para pra por com que qual quais quanto quanta
quantos quantas custa custam custando sai saem preco precos valor valores tem tens tenho temos voces voce vcs
me mostre mostra mostrar ver quero queria gostaria procuro procurando opcao opcoes modelo modelos disponivel
disponiveis estoque algum alguma alguns algumas oi ola bom boa dia tarde noite favor por favor mais
informacao informacoes saber duvida duvidas ajuda ajudar
""".split())


def _ultima_do_usuario(mensagens: list[dict]) -> str:
    return next((m["content"] for m in reversed(mensagens) if m["role"] == "user"), "")


def _rotear(texto: str) -> RespostaLLM:
    t = normalizar(texto)
    pedido = re.search(r"pedido\s*(?:n\D{0,3})?(\d+)", t)
    contato = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+|\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}", texto)
    if pedido and contato:
        return chamar("consultar_pedido", pedido_id=int(pedido.group(1)), verificacao=contato.group())
    if pedido:
        return responder(f"Para consultar o pedido {pedido.group(1)}, me informe o telefone ou o e-mail do cadastro. {AVISO}")
    if pediu_vendedor(texto):          # a mesma detecção do alerta (SPEC-003): o aviso à equipe sai em código
        return responder("Claro! A equipe foi avisada e um vendedor fala com você em seguida. Se preferir, o "
                         f"telefone/WhatsApp é (67) 3341-4444. {AVISO}")
    if any(k in t for k in ("endereco", "onde fica", "localiza", "horario", "aberto", "abre", "fecha", "telefone", "contato", "whatsapp")):
        return chamar("info_loja")
    if any(k in t for k in ("devol", "arrepend", "troca", "garantia", "frete", "entrega", "parcel", "pagamento",
                            "pix", "boleto", "promoc", "dados", "corda", "palheta", "acessorio", "amplificador")):
        return chamar("consultar_politicas", pergunta=texto)
    preco = re.search(r"(?:ate|abaixo de|menos de)\s*r?\$?\s*([\d.]+)", t)
    resto = re.sub(r"(?:ate|abaixo de|menos de)\s*r?\$?\s*[\d.]+", "", t)
    args: dict = {"texto": " ".join(w for w in resto.split() if w not in PALAVRAS_DE_PERGUNTA) or None}
    if not args["texto"] and not preco:
        return responder("Oi! Sou a Lia, assistente virtual da Empório da Música. Posso ajudar com instrumentos, "
                         f"preços, pedidos, trocas e horários. O que você procura? {AVISO}")
    if preco:
        args["preco_max"] = float(preco.group(1).replace(".", ""))
    return chamar("buscar_produtos", **{k: v for k, v in args.items() if v is not None})


def _info_loja(pergunta: str, r: dict) -> str:
    """Só o que foi perguntado; o estado leva a hora considerada (o relógio pode ser a data de referência)."""
    t = normalizar(pergunta)
    quer_endereco = any(k in t for k in ("endereco", "onde fica", "localiza"))
    quer_contato = any(k in t for k in ("telefone", "contato", "whatsapp"))
    quer_horario = "horario" in t
    quer_estado = quer_horario or any(k in t for k in ("aberto", "abre", "fecha"))
    if not (quer_endereco or quer_contato or quer_estado):
        quer_endereco = quer_contato = quer_horario = quer_estado = True
    partes = []
    if quer_endereco:
        partes.append(f"{r['endereco']}.")
    if quer_contato:
        partes.append(f"Telefone/WhatsApp {r['telefone_whatsapp']}.")
    if quer_horario:
        partes.append(f"Horário: {r['horario']}.")
    if quer_estado:
        if r.get("feriado_hoje"):
            partes.append(f"Hoje é feriado ({r['feriado_hoje']}).")
        partes.append(f"Agora ({r['agora']}) estamos abertos." if r["aberto_agora"]
                      else f"Agora ({r['agora']}) estamos fechados; voltamos {r['proxima_abertura']}.")
    return " ".join(partes + [AVISO])


def _formatar(nome: str, r: dict, pergunta: str = "") -> str:
    if "erro" in r:
        return f"Não consegui consultar agora ({r['erro']}). {AVISO}"
    if nome == "buscar_produtos":
        itens = r.get("resultados") or r.get("alternativas_semelhantes") or []
        if not itens:
            return f"Não encontrei esse produto disponível no nosso sistema agora. Quer falar com a equipe? {AVISO}"
        linhas = []
        for p in itens:
            if p.get("promocao"):
                pr = p["promocao"]
                linhas.append(f"- {p['nome']}: de {p['preco_tabela']} por {pr['preco_promocional']} ({pr['percentual']})")
            else:
                linhas.append(f"- {p['nome']}: {p['preco_tabela']} ({p.get('preco_pix')} no PIX)")
        return "Encontrei:\n" + "\n".join(linhas) + f"\n{AVISO}"
    if nome == "info_loja":
        return _info_loja(pergunta, r)
    if nome == "consultar_politicas":
        if not r["trechos"]:
            return f"Aqui eu só consigo ajudar com assuntos da Empório da Música. {AVISO}"
        t = r["trechos"][0]
        return f"Pela nossa política ({t['secao']} {t['titulo']}):\n{t['texto'][:600]}\n{AVISO}"
    if nome == "consultar_pedido":
        if not r.get("autorizado"):
            return f"{r['mensagem']} {AVISO}"
        rastreio = f", rastreio {r['codigo_rastreio']}" if r.get("codigo_rastreio") else ""
        return (f"Pedido {r['pedido_id']}: {r['status']} (feito em {r['data_pedido']}, total {r['total_registrado']}"
                f"{rastreio}). {AVISO}")
    return f"{json.dumps(r, ensure_ascii=False)[:500]} {AVISO}"


class DemoLLMClient:
    modelo = "demo/sem-llm"

    def completar(self, mensagens: list[dict], tools: list[dict], forcar_texto: bool = False,
                  sem_raciocinio: bool = False) -> RespostaLLM:
        ultima = mensagens[-1]
        if ultima["role"] == "tool":
            chamada = next(m for m in reversed(mensagens) if m.get("tool_calls"))
            nome = chamada["tool_calls"][-1]["function"]["name"]
            return responder(_formatar(nome, json.loads(ultima["content"]), _ultima_do_usuario(mensagens)))
        if forcar_texto:
            return responder(f"Não consegui concluir a consulta. {AVISO}")
        return _rotear(_ultima_do_usuario(mensagens))
