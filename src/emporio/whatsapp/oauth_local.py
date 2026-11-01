"""Servidor local que recebe o retorno do login com Facebook (redirect_uri http://localhost:8765/callback).

Revisão do Codex: escuta só em loopback; espera até um retorno VÁLIDO (caminho certo e `state` igual ao
enviado) ou até o prazo, em vez de encerrar na primeira requisição; tempo limite por conexão; HTML escapado.
O endereço de retorno precisa estar cadastrado em "URIs de redirecionamento do OAuth válidos" no app da Meta.
"""

from __future__ import annotations

import html
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from emporio.whatsapp.regras import state_confere, validar_redirect

PAGINA = ("<html><body style='font-family:sans-serif'><h2>Empório da Música</h2>"
          "<p>{msg}</p><p>Pode fechar esta aba e voltar ao terminal.</p></body></html>")


def aguardar_retorno(url_login: str, redirect_uri: str, state_esperado: str | None = None, timeout_s: int = 300,
                     abrir: bool = True) -> tuple[str | None, str | None, str | None]:
    """Abre o navegador no login e espera o retorno. Devolve (code, state, erro)."""
    host, porta, caminho = validar_redirect(redirect_uri)
    resultado: dict = {}

    class Retorno(BaseHTTPRequestHandler):
        timeout = 10                                   # conexão aberta e parada não prende o servidor

        def _responder(self, status: int, msg: str) -> None:
            corpo = PAGINA.format(msg=html.escape(msg)).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def do_GET(self):
            q = urlparse(self.path)
            if q.path != caminho:
                self._responder(404, "Endereço desconhecido.")
                return
            p = {k: v[0] for k, v in parse_qs(q.query).items()}
            if state_esperado is not None and not state_confere(state_esperado, p.get("state")):
                self._responder(400, "Retorno recusado: não corresponde a este login.")
                return
            erro = p.get("error_description") or p.get("error")
            if not p.get("code") and not erro:
                self._responder(400, "Retorno sem código de autorização.")
                return
            resultado.update(code=p.get("code"), state=p.get("state"), erro=erro)
            self._responder(200, "Login concluído." if p.get("code") else f"Login não concluído: {erro}")

        def log_message(self, *args):     # sem log do servidor no terminal (a URL traz o code)
            pass

    servidor = HTTPServer(("127.0.0.1" if host == "localhost" else host, porta), Retorno)
    servidor.timeout = 1
    prazo = time.monotonic() + timeout_s
    try:
        if abrir:
            webbrowser.open(url_login)
        while not resultado and time.monotonic() < prazo:
            servidor.handle_request()
    finally:
        servidor.server_close()
    if not resultado:
        return None, None, "tempo esgotado"
    return resultado.get("code"), resultado.get("state"), resultado.get("erro")
