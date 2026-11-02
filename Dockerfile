# Empório da Música: painel de atendimento (FastAPI) para o Easypanel ou qualquer host com Docker.
# Guia: docs/deploy-easypanel.md. Segredos só por variável de ambiente, nunca na imagem.
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

RUN pip install --no-cache-dir uv==0.7.3

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependências primeiro (camada reaproveitada enquanto o uv.lock não muda)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Código e dados da loja. Instalação editável: o app acha data/ a partir de /app.
COPY src ./src
COPY data ./data
RUN uv sync --frozen --no-dev

# Tudo o que o app grava fica no volume /data: histórico, chave do HMAC, preferências, registros e logs.
ENV PATH=/app/.venv/bin:$PATH \
    EMPORIO_DB=/data/atendimento.db \
    EMPORIO_DB_DEMO=/data/demo.db \
    EMPORIO_PREFERENCIAS=/data/emporio.json \
    TICKETS_PATH=/data/tickets.jsonl \
    ALERTAS_FILA=/data/alertas.jsonl \
    EMPORIO_LOG_TURNOS=/data/emporio.jsonl \
    EMPORIO_LOG_AVISOS=/data/avisos.log \
    WHATSAPP_CONEXAO=/data/whatsapp.json \
    ALERTA_SONORO=false \
    EMPORIO_PROXY_IPS=*

RUN useradd --system --uid 10001 --home-dir /data emporio \
    && mkdir -p /data && chown emporio /data
USER emporio
VOLUME ["/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/login', timeout=4).status == 200 else 1)"

# --https-proxy: o HTTPS fica no proxy do Easypanel (Traefik); os cookies saem sempre com Secure (SPEC-013).
CMD ["python", "-m", "emporio", "ui", "--host", "0.0.0.0", "--porta", "8000", "--https-proxy", "--sem-navegador"]
