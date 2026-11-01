"""Inatividade na janela de 24 h (SPEC-002): janela, agenda, bloqueios, conferência e decisão."""

import json
from datetime import datetime, timedelta

import pytest

from emporio.llm import FakeLLMClient
from emporio.llm.fake import responder
from emporio.retencao import Acompanhamento, ConfigRetencao, Retencao, Status
from emporio.retencao import janela, politica
from emporio.rules.horario import FUSO

T0 = datetime(2026, 3, 25, 10, 0, tzinfo=FUSO)     # quarta-feira
CFG = ConfigRetencao(ativa=True)
HIST = [{"role": "user", "content": "Quais violões até R$ 1000?"},
        {"role": "assistant", "content": "Tenho o Tagima Memphis e o Yamaha C40. Quer detalhes?"}]


def ac_novo(ultima=T0, auto=T0):
    ac = Acompanhamento(ultima_msg_cliente=ultima, ultima_msg_auto=auto)
    politica.agendar(ac, CFG, ultima)
    return ac


def decisao(**kw):
    return responder(json.dumps({"motivo": "teste", **kw}, ensure_ascii=False))


# ---------------------------------------------------------------- janela (RI-01, RI-02)

def test_ci01_janela_e_margem_de_envio():
    assert janela.expira_em(T0) == T0 + timedelta(hours=24)
    assert janela.aberta(T0, T0 + timedelta(hours=23, minutes=58))
    assert not janela.aberta(T0, T0 + timedelta(hours=24))
    ac = ac_novo()
    assert politica.limite_envio(ac, CFG) == datetime(2026, 3, 26, 9, 30, tzinfo=FUSO)
    assert politica.bloqueio(ac, CFG, datetime(2026, 3, 26, 9, 29, tzinfo=FUSO)) is None
    b = politica.bloqueio(ac, CFG, datetime(2026, 3, 26, 9, 30, tzinfo=FUSO))
    assert b.status == Status.JANELA_FECHADA and b.terminal


def test_ci02_lembrete_nao_reabre_a_janela():
    ret = Retencao(FakeLLMClient([decisao(acao="ENVIAR", mensagem="Ficou alguma dúvida sobre os violões?")]), CFG)
    ac = ac_novo()
    ret.avaliar(ac, list(HIST), T0 + timedelta(minutes=30))
    assert ac.total_lembretes == 1
    assert politica.limite_envio(ac, CFG) == datetime(2026, 3, 26, 9, 30, tzinfo=FUSO)   # a âncora não mudou


def test_ci03_agenda_com_horario_silencioso():
    ac = ac_novo()
    assert ac.proxima_avaliacao == T0 + timedelta(minutes=30)
    politica.agendar(ac, CFG, T0 + timedelta(minutes=30))
    assert ac.proxima_avaliacao == T0 + timedelta(hours=4)
    politica.agendar(ac, CFG, T0 + timedelta(hours=4))
    # 21 h depois das 10h = 7h do dia 26 (silêncio) -> 8h, antes do limite das 9h30
    assert ac.proxima_avaliacao == datetime(2026, 3, 26, 8, 0, tzinfo=FUSO)


def test_agenda_sem_horario_possivel_vai_para_o_limite():
    ac = ac_novo(ultima=datetime(2026, 3, 25, 20, 0, tzinfo=FUSO))
    politica.agendar(ac, CFG, datetime(2026, 3, 26, 15, 0, tzinfo=FUSO), pedido=datetime(2026, 3, 26, 23, 0, tzinfo=FUSO))
    assert ac.proxima_avaliacao == politica.limite_envio(ac, CFG)


def test_bloqueios_nao_terminais():
    ac = ac_novo(auto=T0 + timedelta(minutes=25))
    b = politica.bloqueio(ac, CFG, T0 + timedelta(minutes=30))
    assert b.motivo == "mensagem_automatica_recente" and not b.terminal
    assert b.tentar_em == T0 + timedelta(minutes=45)
    noite = Acompanhamento(ultima_msg_cliente=datetime(2026, 3, 25, 20, 0, tzinfo=FUSO))
    b = politica.bloqueio(noite, CFG, datetime(2026, 3, 25, 22, 0, tzinfo=FUSO))
    assert b.motivo == "horario_silencioso" and b.tentar_em == datetime(2026, 3, 26, 8, 0, tzinfo=FUSO)


# ---------------------------------------------------------------- pedido para parar (RI-07)

@pytest.mark.parametrize("texto", ["pare de me mandar mensagem", "PARE", "Não quero mais receber isso", "me tira da lista",
                                   "não quero receber mais mensagens", "não desejo receber lembretes", "pare de me enviar isso"])
def test_quer_parar(texto):
    assert politica.quer_parar(texto)


@pytest.mark.parametrize("texto", ["não quero esse violão, prefere outro?", "parei de tocar faz tempo", "obrigado"])
def test_nao_e_pedido_para_parar(texto):
    assert not politica.quer_parar(texto)


def test_ci04_pedido_para_parar_encerra_sem_chamar_o_modelo():
    llm = FakeLLMClient([])
    ret = Retencao(llm, CFG)
    ac = Acompanhamento()
    ret.ao_receber(ac, "pare de me mandar mensagem", T0)
    assert ac.status == Status.ENCERRADO and ac.optou_sair
    assert ret.avaliar(ac, list(HIST), T0 + timedelta(hours=1)) is None
    ret.ao_receber(ac, "oi, quero ver violões", T0 + timedelta(hours=2))      # conversa segue, retenção não
    assert ac.status == Status.ENCERRADO and ac.proxima_avaliacao is None
    assert llm.chamadas == []


# ---------------------------------------------------------------- conferência do lembrete (RI-08)

@pytest.mark.parametrize("texto, problema", [
    ("O Takamine GD20 está por R$ 2.199,00, quer?", "contem_valor"),
    ("Posso reservar um pra você?", "promessa:reserv"),
    ("Consigo um desconto especial, topa?", "promocional:desconto"),
    ("Temos estoque e entregamos amanhã. Quer comprar?", "informacao_comercial"),   # revisão do Codex
    ("Aproveite a promoção de violões desta semana!", "promocional"),               # RI-15
    (" ".join(["palavra"] * 61), "longo_demais"),
    ("Quer ver? Ou prefere outro?", "mais_de_uma_pergunta"),
    ("", "vazio"),
])
def test_ci05_lembrete_recusado(texto, problema):
    assert any(p.startswith(problema) for p in politica.conferir_lembrete(texto, []))


def test_ci05_lembrete_repetido_e_bom():
    assert politica.conferir_lembrete("Ficou alguma dúvida?", ["ficou alguma duvida"]) == ["repetido"]
    assert politica.conferir_lembrete("Ficou alguma dúvida sobre os violões que te mostrei?", []) == []


def test_ci05_lembrete_com_valor_nao_e_enviado():
    llm = FakeLLMClient([decisao(acao="ENVIAR", mensagem="O Yamaha C40 sai por R$ 599,90!")])
    ret = Retencao(llm, CFG)
    ac, hist = ac_novo(), list(HIST)
    av = ret.avaliar(ac, hist, T0 + timedelta(minutes=30))
    assert av.acao == "ESPERAR" and "contem_valor" in av.motivo
    assert ac.lembretes == [] and len(hist) == 2


# ---------------------------------------------------------------- decisão (RI-10)

def test_enviar_registra_no_historico_e_reagenda():
    llm = FakeLLMClient([decisao(acao="ENVIAR", mensagem="Ficou alguma dúvida sobre os violões que te mostrei?")])
    ret = Retencao(llm, CFG)
    ac, hist = ac_novo(), list(HIST)
    av = ret.avaliar(ac, hist, T0 + timedelta(minutes=30))
    assert av.acao == "ENVIAR" and ac.status == Status.LEMBRETE
    assert hist[-1] == {"role": "assistant", "content": "Ficou alguma dúvida sobre os violões que te mostrei?"}
    assert ac.proxima_avaliacao == T0 + timedelta(hours=4)
    contexto = json.loads(llm.chamadas[0]["mensagens"][1]["content"])
    assert contexto["minutos_de_silencio"] == 30 and contexto["conversa_recente"][-1]["de"] == "Lia"
    assert llm.chamadas[0]["tools"] == []                    # lembrete não consulta tools


def test_infinity_e_nan_viram_sem_sugestao():
    ret = Retencao(FakeLLMClient([decisao(acao="ESPERAR", proxima_avaliacao_min="Infinity")]), CFG)
    av = ret.avaliar(ac_novo(), list(HIST), T0 + timedelta(minutes=30))
    assert av.acao == "ESPERAR"


def test_ci06_saida_invalida_vira_esperar():
    ret = Retencao(FakeLLMClient([responder("vou mandar um oi pro cliente!")]), CFG)
    ac = ac_novo()
    av = ret.avaliar(ac, list(HIST), T0 + timedelta(minutes=30))
    assert av.acao == "ESPERAR" and av.motivo.startswith("saida_invalida_do_modelo") and ac.lembretes == []


def test_resposta_vazia_e_pedida_de_novo():
    llm = FakeLLMClient([responder(""), decisao(acao="ENVIAR", mensagem="Ficou alguma dúvida sobre os violões?")])
    ret = Retencao(llm, CFG)
    av = ret.avaliar(ac_novo(), list(HIST), T0 + timedelta(minutes=30))
    assert av.acao == "ENVIAR" and len(llm.chamadas) == 2


def test_sugestao_fora_do_intervalo_nao_invalida():
    ret = Retencao(FakeLLMClient([decisao(acao="esperar", proxima_avaliacao_min=5000)]), CFG)
    ac = ac_novo()
    av = ret.avaliar(ac, list(HIST), T0 + timedelta(minutes=30))
    assert av.acao == "ESPERAR" and ac.proxima_avaliacao == politica.limite_envio(ac, CFG)


def test_esperar_respeita_sugestao_dentro_dos_limites():
    ret = Retencao(FakeLLMClient([decisao(acao="ESPERAR", proxima_avaliacao_min=120)]), CFG)
    ac = ac_novo()
    ret.avaliar(ac, list(HIST), T0 + timedelta(minutes=30))
    assert ac.status == Status.AGUARDANDO and ac.proxima_avaliacao == T0 + timedelta(minutes=150)


def test_parar_encerra():
    ret = Retencao(FakeLLMClient([decisao(acao="PARAR")]), CFG)
    ac = ac_novo()
    ret.avaliar(ac, list(HIST), T0 + timedelta(minutes=30))
    assert ac.status == Status.ENCERRADO and ac.proxima_avaliacao is None


def test_ci07_teto_de_lembretes_pela_agenda_natural():
    cfg = ConfigRetencao(ativa=True, avaliacoes_min=(30, 60, 90, 120))
    msgs = ["Ficou alguma dúvida sobre os violões?", "Quer que eu compare dois modelos?", "Sigo por aqui se precisar."]
    llm = FakeLLMClient([decisao(acao="ENVIAR", mensagem=m) for m in msgs])
    ret = Retencao(llm, cfg)
    ac = Acompanhamento(ultima_msg_cliente=T0, ultima_msg_auto=T0)
    politica.agendar(ac, cfg, T0)
    acoes = []
    for _ in range(4):                                       # sem mexer na agenda: segue ac.proxima_avaliacao
        acoes.append(ret.avaliar(ac, list(HIST), ac.proxima_avaliacao))
    assert [a.acao for a in acoes] == ["ENVIAR", "ENVIAR", "ENVIAR", "BLOQUEADO"]
    assert acoes[-1].motivo == "teto_de_lembretes" and ac.status == Status.ENCERRADO
    assert len(llm.chamadas) == 3                            # o teto não gasta uma chamada ao modelo


def test_ultima_tentativa_e_terminal_para_envios():
    ret = Retencao(FakeLLMClient([decisao(acao="ENVIAR", mensagem="Sigo por aqui se precisar de algo.")]), CFG)
    ac = Acompanhamento(ultima_msg_cliente=T0, ultima_msg_auto=T0)
    ac.proxima_avaliacao = datetime(2026, 3, 26, 8, 0, tzinfo=FUSO)          # faltam 2 h para as 24 h
    assert ret.avaliar(ac, list(HIST), ac.proxima_avaliacao).acao == "ENVIAR"
    assert ac.status == Status.ULTIMA and ac.proxima_avaliacao == politica.limite_envio(ac, CFG)
    av = ret.avaliar(ac, list(HIST), ac.proxima_avaliacao)
    assert av.motivo == "janela_fechada" and ac.status == Status.JANELA_FECHADA


def test_ultima_tentativa_conta_da_expiracao_real():
    ac = Acompanhamento(ultima_msg_cliente=T0)
    assert not politica.ultima_tentativa(ac, CFG, T0 + timedelta(hours=19, minutes=30))   # antes: já contava
    assert politica.ultima_tentativa(ac, CFG, T0 + timedelta(hours=20))


def test_relogio_relido_antes_do_envio():
    from emporio.rules.horario import RelogioAjustavel, relogio_fixo
    rel = RelogioAjustavel(relogio_fixo(datetime(2026, 3, 25, 20, 59, tzinfo=FUSO)))

    def modelo_lento(_mensagens):
        rel.avancar(timedelta(minutes=2))                    # a resposta chega às 21h01 (horário silencioso)
        return decisao(acao="ENVIAR", mensagem="Ficou alguma dúvida sobre os violões?")

    ret = Retencao(FakeLLMClient([modelo_lento]), CFG, rel)
    ac = Acompanhamento(ultima_msg_cliente=datetime(2026, 3, 25, 20, 0, tzinfo=FUSO),
                        ultima_msg_auto=datetime(2026, 3, 25, 20, 0, tzinfo=FUSO))
    ac.proxima_avaliacao = rel()
    av = ret.avaliar(ac, list(HIST), rel())
    assert av.acao == "BLOQUEADO" and av.motivo == "horario_silencioso" and ac.lembretes == []


def test_config_invalida_e_limite_absoluto():
    with pytest.raises(ValueError, match="margem_envio_min"):
        ConfigRetencao(margem_envio_min=-120)
    with pytest.raises(ValueError, match="avaliacoes_min"):
        ConfigRetencao(avaliacoes_min=(30, 2000))
    ac = Acompanhamento(ultima_msg_cliente=T0)
    assert politica.bloqueio(ac, ConfigRetencao(margem_envio_min=0), T0 + timedelta(hours=24)).motivo == "janela_fechada"


def test_motivo_e_contexto_mascarados():
    llm = FakeLLMClient([decisao(acao="ESPERAR", motivo="cliente deu o fixo 33424567 e anacarol.ferreira@coldmail.com")])
    ret = Retencao(llm, CFG)
    hist = [{"role": "user", "content": "meu fixo é 33424567"}, {"role": "assistant", "content": "Anotado!"}]
    av = ret.avaliar(ac_novo(), hist, T0 + timedelta(minutes=30))
    assert "33424567" not in av.motivo and "anacarol" not in av.motivo
    assert "33424567" not in llm.chamadas[0]["mensagens"][1]["content"]


def test_cliente_responde_e_o_ciclo_recomeca():
    ret = Retencao(FakeLLMClient([decisao(acao="ENVIAR", mensagem="Ficou alguma dúvida?")]), CFG)
    ac = ac_novo()
    ret.avaliar(ac, list(HIST), T0 + timedelta(minutes=30))
    ret.ao_receber(ac, "oi, voltei", T0 + timedelta(hours=1))
    assert ac.status == Status.ATIVO and ac.lembretes == [] and ac.avaliacoes == 0
    assert ac.proxima_avaliacao == T0 + timedelta(hours=1, minutes=30)


def test_desligada_nao_agenda_nem_avalia():
    ret = Retencao(FakeLLMClient([]), ConfigRetencao(ativa=False))
    ac = Acompanhamento()
    ret.ao_receber(ac, "oi", T0)
    assert ac.proxima_avaliacao is None and ac.ultima_msg_cliente == T0
    assert ret.avaliar(ac, list(HIST), T0 + timedelta(hours=1)) is None


def test_equipe_assumiu_encerra():
    ret = Retencao(FakeLLMClient([]), CFG)
    ac = ac_novo()
    ret.ao_responder(ac, T0, equipe_assumiu=True)
    assert ac.status == Status.ENCERRADO and ac.motivo == "encaminhado_equipe"
