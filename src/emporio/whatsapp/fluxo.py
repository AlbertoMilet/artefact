"""Etapas da conexão do WhatsApp da loja, retomáveis (SPEC-004 §4.1).

Cada método confere a etapa atual, chama o provedor (real ou simulado), avança e salva. Erro da Meta não
avança a etapa (RW-07). O token fica em memória durante o comando e, se houver chave, cifrado no arquivo.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from emporio.whatsapp import conexao as arq
from emporio.whatsapp import regras
from emporio.whatsapp.conexao import Conexao, Etapa, SemChaveDeCifra
from emporio.whatsapp.meta import ErroMeta, Numero, ProvedorMeta, Token


class EtapaInvalida(RuntimeError):
    pass


class Onboarding:
    def __init__(self, provedor: ProvedorMeta, conexao: Conexao | None = None,
                 agora: Callable[[], datetime] = datetime.now, salvar: bool = True):
        self.p = provedor
        self.c = conexao or arq.carregar()
        self.agora = agora
        self.salvar_em_disco = salvar
        self.token: Token | None = None
        self.avisos: list[str] = []

    # ---------------------------------------------------------------- utilidades
    def _salvar(self) -> None:
        if self.salvar_em_disco:
            arq.salvar(self.c)

    def _exigir(self, minima: Etapa, maxima: Etapa | None = None) -> None:
        if not self.c.chegou(minima) or (maxima is not None and self.c.chegou(maxima) and self.c.etapa != maxima):
            raise EtapaInvalida(f"etapa atual: {self.c.etapa.value}; próxima ação: {self.proxima_acao()}")

    def _token(self) -> Token:
        if self.token:
            return self.token
        if self.c.token_cifrado:
            try:
                return Token(arq.decifrar(self.c.token_cifrado))
            except SemChaveDeCifra:
                pass
            except Exception:
                self.avisos.append("o token salvo não pôde ser decifrado (chave trocada?)")
        raise EtapaInvalida("sem token da Meta nesta sessão: faça o login com Facebook de novo")

    def proxima_acao(self) -> str:
        return {
            Etapa.NAO_CONECTADO: "fazer login com Facebook",
            Etapa.AUTENTICADO: "escolher ou cadastrar o número da loja",
            Etapa.NUMERO_ESCOLHIDO: "enviar o código por SMS",
            Etapa.CODIGO_ENVIADO: "digitar o código recebido por SMS",
            Etapa.VERIFICADO: "registrar o número com o PIN de 6 dígitos",
            Etapa.REGISTRADO: "assinar os webhooks",
            Etapa.CONECTADO: "nada: o WhatsApp da loja está conectado",
        }[self.c.etapa]

    # ---------------------------------------------------------------- 1. login com Facebook
    def autenticar(self, code: str, state_recebido: str | None, state_esperado: str, waba_id: str | None = None) -> list[str]:
        if not regras.state_confere(state_esperado, state_recebido):          # RW-01
            raise EtapaInvalida("retorno do login recusado: state diferente do enviado (possível CSRF)")
        token = self.p.longa_duracao(self.p.trocar_codigo(code))
        info = self.p.validar(token)
        app_id = getattr(self.p, "app_id", None)
        if not info["valido"] or (app_id and info["app_id"] != str(app_id)):  # RW-02
            raise EtapaInvalida("token inválido ou de outro app da Meta")
        faltando = regras.escopos_faltando(info["escopos"])
        if faltando:
            raise EtapaInvalida(f"faltam permissões no login: {', '.join(faltando)}")
        if not info["wabas"]:
            raise EtapaInvalida("nenhuma conta do WhatsApp Business foi autorizada no login")
        self.token = token
        retomando = self.c.chegou(Etapa.AUTENTICADO) and self.c.waba_id in info["wabas"]
        if not retomando:
            self.c.waba_id = waba_id if waba_id in info["wabas"] else info["wabas"][0]
        if token.expira_em_s:
            self.c.token_expira_em = (self.agora() + timedelta(seconds=token.expira_em_s)).isoformat()
        try:
            self.c.token_cifrado = arq.cifrar(token.valor)                    # RW-06
        except SemChaveDeCifra as e:
            self.c.token_cifrado = None
            self.avisos.append(f"token não salvo: {e}")
        if retomando:      # login refeito no meio do caminho: renova o token sem perder a etapa (CW-06)
            self.c.historico.append(f"{self.agora():%d/%m %H:%M} token renovado em {self.c.etapa.value}")
        else:
            self.c.avancar(Etapa.AUTENTICADO, self.agora(), f"WABA {self.c.waba_id}")
        self._salvar()
        return info["wabas"]

    def precisa_login(self) -> bool:
        if self.c.etapa == Etapa.NAO_CONECTADO:
            return True
        if self.c.etapa == Etapa.CONECTADO:
            return False
        try:
            self._token()
            return False
        except EtapaInvalida:
            return True

    # ---------------------------------------------------------------- 2. número
    def numeros(self) -> list[Numero]:
        self._exigir(Etapa.AUTENTICADO)
        return self.p.listar_numeros(self._token(), self.c.waba_id)

    def escolher_numero(self, numero: Numero) -> None:
        self._exigir(Etapa.AUTENTICADO)
        self.c.phone_number_id, self.c.numero_exibicao, self.c.nome_verificado = numero.id, numero.exibicao, numero.nome_verificado
        self.c.tentativas_codigo, self.c.codigo_pedido_em = 0, None
        if numero.status == "CONNECTED":
            self.c.avancar(Etapa.REGISTRADO, self.agora(), f"{numero.exibicao} já ativo na Cloud API")
        elif numero.verificacao == "VERIFIED":
            self.c.avancar(Etapa.VERIFICADO, self.agora(), f"{numero.exibicao} já verificado")
        else:
            self.c.avancar(Etapa.NUMERO_ESCOLHIDO, self.agora(), numero.exibicao)
        self._salvar()

    def cadastrar_numero(self, texto: str, nome_exibicao: str) -> Numero:
        self._exigir(Etapa.AUTENTICADO)
        cc, numero = regras.normalizar_numero_br(texto)                      # RW-03
        if not nome_exibicao.strip():
            raise ValueError("informe o nome de exibição do negócio (ex.: Empório da Música)")
        novo_id = self.p.cadastrar_numero(self._token(), self.c.waba_id, cc, numero, nome_exibicao.strip())
        n = Numero(novo_id, f"+{cc} {numero}", nome_exibicao.strip(), "NOT_VERIFIED", "PENDING")
        self.escolher_numero(n)
        return n

    # ---------------------------------------------------------------- 3. código por SMS
    def pedir_codigo(self, metodo: str = "SMS") -> None:
        if self.c.etapa not in (Etapa.NUMERO_ESCOLHIDO, Etapa.CODIGO_ENVIADO):
            raise EtapaInvalida(f"etapa atual: {self.c.etapa.value}; próxima ação: {self.proxima_acao()}")
        ultimo = datetime.fromisoformat(self.c.codigo_pedido_em) if self.c.codigo_pedido_em else None
        pode, espera = regras.pode_pedir_codigo(ultimo, self.agora())          # RW-04
        if not pode:
            raise EtapaInvalida(f"aguarde {espera} s para pedir outro código")
        self.p.pedir_codigo(self._token(), self.c.phone_number_id, metodo.upper(), "pt_BR")
        self.c.codigo_pedido_em, self.c.tentativas_codigo = self.agora().isoformat(), 0
        self.c.avancar(Etapa.CODIGO_ENVIADO, self.agora(), f"código por {metodo.upper()}")
        self._salvar()

    def confirmar_codigo(self, codigo: str) -> None:
        self._exigir(Etapa.CODIGO_ENVIADO, Etapa.CODIGO_ENVIADO)
        codigo = regras.validar_codigo(codigo)
        if self.c.tentativas_codigo >= regras.TENTATIVAS_POR_CODIGO:
            raise EtapaInvalida("tentativas esgotadas para este código: peça outro")
        try:
            self.p.confirmar_codigo(self._token(), self.c.phone_number_id, codigo)
        except ErroMeta:
            self.c.tentativas_codigo += 1
            self._salvar()
            raise
        self.c.avancar(Etapa.VERIFICADO, self.agora(), "código confirmado")
        self._salvar()

    # ---------------------------------------------------------------- 4. registro e webhooks
    def registrar(self, pin: str) -> None:
        self._exigir(Etapa.VERIFICADO, Etapa.VERIFICADO)
        self.p.registrar(self._token(), self.c.phone_number_id, regras.validar_pin(pin))    # RW-05: não salva
        self.c.avancar(Etapa.REGISTRADO, self.agora(), "número ativo na Cloud API")
        self._salvar()

    def assinar_webhooks(self) -> None:
        self._exigir(Etapa.REGISTRADO, Etapa.REGISTRADO)
        self.p.assinar_webhooks(self._token(), self.c.waba_id)
        self.c.avancar(Etapa.CONECTADO, self.agora(), "webhooks assinados")
        self._salvar()
