"""Argumentos tipados das tools. O JSON Schema enviado ao LLM sai destes modelos."""

from __future__ import annotations

from datetime import date
from typing import Literal

from difflib import SequenceMatcher

from pydantic import BaseModel, ConfigDict, Field, field_validator

from emporio.data.normalize import compactar

CATEGORIAS = ["Guitarras", "Baixos", "Baterias e Percussão", "Teclados e Pianos", "Violões",
              "Instrumentos de Sopro (Madeiras)", "Instrumentos de Sopro (Metais)", "Cordas Orquestrais", "Ukuleles"]


def categoria_canonica(valor: str | None) -> str | None:
    """Tolerante a acento e a caractere corrompido pelo modelo ("Violཞs" -> "Violões", visto na Fase 5)."""
    if valor is None or not str(valor).strip():
        return None
    alvo = compactar(str(valor))
    melhor = max(CATEGORIAS, key=lambda c: SequenceMatcher(None, alvo, compactar(c)).ratio())
    if SequenceMatcher(None, alvo, compactar(melhor)).ratio() < 0.7:
        raise ValueError(f"categoria desconhecida: {valor!r}; válidas: {', '.join(CATEGORIAS)}")
    return melhor


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BuscarProdutosArgs(_Args):
    texto: str | None = Field(None, description="Nome, marca, modelo ou característica, como o cliente escreveu")
    categoria: str | None = Field(None, description="Categoria do catálogo",
                                  json_schema_extra={"enum": CATEGORIAS})
    preco_max: float | None = Field(None, gt=0, description="Preço máximo em reais (compara com o melhor preço à vista)")
    marca: str | None = Field(None, description="Marca, quando o cliente pedir uma marca específica")
    so_disponiveis: bool = Field(True, description="Só produtos à venda e com estoque. Use false para "
                                                    "checar um modelo que o cliente citou e pode estar indisponível")
    limite: int = Field(5, ge=1, le=10, description="Máximo de resultados")

    _categoria = field_validator("categoria", mode="before")(categoria_canonica)


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


class CalcularFreteArgs(_Args):
    cidade: str = Field(min_length=2, description="Cidade de entrega informada pelo cliente")
    valor: float = Field(gt=0, description="Valor final da compra em reais (preço que o cliente vai pagar)")


class ConsultarPromocoesArgs(_Args):
    nome: str | None = Field(None, description="Nome da campanha perguntada (ex.: Black Friday). "
                                               "Vazio: lista as promoções ativas")


class RegistrarSolicitacaoArgs(_Args):
    tipo: Literal["reclamacao", "devolucao", "troca", "atendimento_humano", "outro"]
    resumo: str = Field(min_length=5, max_length=800, description="Resumo do pedido do cliente, sem telefone nem e-mail")
    pedido_id: int | None = Field(None, description="Pedido relacionado, se houver e estiver verificado")
    confirmado: bool = Field(description="false: prepara o resumo para mostrar ao cliente. true: grava, e só é "
                                         "aceito depois que o cliente confirmou, em mensagem posterior, o resumo "
                                         "preparado com false")
