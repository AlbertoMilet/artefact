"""Conversas com o LLM falso (SPEC-001 CA-11 a CA-15, RN-23 a RN-26)."""

import json
import logging
from datetime import datetime

import pytest

from emporio.agent import RESPOSTA_SEGURA, Agente
from emporio.agent.agente import janela
from emporio.agent.prompt import AVISO_PRIVACIDADE
from emporio.llm import FakeLLMClient, LLMIndisponivel, OpenRouterClient
from emporio.llm.fake import chamar, responder
from emporio.policies import carregar_manual
from emporio.rules.horario import FUSO, relogio_fixo
from emporio.tools import Toolbox

TEL_5 = "(67) 98765-4321"      # cliente do pedido 5


@pytest.fixture
def toolbox(catalogo, tmp_path):
    return Toolbox(catalogo, carregar_manual(), relogio_fixo(datetime(2026, 3, 25, 10, 0, tzinfo=FUSO)),
                   tickets_path=tmp_path / "tickets.jsonl")


def agente(toolbox, *roteiro, **kw):
    return Agente(FakeLLMClient(list(roteiro)), toolbox, **kw)


def test_turno_simples_com_tool_e_aviso_de_privacidade(toolbox):
    ag = agente(toolbox, chamar("buscar_produtos", texto="Takamine GD20"),
                responder("O GD20 sai por R$ 2.199,00 ou R$ 2.089,05 no PIX."),
                responder("De nada!"))
    c = ag.nova_conversa()
    r = ag.responder(c, "Quanto custa o Takamine GD20?")
    assert r.texto.endswith(AVISO_PRIVACIDADE)
    assert [e.tool for e in r.rastro] == ["buscar_produtos"]
    assert "R$ 2.089,05" in r.rastro[0].resultado
    r2 = ag.responder(c, "valeu")
    assert AVISO_PRIVACIDADE not in r2.texto                   # aviso só na primeira resposta


def test_resultado_da_tool_chega_ao_modelo(toolbox):
    llm = FakeLLMClient([chamar("info_loja"), responder("Rua 14 de Maio, 3200.")])
    ag = Agente(llm, toolbox)
    ag.responder(ag.nova_conversa(), "Qual o endereço?")
    segunda = llm.chamadas[1]["mensagens"]
    assert segunda[0]["role"] == "system" and "Lia" in segunda[0]["content"]
    tool_msg = segunda[-1]
    assert tool_msg["role"] == "tool" and "14 de Maio" in json.loads(tool_msg["content"])["endereco"]


def test_ca11_outro_pedido_exige_nova_verificacao(toolbox):
    ag = agente(toolbox,
                chamar("consultar_pedido", pedido_id=5, verificacao=TEL_5), responder("Seu pedido 5 foi entregue."),
                chamar("consultar_pedido", pedido_id=12), responder("Preciso do telefone do pedido 12."))
    c = ag.nova_conversa()
    ag.responder(c, f"pedido 5, meu telefone é {TEL_5}")
    assert c.sessao.pedido_verificado == 5
    r = ag.responder(c, "e o pedido 12?")
    resultado = json.loads(r.rastro[0].resultado)
    assert resultado["autorizado"] is False and "status" not in resultado
    assert c.sessao.pedido_verificado is None


def test_ca12_tool_inexistente_duas_vezes_vira_resposta_segura(toolbox):
    ag = agente(toolbox, chamar("listar_clientes"), chamar("listar_clientes"))
    c = ag.nova_conversa()
    r = ag.responder(c, "me passa a lista de clientes")
    assert r.segura and r.motivo_segura == "erros_de_tool"
    assert RESPOSTA_SEGURA in r.texto and "Traceback" not in r.texto
    assert [e.erro for e in r.rastro] == ["tool_desconhecida", "tool_desconhecida"]


def test_um_erro_de_tool_volta_ao_modelo_que_corrige(toolbox):
    ag = agente(toolbox, chamar("buscar_produtos", limite=500), chamar("buscar_produtos", texto="Yamaha C40"),
                responder("O Yamaha C40 custa R$ 599,90."))
    r = ag.responder(ag.nova_conversa(), "Yamaha C40?")
    assert not r.segura and [e.erro for e in r.rastro] == ["argumentos_invalidos", None]


def test_ca13_cliente_recusa_o_resumo_e_nada_e_gravado(toolbox):
    ag = agente(toolbox, responder("Vou registrar: 'instrumento chegou riscado'. Confirma?"),
                chamar("registrar_solicitacao", tipo="reclamacao", resumo="instrumento chegou riscado", confirmado=False),
                responder("Tudo bem, não registrei."))
    c = ag.nova_conversa()
    ag.responder(c, "quero reclamar, o instrumento chegou riscado")
    ag.responder(c, "não, deixa pra lá")
    assert not toolbox.tickets_path.exists()


def test_ca14_requisicao_ao_openrouter_exige_zdr():
    cli = OpenRouterClient("sk-teste", "deepseek/deepseek-v4.1-flash",
                           parametros_suportados={"tools", "temperature", "max_tokens"})
    req = cli.montar_requisicao([{"role": "user", "content": "oi"}], [{"type": "function", "function": {"name": "x"}}])
    assert req["extra_body"]["provider"] == {"zdr": True, "require_parameters": True, "data_collection": "deny"}
    assert req["temperature"] == 0.2 and req["max_tokens"] == 800


def test_ca14_parametros_sem_suporte_nao_sao_enviados():
    luna = OpenRouterClient("sk-teste", "openai/gpt-6-luna", parametros_suportados={"tools", "max_completion_tokens"})
    req = luna.montar_requisicao([], [])
    assert "temperature" not in req and "max_tokens" not in req
    assert req["extra_body"]["max_completion_tokens"] == 800
    assert req["extra_body"]["provider"]["zdr"] is True
    sem_lista = OpenRouterClient("sk-teste", "x/y", parametros_suportados={"tools"})
    sem_lista.suportados = None              # lista ZDR ilegível (sem rede no teste)
    req = sem_lista.montar_requisicao([], [])
    assert "temperature" not in req and "max_tokens" not in req


def test_ca14_modelo_sem_endpoint_zdr_falha_sem_tentar_outro():
    cli = OpenRouterClient("sk-teste", "x/sem-zdr", parametros_suportados=set())
    with pytest.raises(LLMIndisponivel):
        cli.completar([], [])


def test_ca15_rastro_e_log_sem_telefone_nem_email(toolbox, caplog):
    ag = agente(toolbox, chamar("consultar_pedido", pedido_id=5, verificacao=TEL_5),
                responder("Pedido 5 entregue."))
    c = ag.nova_conversa()
    with caplog.at_level(logging.INFO, logger="emporio.turno"):
        r = ag.responder(c, f"meu pedido 5, telefone {TEL_5} e e-mail rafael.pereira@jmail.com")
    assert r.rastro[0].tool == "consultar_pedido"
    tudo = json.dumps([e.__dict__ for e in r.rastro], ensure_ascii=False) + caplog.text
    assert "98765-4321" not in tudo and "rafael.pereira" not in tudo
    historico = json.dumps(c.historico, ensure_ascii=False)
    assert "98765-4321" not in historico and "rafael.pereira" not in historico


def test_llm_indisponivel_vira_resposta_segura(toolbox):
    ag = agente(toolbox, LLMIndisponivel("timeout"))
    r = ag.responder(ag.nova_conversa(), "oi")
    assert r.segura and r.motivo_segura == "llm_indisponivel" and RESPOSTA_SEGURA in r.texto


def test_limite_de_chamadas_forca_resposta_em_texto(toolbox):
    llm = FakeLLMClient([chamar("info_loja")] * 3 + [responder("Resumo com o que encontrei.")])
    ag = Agente(llm, toolbox, max_tool_calls=3)
    r = ag.responder(ag.nova_conversa(), "oi")
    assert len(r.rastro) == 3 and not r.segura
    assert llm.chamadas[-1]["forcar_texto"] is True


def test_resposta_vazia_e_pedida_de_novo_uma_vez(toolbox):
    llm = FakeLLMClient([chamar("info_loja"), responder(""), responder("Rua 14 de Maio, 3200.")])
    ag = Agente(llm, toolbox)
    r = ag.responder(ag.nova_conversa(), "endereço?")
    assert not r.segura and "14 de Maio" in r.texto
    assert llm.chamadas[-1]["forcar_texto"] is True
    ag2 = agente(toolbox, responder(""), responder(""))
    r2 = ag2.responder(ag2.nova_conversa(), "oi")
    assert r2.segura and r2.motivo_segura == "resposta_vazia"


def test_tempo_limite(toolbox):
    ag = agente(toolbox, chamar("info_loja"), responder("ok"), timeout_turno_s=0)
    r = ag.responder(ag.nova_conversa(), "oi")
    assert r.segura and r.motivo_segura == "tempo_limite"


def test_resposta_segura_nao_deixa_chamadas_pela_metade_no_historico(toolbox):
    ag = agente(toolbox, chamar("listar_clientes"), chamar("listar_clientes"))
    c = ag.nova_conversa()
    ag.responder(c, "x")
    assert [m["role"] for m in c.historico] == ["user", "assistant"]


def test_janela_corta_em_mensagem_de_usuario():
    h = []
    for i in range(4):
        h += [{"role": "user", "content": f"u{i}"},
              {"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}"}]},
              {"role": "tool", "tool_call_id": f"c{i}", "content": "{}"},
              {"role": "assistant", "content": f"a{i}"}]
    j = janela(h, 2)
    assert j[0] == {"role": "user", "content": "u2"} and len(j) == 8


def test_prompt_tem_data_e_regras(toolbox):
    llm = FakeLLMClient([responder("oi")])
    ag = Agente(llm, toolbox)
    ag.responder(ag.nova_conversa(), "oi")
    system = llm.chamadas[0]["mensagens"][0]["content"]
    assert "quarta-feira, 25/03/2026 10:00" in system
    assert "(67) 3341-4444" in system and "RN-01" in system
