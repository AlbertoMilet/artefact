"""Decisão de retenção com o modelo real (SPEC-002 CI-10). `uv run pytest -m llm`."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from emporio.config import MODELO_PADRAO, Config, montar_llm
from emporio.retencao import Acompanhamento, ConfigRetencao, Retencao, politica
from emporio.rules.horario import FUSO

pytestmark = pytest.mark.llm

T0 = datetime(2026, 3, 25, 10, 0, tzinfo=FUSO)

CENARIOS = {
    "lista_sem_resposta": ("ENVIAR", [
        ("user", "Quais violões vocês têm até R$ 1000?"),
        ("assistant", "Tenho 5 opções: Tagima Memphis AC-39, Rozini RC-104, Shelby SN-100, Giannini GF-1R e "
                      "Yamaha C40. Quer que eu te conte mais de algum?")]),
    "volta_depois": ("ESPERAR", [
        ("user", "Quanto custa o Takamine GD20?"),
        ("assistant", "O Takamine GD20 sai por R$ 2.199,00, ou R$ 2.089,05 no PIX. Quer ver o parcelamento?"),
        ("user", "Depois eu vejo, tô no trabalho agora. Falo com você à noite.")]),
    "resolvido": ("PARAR", [
        ("user", "Qual o endereço da loja?"),
        ("assistant", "Ficamos na Rua 14 de Maio, 3200, Centro, Campo Grande."),
        ("user", "Obrigado, era só isso!"),
        ("assistant", "De nada! Qualquer coisa é só chamar. 🎸")]),
    "pergunta_pendente": ("ENVIAR", [
        ("user", "Me arrependi da compra do pedido 5, posso devolver?"),
        ("assistant", "Achei seu pedido, Rafael. Para eu verificar o prazo, em que data você recebeu o produto "
                      "e a compra foi pelo site ou na loja?")]),
}


@pytest.fixture(scope="module")
def retencao():
    config = replace(Config.do_ambiente(usar_preferencias=False), llm_provider="openrouter", openrouter_model=MODELO_PADRAO)
    if not config.openrouter_api_key:
        pytest.skip("OPENROUTER_API_KEY não definida")
    return Retencao(montar_llm(config), ConfigRetencao(ativa=True))


@pytest.mark.parametrize("nome", list(CENARIOS))
def test_ci10_decisao_de_retencao(retencao, nome):
    esperado, conversa = CENARIOS[nome]
    historico = [{"role": r, "content": c} for r, c in conversa]
    ac = Acompanhamento(ultima_msg_cliente=T0, ultima_msg_auto=T0)
    ac.proxima_avaliacao = T0 + timedelta(minutes=30)
    av = retencao.avaliar(ac, historico, T0 + timedelta(minutes=30))
    assert av.acao == esperado, (av.acao, av.motivo, av.mensagem)
    if av.acao == "ENVIAR":
        assert politica.conferir_lembrete(av.mensagem, []) == []
