"""Modo demonstração (LLM_PROVIDER=fake): responde só o que foi perguntado sobre a loja."""

import json

from emporio.llm.demo import DemoLLMClient

LOJA = {"endereco": "Rua 14 de Maio, 3200", "telefone_whatsapp": "(67) 3341-4444",
        "horario": "segunda a sexta, 09:00 às 18:00", "agora": "01/11/2026 15:43", "aberto_agora": False,
        "proxima_abertura": "terça, 03/11 às 09:00"}


def _responder(pergunta: str, loja: dict = LOJA) -> str:
    msgs = [{"role": "user", "content": pergunta},
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "info_loja", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": json.dumps(loja)}]
    return DemoLLMClient().completar(msgs, []).texto


def test_aberto_agora_responde_so_o_estado_com_a_hora_considerada():
    t = _responder("Estão abertos agora?")
    assert "Agora (01/11/2026 15:43) estamos fechados; voltamos terça, 03/11 às 09:00." in t
    assert "Rua 14 de Maio" not in t and "3341-4444" not in t


def test_aberto_agora_quando_aberto():
    t = _responder("Vocês estão abertos?", {**LOJA, "aberto_agora": True, "agora": "04/11/2026 10:00"})
    assert "Agora (04/11/2026 10:00) estamos abertos." in t


def test_feriado_aparece_no_estado():
    t = _responder("Abre hoje?", {**LOJA, "agora": "02/11/2026 10:00", "feriado_hoje": "Finados"})
    assert "Hoje é feriado (Finados)." in t


def test_endereco_responde_so_o_endereco():
    t = _responder("Qual o endereço?")
    assert "Rua 14 de Maio, 3200" in t and "3341-4444" not in t and "fechados" not in t


def test_horario_traz_o_expediente_e_o_estado():
    t = _responder("Qual o horário de vocês?")
    assert "segunda a sexta, 09:00 às 18:00" in t and "estamos fechados" in t and "Rua" not in t


def test_contato_e_endereco_juntos():
    t = _responder("Me passa o endereço e o telefone")
    assert "Rua 14 de Maio" in t and "(67) 3341-4444" in t
