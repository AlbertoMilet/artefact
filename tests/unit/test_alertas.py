"""Alerta sonoro para o vendedor (SPEC-003): detecção, padrões, duplicidade, fila e vigia."""

import json
from datetime import datetime, timedelta

import pytest

from emporio.agent.agente import EventoTool
from emporio.alertas import PADROES, CentralAlertas, Tocador, pediu_vendedor
from emporio.alertas.central import ler_fila, vigiar
from emporio.rules.horario import FUSO

T0 = datetime(2026, 3, 25, 10, 0, tzinfo=FUSO)


class TocadorFalso(Tocador):
    def __init__(self, ligado=True):
        super().__init__(ligado)
        self.tocados = []

    def tocar(self, tipo):
        if self.ligado:
            self.tocados.append(tipo)
        return self.ligado

    def tocar_e_esperar(self, tipo):
        return self.tocar(tipo)


def registro(tipo="reclamacao", gravado=True, protocolo="SIM-20260325-0001"):
    return EventoTool("registrar_solicitacao", json.dumps({"tipo": tipo, "resumo": "x", "confirmado": True}), "", 1,
                      None, json.dumps({"gravado": gravado, "protocolo_simulado": protocolo if gravado else None}))


@pytest.fixture
def central(tmp_path):
    return CentralAlertas(TocadorFalso(), tmp_path / "alertas.jsonl")


@pytest.mark.parametrize("texto", ["quero falar com um vendedor", "me passa pra um atendente", "atendimento humano",
                                   "não quero falar com robô", "posso falar com o gerente?", "atendente",
                                   "tem algum atendente disponível?"])
def test_detecta_pedido_explicito(texto):
    assert pediu_vendedor(texto)


@pytest.mark.parametrize("texto", ["o vendedor de vocês me indicou este violão", "o atendente da loja foi ótimo",
                                   "quero um violão para uma pessoa iniciante", "vou falar com minha esposa e volto",
                                   "quanto custa o Takamine?"])
def test_ca3_02_nao_dispara_sem_pedido(texto):
    assert not pediu_vendedor(texto)


def test_padroes_iguais_ao_saude_legal():
    assert PADROES["normal"] == [(880.0, 0.0), (1174.7, 0.16)]
    assert [hz for hz, _ in PADROES["vendedor"]] == [784.0, 1046.5, 1318.5] * 2


def test_ca3_01_pedido_explicito_vai_para_a_fila_e_toca(central):
    alertas = central.avaliar_turno("c1", "Quero falar com um vendedor, meu tel é (67) 99654-7821", [], T0)
    central.emitir(alertas)
    assert [a.tipo for a in alertas] == ["pedido_vendedor"]
    assert central.tocador.tocados == ["vendedor"]
    linha = ler_fila(central.fila)[0]
    assert linha["tipo"] == "pedido_vendedor" and linha["conversa"] == "c1"
    assert "99654" not in json.dumps(linha, ensure_ascii=False)                # CA3-07: fila mascarada


def test_ca3_03_encaminhamento_com_protocolo(central):
    alertas = central.avaliar_turno("c1", "pode registrar", [registro("reclamacao")], T0)
    central.emitir(alertas)
    assert alertas[0].tipo == "encaminhamento" and alertas[0].protocolo == "SIM-20260325-0001"
    assert alertas[0].aviso() == "📋 Nova solicitação encaminhada à equipe: reclamação (SIM-20260325-0001)."
    assert central.tocador.tocados == ["normal"]


def test_registro_nao_gravado_nao_alerta(central):
    assert central.avaliar_turno("c1", "x", [registro(gravado=False)], T0) == []


def test_ca3_04_atendimento_humano_depois_do_pedido_nao_toca_de_novo(central):
    central.emitir(central.avaliar_turno("c1", "quero falar com um atendente", [], T0))
    seguinte = central.avaliar_turno("c1", "sim, pode registrar", [registro("atendimento_humano")], T0 + timedelta(minutes=2))
    central.emitir(seguinte)
    assert seguinte[0].tocar is False
    assert central.tocador.tocados == ["vendedor"]
    assert len(ler_fila(central.fila)) == 2                                   # mas vai para a fila


def test_pedido_repetido_em_menos_de_10_min_nao_alerta_de_novo(central):
    central.emitir(central.avaliar_turno("c1", "quero um vendedor", [], T0))
    assert central.avaliar_turno("c1", "cadê o vendedor? quero falar com um vendedor", [], T0 + timedelta(minutes=5)) == []
    assert len(central.avaliar_turno("c1", "quero falar com um vendedor", [], T0 + timedelta(minutes=11))) == 1
    assert len(central.avaliar_turno("c2", "quero falar com um vendedor", [], T0)) == 1   # outra conversa


def test_pedido_e_encaminhamento_no_mesmo_turno_toca_o_padrao_do_pedido(central):
    central.emitir(central.avaliar_turno("c1", "quero falar com um vendedor", [registro("reclamacao")], T0))
    assert central.tocador.tocados == ["vendedor"]


def test_ca3_06_sem_som_aviso_visual_continua(tmp_path):
    avisos = []
    c = CentralAlertas(TocadorFalso(ligado=False), tmp_path / "f.jsonl", avisar=lambda a: avisos.append(a.aviso()))
    c.emitir(c.avaliar_turno("c1", "quero falar com um vendedor", [], T0))
    assert c.tocador.tocados == [] and avisos == ["🙋 Cliente pediu um vendedor: quer falar agora."]


def test_ca3_05_vigia_ignora_antigos_e_toca_uma_vez_por_ciclo(central):
    for i in range(3):
        central.emitir(central.avaliar_turno(f"antiga{i}", "quero falar com um vendedor", [], T0))
    tocador, linhas = TocadorFalso(), []

    def dormir(_):
        if not hasattr(dormir, "feito"):
            dormir.feito = True
            central.emitir(central.avaliar_turno("nova1", "quero falar com um atendente", [], T0))
            central.emitir(central.avaliar_turno("nova2", "pode registrar", [registro("troca", protocolo="SIM-2")], T0))

    avisados = vigiar(central.fila, tocador, linhas.append, intervalo_s=0, ciclos=2, dormir=dormir)
    assert avisados == 2 and tocador.tocados == ["vendedor"]
    texto = "\n".join(linhas)
    assert "3 alerta(s) já existente(s) ignorado(s)" in texto
    assert "Cliente pediu um vendedor" in texto and "troca (SIM-2)" in texto


def test_tocador_real_nao_quebra_sem_dispositivo():
    chamado = []
    t = Tocador(executar=lambda p: (chamado.append(p), (_ for _ in ()).throw(RuntimeError("sem som"))))
    assert t.tocar_e_esperar("vendedor") is True and chamado
