"""Implementação das 7 tools (SPEC-001 §4.2) e do executor usado pelo agente.

Princípios:
- Toda decisão (preço, elegibilidade, autorização) vem de `emporio.rules`; o LLM só redige.
- Valores saem já formatados ("R$ 2.089,05") para o LLM não reescrever números (RN-01, risco do §7).
- Nada de telefone ou e-mail na saída (RN-24); só o primeiro nome do cliente verificado.
- Erro de argumento ou tool desconhecida vira um dicionário {"erro": ...}, nunca uma exceção (RN-26).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from emporio.data.loader import Catalogo
from emporio.data.models import Pedido, Produto
from emporio.data.normalize import normalizar
from emporio.policies.busca import Manual
from emporio.rules.catalogo import Resultado, buscar, disponibilidade
from emporio.rules.devolucao import elegivel_arrependimento
from emporio.rules.dinheiro import brl
from emporio.rules.frete import frete
from emporio.rules.horario import Calendario, Relogio, aberto_agora, proxima_abertura, relogio_real
from emporio.rules.parcelamento import parcelamento_maximo
from emporio.rules.precos import preco_final
from emporio.rules.limites import TENTATIVAS_VERIFICACAO
from emporio.rules.nome_cliente import primeiro_nome
from emporio.rules.privacidade import PRAZO_RESPOSTA_TITULAR_DIAS
from emporio.rules.verificacao import cliente_do_telefone, mascarar_texto, verificar_dono
from emporio.tools import schemas as S

log = logging.getLogger(__name__)

LOJA = {
    "nome": "Empório da Música",
    "endereco": "Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, CEP 79202-333",
    "telefone_whatsapp": "(67) 3341-4444",          # D-08 (A1)
    "email": "contato@emporiodamusica.com.br",       # D-08 (A2)
    "horario": "segunda a sexta, 09:00 às 18:00; sábado, 09:00 às 13:00; domingos e feriados, fechado",
}

STATUS_PEDIDO = {"pending": "pendente", "confirmed": "confirmado", "shipped": "enviado",
                 "delivered": "entregue", "cancelled": "cancelado"}
DISPONIBILIDADE = {"disponivel": "disponível", "sem_estoque": "indisponível no momento (sem estoque)",
                   "descontinuado": "descontinuado (fora do catálogo)", "em_breve": "em breve (ainda não à venda)"}
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
RELEVANCIA_FORTE = 0.85     # abaixo disso, o resultado é só parecido com o que o cliente pediu
MSG_NAO_AUTORIZADO = ("Não foi possível confirmar o pedido com os dados informados. Peça ao cliente para conferir "
                      "o número do pedido e o telefone ou e-mail do cadastro.")


def _data(d: date | None) -> str | None:
    return d.strftime("%d/%m/%Y") if d else None


def _pagamento(metodo: str) -> str:
    if metodo.startswith("credit_"):
        return f"cartão de crédito em {metodo.removeprefix('credit_')}"
    return {"pix": "PIX", "debit": "cartão de débito", "boleto": "boleto bancário"}.get(metodo, metodo)


@dataclass
class Sessao:
    """Estado explícito da conversa (SPEC-001 §4.3)."""
    pedido_verificado: int | None = None
    registros: list[str] = field(default_factory=list)
    turno: int = 0                              # turno atual do cliente (o agente atualiza)
    atendimento_humano: bool = False            # solicitação de atendimento humano registrada (SPEC-002 RI-11)
    registro_proposto: dict | None = None       # resumo preparado e ainda não confirmado (§4.3 da spec)
    origem: str | None = None                   # canal de onde veio o lead (SPEC-005), detectado em código
    nome_cliente: str | None = None             # primeiro nome do perfil do WhatsApp, já filtrado (SPEC-010)
    perfil_sem_nome: bool = False               # o WhatsApp mandou o perfil, mas sem nome usável (SPEC-010)
    cliente_canal: int | None = None            # customer_id do número do remetente; nunca o número (SPEC-011)
    verificacoes_falhas: int = 0                # verificações de pedido que não conferiram (SPEC-013 RS-06)
    nome_do_cadastro: bool = False              # nome_cliente veio do customers.csv, não do perfil (SPEC-011 RP-08)


@dataclass(frozen=True)
class Tool:
    nome: str
    descricao: str
    args: type[BaseModel]
    funcao: Callable[..., dict]


class Toolbox:
    def __init__(self, catalogo: Catalogo, manual: Manual, relogio: Relogio = relogio_real,
                 calendario: Calendario | None = None, tickets_path: Path | str = "tickets.jsonl"):
        self.catalogo = catalogo
        self.manual = manual
        self.relogio = relogio
        self.calendario = calendario or Calendario()
        self.tickets_path = Path(tickets_path)
        self.tools: dict[str, Tool] = {t.nome: t for t in [
            Tool("buscar_produtos", "Busca instrumentos no catálogo com preço, promoção, PIX e disponibilidade. "
                 "Use para qualquer pergunta sobre produto, preço ou estoque.", S.BuscarProdutosArgs, self.buscar_produtos),
            Tool("detalhar_produto", "Detalhes de um produto: preço, PIX, promoção, parcelamento máximo no cartão, "
                 "especificações e disponibilidade.", S.DetalharProdutoArgs, self.detalhar_produto),
            Tool("consultar_pedido", "Status, rastreio, previsão e itens de um pedido. Exige o número do pedido e o "
                 "telefone ou e-mail do cadastro, a não ser que o pedido seja do cliente identificado pelo número "
                 "do WhatsApp (veio de meus_pedidos).", S.ConsultarPedidoArgs, self.consultar_pedido),
            Tool("meus_pedidos", "Pedidos do cliente identificado pelo número do WhatsApp desta conversa, do mais "
                 "recente para o mais antigo. Use para 'minha última compra', 'meus pedidos'. Sem argumentos.",
                 S.MeusPedidosArgs, self.meus_pedidos),
            Tool("verificar_arrependimento", "Decide se um pedido verificado pode ser devolvido por arrependimento "
                 "(compra online, até 7 dias do recebimento). Pergunte ao cliente a data de recebimento e o canal.",
                 S.VerificarArrependimentoArgs, self.verificar_arrependimento),
            Tool("consultar_politicas", "Trechos do manual da loja: trocas, devolução, garantia, frete, pagamento, "
                 "parcelamento, promoções, privacidade.", S.ConsultarPoliticasArgs, self.consultar_politicas),
            Tool("info_loja", "Endereço, telefone, e-mail, horário de funcionamento e se a loja está aberta agora.",
                 S.InfoLojaArgs, self.info_loja),
            Tool("calcular_frete", "Frete e prazo de entrega para uma cidade e um valor de compra (§5).",
                 S.CalcularFreteArgs, self.calcular_frete),
            Tool("consultar_promocoes", "Promoções cadastradas: se uma campanha (ex.: Black Friday) está ativa, ou a "
                 "lista das promoções ativas com produto e preço.", S.ConsultarPromocoesArgs, self.consultar_promocoes),
            Tool("registrar_solicitacao", "Registra (de forma simulada, protótipo) reclamação, devolução, troca, "
                 "pedido de atendimento humano ou pedido do cliente sobre os próprios dados (tipo privacidade: ver, "
                 "corrigir, apagar), em dois passos: confirmado=false prepara o resumo para mostrar ao "
                 "cliente; confirmado=true grava, depois que ele aprovar.",
                 S.RegistrarSolicitacaoArgs, self.registrar_solicitacao),
        ]}

    # ---------------------------------------------------------------- integração com o LLM

    def schemas_openai(self) -> list[dict]:
        out = []
        for t in self.tools.values():
            params = t.args.model_json_schema()
            params.pop("title", None)
            out.append({"type": "function", "function": {"name": t.nome, "description": t.descricao,
                                                          "parameters": params}})
        return out

    def executar(self, nome: str, argumentos: str | dict | None, sessao: Sessao) -> dict:
        tool = self.tools.get(nome)
        if tool is None:
            return {"erro": "tool_desconhecida", "detalhes": f"'{nome}' não existe", "tools": list(self.tools)}
        try:
            dados = json.loads(argumentos) if isinstance(argumentos, str) else (argumentos or {})
            args = tool.args.model_validate(dados)
        except json.JSONDecodeError:
            return {"erro": "argumentos_invalidos", "detalhes": ["JSON inválido"]}
        except ValidationError as e:
            # Só campo, tipo e mensagem: nunca o valor recebido, que pode ser telefone ou e-mail (RN-24)
            detalhes = []
            for err in e.errors(include_input=False, include_url=False):
                campo = ".".join(str(p) for p in err.get("loc", ())) or "argumentos"
                msg = err.get("msg", "")
                if err.get("type") == "value_error" and "categoria" in campo:
                    msg = f"categoria desconhecida; válidas: {', '.join(S.CATEGORIAS)}"
                detalhes.append(f"{campo}: {msg}")
            return {"erro": "argumentos_invalidos", "detalhes": detalhes[:6]}
        try:
            return tool.funcao(args, sessao)
        except Exception:  # falha interna não derruba a conversa
            log.exception("falha na tool %s", nome)
            return {"erro": "falha_interna", "detalhes": "a consulta falhou; ofereça o contato da loja"}

    # ---------------------------------------------------------------- produtos

    def _resumo(self, r: Resultado | None = None, produto: Produto | None = None) -> dict:
        p = r.produto if r else produto
        preco = r.preco if r else preco_final(p, self.catalogo.promocoes_ativas(p.product_id))
        disp = r.disponibilidade if r else disponibilidade(p)
        out = {
            "produto_id": p.product_id, "nome": p.name, "marca": p.marca,
            "categoria": self.catalogo.categoria_nome(p.category_id),
            "disponibilidade": DISPONIBILIDADE[disp],
            "preco_tabela": brl(preco.tabela),
        }
        if disp in ("descontinuado", "em_breve"):
            out["observacao"] = "não está à venda: não informe preço como oferta; sugira um equivalente disponível"
            return out
        if preco.promocao:
            pct = preco.promocao.discount_percent
            pct_txt = f"{int(pct)}%" if pct == pct.to_integral_value() else f"{pct}%".replace(".", ",")
            out["promocao"] = {"descricao": preco.promocao.description,
                               "percentual": pct_txt,
                               "preco_promocional": brl(preco.final),
                               "economia": brl(preco.tabela - preco.final)}      # RN-01: a conta é do código
            out["preco_pix"] = None
            out["obs_pix"] = "o desconto do PIX não se aplica sobre preço promocional (§6.2)"
        else:
            out["preco_pix"] = brl(preco.pix)
            out["economia_pix"] = brl(preco.tabela - preco.pix)                  # RN-01: a conta é do código
        if disp == "disponivel":
            out["estoque"] = p.stock_quantity
        return out

    def buscar_produtos(self, a: S.BuscarProdutosArgs, sessao: Sessao) -> dict:
        res = buscar(self.catalogo, a.texto, a.categoria, a.preco_max, a.marca, a.so_disponiveis, a.limite,
                     so_promocao=a.so_promocao)
        fortes = [r for r in res if r.relevancia >= RELEVANCIA_FORTE]
        if fortes:
            return {"resultados": [self._resumo(r) for r in fortes], "total": len(fortes)}

        saida: dict[str, Any] = {"resultados": [], "total": 0}
        if a.so_disponiveis and a.texto:
            # o modelo pedido existe, mas não está à venda? (descontinuado, sem estoque, em breve)
            todos = buscar(self.catalogo, a.texto, a.categoria, None, a.marca, False, 3)
            exatos = [r for r in todos if r.relevancia >= RELEVANCIA_FORTE and r.disponibilidade != "disponivel"]
            if exatos:
                saida["indisponiveis_com_esse_nome"] = [self._resumo(r) for r in exatos]
        if res:
            saida["alternativas_semelhantes"] = [self._resumo(r) for r in res]
            saida["orientacao"] = ("Nenhum produto corresponde exatamente ao pedido. Os itens em "
                                   "alternativas_semelhantes são parecidos, não o modelo pedido: apresente-os "
                                   "como alternativas.")
            return saida
        if a.categoria:
            alternativas = buscar(self.catalogo, None, a.categoria, None, None, True, 3)
            if alternativas:
                saida["alternativas_na_categoria"] = [self._resumo(r) for r in alternativas]
        saida["orientacao"] = ("Nada encontrado com esses critérios. Diga que não encontrou no sistema agora; "
                               "ofereça alternativas cadastradas, se houver, ou o contato da equipe. "
                               "Não afirme que a loja não vende a categoria.")
        return saida

    def detalhar_produto(self, a: S.DetalharProdutoArgs, sessao: Sessao) -> dict:
        p = self.catalogo.produtos.get(a.produto_id)
        if p is None:
            return {"erro": "produto_inexistente", "detalhes": f"não há produto {a.produto_id}"}
        out = self._resumo(produto=p)
        out["especificacoes"] = p.specs_normalizadas
        if p.descricao_confiavel:
            out["descricao"] = p.description
        else:
            out["descricao"] = None
            out["aviso"] = "descrição cadastrada inconsistente com o nome; use só nome, preço e especificações"
        if disponibilidade(p) in ("disponivel", "sem_estoque"):
            preco = preco_final(p, self.catalogo.promocoes_ativas(p.product_id))
            parc = parcelamento_maximo(preco.final)
            out["parcelamento_cartao"] = {
                "parcelas_max": parc.parcelas,
                "valor_parcela": brl(parc.valor_parcela),
                "primeira_parcela": brl(parc.primeira_parcela),
                "total_no_cartao": brl(parc.total),
                "regra": "sem juros; até 3x parcela >= R$ 50, 4x-6x >= R$ 80, 7x-12x >= R$ 100 (§3.1)",
            }
        return out

    # ---------------------------------------------------------------- pedidos

    def _pedido_autorizado(self, pedido_id: int, verificacao: str | None, sessao: Sessao) -> Pedido | None:
        pedido = self.catalogo.pedidos.get(pedido_id)
        if pedido is None:
            return None
        if sessao.cliente_canal is not None and pedido.customer_id == sessao.cliente_canal:
            sessao.pedido_verificado = pedido_id     # SPEC-011: do dono do número do WhatsApp
            return pedido
        if verificacao:
            cliente = self.catalogo.clientes[pedido.customer_id]
            if verificar_dono(cliente, verificacao):
                sessao.pedido_verificado = pedido_id
                return pedido
            if sessao.pedido_verificado == pedido_id:
                sessao.pedido_verificado = None
            return None
        return pedido if sessao.pedido_verificado == pedido_id else None

    def consultar_pedido(self, a: S.ConsultarPedidoArgs, sessao: Sessao) -> dict:
        if sessao.pedido_verificado not in (None, a.pedido_id):
            sessao.pedido_verificado = None          # outro pedido: a verificação anterior cai (RN-08)
        do_canal = self.catalogo.pedidos.get(a.pedido_id)
        do_canal = do_canal is not None and sessao.cliente_canal == do_canal.customer_id
        if a.verificacao and not do_canal and sessao.verificacoes_falhas >= TENTATIVAS_VERIFICACAO:
            return {"autorizado": False, "erro": "muitas_tentativas",          # SPEC-013 RS-06
                    "mensagem": "Muitas tentativas de verificação nesta conversa. Não tente de novo: ofereça o "
                                "contato da equipe (telefone, e-mail e horário) para o cliente confirmar o pedido."}
        pedido = self._pedido_autorizado(a.pedido_id, a.verificacao, sessao)
        if pedido is None:
            if a.verificacao and not do_canal:
                sessao.verificacoes_falhas += 1
            return {"autorizado": False, "mensagem": MSG_NAO_AUTORIZADO}
        cliente = self.catalogo.clientes[pedido.customer_id]
        itens = [{"produto": self.catalogo.produtos[i.product_id].name, "quantidade": i.quantity}
                 for i in self.catalogo.itens.get(pedido.order_id, [])]
        return {
            "autorizado": True,
            "pedido_id": pedido.order_id,
            "cliente_primeiro_nome": cliente.name.split()[0],
            "status": STATUS_PEDIDO[pedido.status],
            "data_pedido": _data(pedido.order_date),
            "total_registrado": brl(pedido.total_brl),
            "forma_pagamento": _pagamento(pedido.payment_method),
            "codigo_rastreio": pedido.tracking_code,
            "previsao_entrega_original": _data(pedido.estimated_delivery),
            "observacao": pedido.notes,
            "itens": itens,
            "nota": ("valores como registrados no pedido; não recalcule com preços atuais (RN-12). "
                     "previsao_entrega_original é só a previsão feita na compra: não diga que o produto foi "
                     "entregue ou recebido nessa data"),
        }

    def cliente_do_canal(self, telefone: str | None) -> int | None:
        """customer_id do número do remetente (SPEC-011), ou None."""
        cliente = cliente_do_telefone(self.catalogo.clientes.values(), telefone)
        return cliente.customer_id if cliente else None

    def primeiro_nome_do_cliente(self, customer_id: int | None) -> str | None:
        """Primeiro nome do cadastro (customers.csv), para tratar o cliente identificado pelo canal."""
        cliente = self.catalogo.clientes.get(customer_id) if customer_id is not None else None
        return primeiro_nome(cliente.name) if cliente else None

    def meus_pedidos(self, a: S.MeusPedidosArgs, sessao: Sessao) -> dict:
        if sessao.cliente_canal is None:
            return {"identificado": False, "mensagem": (
                "O número deste WhatsApp não está no cadastro. Peça o número do pedido e o telefone ou e-mail "
                "do cadastro para usar consultar_pedido.")}
        cliente = self.catalogo.clientes[sessao.cliente_canal]
        pedidos = sorted((p for p in self.catalogo.pedidos.values() if p.customer_id == cliente.customer_id),
                         key=lambda p: (p.order_date, p.order_id), reverse=True)
        return {
            "identificado": True,
            "cliente_primeiro_nome": cliente.name.split()[0],
            "total_de_pedidos": len(pedidos),
            "pedidos": [{
                "pedido_id": p.order_id,
                "data_pedido": _data(p.order_date),
                "status": STATUS_PEDIDO[p.status],
                "total_registrado": brl(p.total_brl),
                "itens": [{"produto": self.catalogo.produtos[i.product_id].name, "quantidade": i.quantity}
                          for i in self.catalogo.itens.get(p.order_id, [])],
            } for p in pedidos[:5]],
            "nota": ("o primeiro da lista é o mais recente. Para rastreio, previsão ou devolução, use "
                     "consultar_pedido com o pedido_id, sem pedir telefone ou e-mail. Valores como registrados."),
        }

    def verificar_arrependimento(self, a: S.VerificarArrependimentoArgs, sessao: Sessao) -> dict:
        if sessao.pedido_verificado != a.pedido_id:
            return {"autorizado": False, "mensagem": "Verifique o pedido com consultar_pedido antes."}
        pedido = self.catalogo.pedidos[a.pedido_id]
        hoje = self.relogio().date()
        r = elegivel_arrependimento(pedido.status, a.data_recebimento, a.canal, hoje, pedido.order_date)
        out: dict[str, Any] = {
            "autorizado": True, "pedido_id": a.pedido_id, "status_pedido": STATUS_PEDIDO[pedido.status],
            "elegivel": r.elegivel, "motivo": r.motivo, "hoje": _data(hoje),
        }
        if r.dias_desde_recebimento is not None:
            out["dias_desde_recebimento"] = r.dias_desde_recebimento
        if r.condicoes:
            out["condicoes"] = r.condicoes
        if r.alternativas:
            out["alternativas"] = [{"tipo": x.tipo, "regra": x.regra, "dentro_do_prazo": x.dentro_do_prazo}
                                   for x in r.alternativas]
        out["orientacao"] = {
            "dentro_do_prazo": "Elegível. Explique as condições e ofereça registrar a solicitação.",
            "fora_do_prazo": "Não elegível ao arrependimento. Apresente as alternativas; não trate como defeito. "
                             "Ofereça também a revisão do caso pela equipe, se o cliente quiser (SPEC-012 RL-10).",
            "compra_na_loja": "Arrependimento vale só para compra online. Apresente as alternativas. Ofereça também "
                              "a revisão do caso pela equipe, se o cliente quiser (SPEC-012 RL-10).",
            "faltam_dados": "Pergunte a data em que recebeu e se a compra foi online; explique a regra de forma "
                            "condicional enquanto isso.",
            "pedido_nao_entregue": "O pedido ainda não foi entregue; informe o status e ofereça a equipe.",
            "data_invalida": "A data informada é posterior a hoje; peça para conferir.",
        }[r.motivo]
        return out

    # ---------------------------------------------------------------- políticas e loja

    def consultar_politicas(self, a: S.ConsultarPoliticasArgs, sessao: Sessao) -> dict:
        trechos = self.manual.buscar(a.pergunta)
        if not trechos:
            return {"trechos": [], "indice": self.manual.secoes,
                    "orientacao": "Nada relevante no manual. Se for assunto da loja, ofereça confirmar com a equipe; "
                                  "se for fora do escopo, recuse com gentileza."}
        return {"trechos": [{"secao": t.secao, "titulo": t.titulo, "texto": t.texto} for t in trechos]}

    def info_loja(self, a: S.InfoLojaArgs, sessao: Sessao) -> dict:
        agora = self.relogio()
        aberto = aberto_agora(agora, self.calendario)
        out = {**LOJA, "agora": agora.strftime("%d/%m/%Y %H:%M"), "aberto_agora": aberto}
        feriado = self.calendario.feriado(agora.date())
        if feriado:
            out["feriado_hoje"] = feriado
        if not aberto:
            prox = proxima_abertura(agora, self.calendario)
            out["proxima_abertura"] = f"{DIAS[prox.weekday()]}, {prox.strftime('%d/%m')} às {prox.strftime('%H:%M')}"
        return out

    def calcular_frete(self, a: S.CalcularFreteArgs, sessao: Sessao) -> dict:
        f = frete(a.cidade, Decimal(str(a.valor)))
        out: dict[str, Any] = {"cidade": a.cidade, "valor_compra": brl(Decimal(str(a.valor))), "tipo": f.tipo,
                               "prazo": f.prazo, "observacao": f.observacao}
        if f.tipo == "metropolitano":
            out["frete"] = "grátis" if f.valor == 0 else brl(f.valor)
            out["regra"] = "grátis só acima de R$ 500,00; até R$ 500,00, inclusive, taxa de R$ 35,00 (§5.1)"
        else:
            out["frete"] = None
            out["modalidades"] = f.modalidades
            out["orientacao"] = "Não informe valor de frete: depende de CEP, peso e dimensões (§5.2)."
        return out

    def consultar_promocoes(self, a: S.ConsultarPromocoesArgs, sessao: Sessao) -> dict:
        def item(pr) -> dict:
            p = self.catalogo.produtos[pr.product_id]
            d: dict[str, Any] = {"campanha": pr.description, "produto": p.name, "ativa": pr.is_active}
            if pr.is_active and disponibilidade(p) in ("disponivel", "sem_estoque"):
                preco = preco_final(p, self.catalogo.promocoes_ativas(p.product_id))
                d.update(preco_original=brl(preco.tabela), preco_promocional=brl(preco.final),
                         percentual=f"{int(pr.discount_percent)}%" if pr.discount_percent == pr.discount_percent.to_integral_value()
                         else f"{pr.discount_percent}%")
            return d

        if not a.nome:
            ativas = [item(pr) for pr in self.catalogo.promocoes if pr.is_active]
            return {"promocoes_ativas": ativas, "total": len(ativas)}
        alvo = normalizar(a.nome)
        casam = [pr for pr in self.catalogo.promocoes if alvo in normalizar(pr.description)
                 or normalizar(pr.description) in alvo]
        ativas = [item(pr) for pr in casam if pr.is_active]
        out: dict[str, Any] = {"campanha_perguntada": a.nome, "ativas_com_esse_nome": ativas}
        if not ativas:
            out["orientacao"] = ("Nenhuma promoção com esse nome está ativa no sistema agora. Diga isso com "
                                 "transparência e apresente o preço atual se o cliente citar um produto; não diga "
                                 "quando terminou nem quando volta (as promoções não têm datas cadastradas).")
        return out

    def registrar_solicitacao(self, a: S.RegistrarSolicitacaoArgs, sessao: Sessao) -> dict:
        if a.pedido_id is not None and sessao.pedido_verificado != a.pedido_id:
            return {"gravado": False, "orientacao": "O pedido citado não foi verificado nesta conversa."}
        if not a.confirmado:
            if not a.resumo:
                return {"gravado": False, "erro": "resumo_obrigatorio",
                        "orientacao": "Com confirmado=false, escreva o resumo que o cliente vai aprovar."}
            sessao.registro_proposto = {"tipo": a.tipo, "resumo": a.resumo, "pedido_id": a.pedido_id,
                                        "turno": sessao.turno}
            out = {"gravado": False, "resumo_para_confirmar": a.resumo, "tipo": a.tipo,
                   "orientacao": "Mostre este resumo ao cliente e pergunte se pode registrar. Só chame com "
                                 "confirmado=true depois que ele responder que sim."}
            if a.tipo == "privacidade":                   # SPEC-012 RL-04
                out["prazo_resposta"] = f"até {PRAZO_RESPOSTA_TITULAR_DIAS} dias"
            return out
        proposta = sessao.registro_proposto
        if proposta is None or proposta["turno"] >= sessao.turno or proposta["tipo"] != a.tipo:
            return {"gravado": False, "orientacao": "Antes de gravar, chame com confirmado=false, mostre o resumo e "
                                                    "espere o cliente confirmar numa nova mensagem."}
        mudou_resumo = a.resumo is not None and " ".join(a.resumo.split()) != " ".join(proposta["resumo"].split())
        mudou_pedido = a.pedido_id is not None and a.pedido_id != proposta["pedido_id"]
        if mudou_resumo or mudou_pedido:
            return {"gravado": False, "erro": "proposta_alterada",
                    "orientacao": "O resumo ou o pedido mudou depois que o cliente aprovou. Mostre o novo resumo "
                                  "(confirmado=false) e peça a confirmação de novo; para gravar o que ele aprovou, "
                                  "chame com confirmado=true sem resumo."}
        sessao.registro_proposto = None
        if a.tipo == "atendimento_humano":
            sessao.atendimento_humano = True
        agora = self.relogio()
        existentes = 0
        if self.tickets_path.exists():
            existentes = sum(1 for _ in self.tickets_path.open(encoding="utf-8"))
        protocolo = f"SIM-{agora:%Y%m%d}-{existentes + 1:04d}"
        registro = {"protocolo": protocolo, "criado_em": agora.isoformat(), "tipo": a.tipo,   # grava o aprovado
                    "pedido_id": proposta["pedido_id"], "resumo": mascarar_texto(proposta["resumo"]),
                    "origem": sessao.origem, "simulado": True}
        self.tickets_path.parent.mkdir(parents=True, exist_ok=True)
        with self.tickets_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        sessao.registros.append(protocolo)
        if a.tipo == "privacidade":                       # SPEC-012 RL-04: prazo do art. 19, II, da LGPD
            return {"gravado": True, "protocolo_simulado": protocolo,
                    "texto_para_cliente": (f"Registrei seu pedido sobre seus dados pessoais (protótipo), protocolo "
                                           f"{protocolo}. A equipe responde em até {PRAZO_RESPOSTA_TITULAR_DIAS} dias."),
                    "orientacao": "Informe o protocolo e o prazo de resposta; não prometa que os dados já foram apagados."}
        return {"gravado": True, "protocolo_simulado": protocolo,
                "texto_para_cliente": f"Registrei sua solicitação (protótipo), protocolo {protocolo}.",
                "orientacao": "Não prometa prazo de retorno; informe os canais da loja (telefone, e-mail, horário)."}
