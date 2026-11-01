"""Servidor local que recebe o retorno do login com Facebook (redirect_uri http://localhost:8765/callback).

Atende uma única requisição, devolve uma página simples ao navegador e entrega (code, state) ao CLI.
O endereço de retorno precisa estar cadastrado em "URIs de redirecionamento do OAuth válidos" no app da Meta.
"""

from __future__ import annotations

import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

PAGINA = ("<html><body style='font-family:sans-serif'><h2>Empório da Música</h2>"
          "<p>{msg}</p><p>Pode fechar esta aba e voltar ao terminal.</p></body></html>")


def aguardar_retorno(url_login: str, redirect_uri: str, timeout_s: int = 300, abrir: bool = True) -> tuple[str | None, str | None, str | None]:
    """Abre o navegador no login e espera o retorno. Devolve (code, state, erro)."""
    alvo = urlparse(redirect_uri)
    resultado: dict = {}

    class Retorno(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urlparse(self.path)
            if q.path != alvo.path:
                self.send_response(404)
                self.end_headers()
                return
            p = {k: v[0] for k, v in parse_qs(q.query).items()}
            resultado.update(code=p.get("code"), state=p.get("state"),
                             erro=p.get("error_description") or p.get("error"))
            msg = "Login concluído." if p.get("code") else f"Login não concluído: {resultado['erro']}"
            corpo = PAGINA.format(msg=msg).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *args):     # sem log do servidor no terminal (a URL traz o code)
            pass

    servidor = HTTPServer((alvo.hostname or "localhost", alvo.port or 80), Retorno)
    servidor.timeout = timeout_s
    if abrir:
        webbrowser.open(url_login)
    servidor.handle_request()
    servidor.server_close()
    return resultado.get("code"), resultado.get("state"), resultado.get("erro") or (None if resultado else "tempo esgotado")
