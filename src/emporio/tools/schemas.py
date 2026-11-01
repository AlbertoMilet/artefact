"""Argumentos tipados das tools. O JSON Schema enviado ao LLM sai destes modelos."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Categoria = Literal["Guitarras", "Baixos", "Baterias e Percussão", "Teclados e Pianos", "Violões",
                    "Instrumentos de Sopro (Madeiras)", "Instrumentos de Sopro (Metais)",
                    "Cordas Orquestrais", "Ukuleles"]


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BuscarProdutosArgs(_Args):
    texto: str | None = Field(None, description="Nome, marca, modelo ou característica, como o cliente escreveu")
    categoria: Categoria | None = Field(None, description="Categoria do catálogo")
    preco_max: float | None = Field(None, gt=0, description="Preço máximo em reais (compara com o melhor preço à vista)")
    marca: str | None = Field(None, description="Marca, quando o cliente pedir uma marca específica")
    so_disponiveis: bool = Field(True, description="Só produtos à venda e com estoque. Use false para "
                                                    "checar um modelo que o cliente citou e pode estar indisponível")
    limite: int = Field(5, ge=1, le=10, description="Máximo de resultados")


class DetalharProdutoArgs(_Args):
    produto_id: int = Field(description="Id do produto, vindo de buscar_produtos")


class ConsultarPedidoArgs(_Args):
    pedido_id: int = Field(description="Número do pedido informado pelo cliente")
    verificacao: str | None = Field(None, description="Telefone ou e-mail do cadastro, informado pelo cliente. "
                                                      "Obrigatório na primeira consulta de cada pedido")


class VerificarArrependimentoArgs(_Args):
    pedido_id: int = Field(description="Pedido já verificado nesta conversa")
    data_recebimento: date | None = Field(None, description="Data em que o cliente recebeu o produto (AAAA-MM-DD), "
                                                            "informada por ele. Não use a previsão de entrega")
    canal: Literal["online", "loja"] | None = Field(None, description="Onde a compra foi feita, informado pelo cliente")


class ConsultarPoliticasArgs(_Args):
    pergunta: str = Field(min_length=2, description="A dúvida do cliente sobre regras da loja")


class InfoLojaArgs(_Args):
    pass


class RegistrarSolicitacaoArgs(_Args):
    tipo: Literal["reclamacao", "devolucao", "troca", "atendimento_humano", "outro"]
    resumo: str = Field(min_length=5, max_length=800, description="Resumo do pedido do cliente, sem telefone nem e-mail")
    pedido_id: int | None = Field(None, description="Pedido relacionado, se houver e estiver verificado")
    confirmado: bool = Field(description="true só depois que o cliente confirmou o resumo exibido")
