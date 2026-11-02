# Deploy no Easypanel

O painel de atendimento (FastAPI) sobe a partir do `Dockerfile` da raiz. O Easypanel constrói a imagem, cuida do HTTPS (Traefik) e guarda os dados num volume. O WhatsApp real **não** é conectado: o atendimento acontece pelo Simulador do painel (SPEC-004 e SPEC-014).

## 1. Antes de começar

- O repositório precisa estar no GitHub (o Easypanel puxa de lá) ou você envia a imagem para um registro.
- Gere os valores secretos **no seu computador**, na raiz do projeto:

```bash
uv run python -m emporio usuario criar seu_nome      # pede a senha; imprime EMPORIO_USUARIOS=seu_nome:pbkdf2_sha256$...
uv run python -m emporio usuario segredo             # imprime EMPORIO_SEGREDO_SESSAO=...
uv run python -c "import secrets; print(secrets.token_hex(32))"   # valor para EMPORIO_CHAVE_TELEFONE
```

Guarde esses valores só no Easypanel. Nada disso vai para o git.

## 2. Criar o serviço

1. **Projeto → + Service → App.** Dê um nome (por exemplo, `emporio`).
2. **Source:** GitHub, repositório do projeto, branch `main`.
3. **Build:** Dockerfile, caminho `Dockerfile`. A imagem usa Python 3.12 e instala as dependências travadas do `uv.lock`.
4. **Mounts → Volume:** nome `emporio-dados`, caminho de montagem **`/data`**. Tudo o que o app grava fica lá: histórico (SQLite), chave do HMAC, preferências, registros e logs.
5. **Domains:** adicione o domínio e aponte para a **porta 8000** do contêiner. O HTTPS é automático.

## 3. Variáveis de ambiente (aba Environment)

| Variável | Obrigatória | Valor |
|---|---|---|
| `OPENROUTER_API_KEY` | sim | chave do OpenRouter (toda chamada usa Zero Data Retention) |
| `EMPORIO_USUARIOS` | sim | a linha gerada por `usuario criar` (vários usuários separados por vírgula) |
| `EMPORIO_SEGREDO_SESSAO` | sim | gerado por `usuario segredo`; sem ele, as sessões caem a cada deploy |
| `EMPORIO_CHAVE_TELEFONE` | recomendada | chave do HMAC do telefone; sem ela, uma é criada no volume (`/data/.chave_telefone`) |
| `DATA_REFERENCIA` | recomendada para demonstração | `2026-03-25T10:00`: os pedidos dos dados são de out/2025 a mar/2026 |
| `OPENROUTER_MODEL` | não | `deepseek/deepseek-v4.1-flash` (padrão), ou troque depois em Configurações |

O hash da senha tem `$` (`pbkdf2_sha256$600000$...`). Se o app não subir e o log disser `EMPORIO_USUARIOS: entrada inválida`, o Easypanel interpretou o `$`: escreva cada `$` como `$$` e faça o deploy de novo.

Os caminhos dentro de `/data` e a confiança no proxy (`EMPORIO_PROXY_IPS=*`) já vêm definidos no `Dockerfile`.

## 4. Deploy e primeiro acesso

1. Clique em **Deploy**. O build leva alguns minutos; o healthcheck consulta `/login` a cada 30 s.
2. Abra o domínio e entre com o usuário criado no passo 1.
3. No **Simulador de WhatsApp**, mande "Qual o endereço da loja?" para conferir o modelo. Em **Configurações**, troque o modelo e a persona sem reiniciar.

## 5. Como o contêiner se protege (SPEC-012 e 013)

- Sobe com `--https-proxy`: cookies sempre `Secure`, e o servidor recusa subir fora do loopback sem isso.
- Sem `EMPORIO_USUARIOS`, **recusa subir**: o login de demonstração (`demo`/`demo1234`) só vale num computador local.
- Roda sem root (usuário `emporio`), com CSRF, CSP e cabeçalhos de segurança em toda resposta.
- Conversas e logs com mais de 90 dias são apagados ao iniciar e a cada hora com o painel recebendo acessos.

## 6. Operação

- **Atualizar:** commit na `main` e **Deploy** (ou ative o deploy automático no Easypanel).
- **Backup:** faça backup do volume `/data`; é o único estado do app.
- **Logs:** aba Logs do serviço. Erros vão também para `/data/avisos.log`, já mascarados.
- **Custo do LLM:** cada conversa tem limite de 10 mensagens por minuto e 200 por dia (SPEC-013).

## 7. Limitações deste deploy

- O Simulador aceita qualquer telefone e mostra os pedidos do cliente cadastrado com esse número (SPEC-011). Os dados são fictícios; com dados reais, o Simulador teria de ser desligado e a identificação viria do webhook do WhatsApp.
- Um único contêiner: a trava de um turno por vez e os limites ficam neste processo.
- O WhatsApp real exige um webhook HTTPS que o protótipo não tem; a aba de conexão do WhatsApp roda só em modo simulado sem `META_APP_ID`.

## Testar a imagem localmente

```bash
docker build -t emporio-atendimento .
docker run --rm -p 8090:8000 -v emporio-dados:/data \
  -e OPENROUTER_API_KEY=... -e EMPORIO_USUARIOS='seu_nome:pbkdf2_sha256$...' \
  -e EMPORIO_SEGREDO_SESSAO=... emporio-atendimento
```

Abra `http://127.0.0.1:8090`. Localmente o cookie sai `Secure` (por causa do `--https-proxy`) e o Chrome o aceita em `127.0.0.1`. Para testar sem chave, acrescente `-e LLM_PROVIDER=fake`. Se o download da imagem base falhar na sua rede, use `--build-arg PYTHON_IMAGE=python:3.13-slim` com uma imagem que você já tenha.
