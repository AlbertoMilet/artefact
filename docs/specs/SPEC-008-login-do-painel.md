# SPEC-008: Login do painel com usuários no .env

- **Status:** concluída
- **Data:** 2026-11-01
- **Autor:** Alberto Milet
- **Origem:** pedido do usuário em 01/11/2026: "crie login, colocar os usuários em .env". Fecha a limitação "sem login" da SPEC-007.

---

## 1. Solução

Todo o painel (Atendimento e Simulador de WhatsApp) exige login; só `/login` e os arquivos estáticos ficam abertos.

```env
EMPORIO_USUARIOS=carlos:pbkdf2_sha256$600000$<sal>$<hash>,ana:pbkdf2_sha256$600000$<sal>$<hash>
EMPORIO_SEGREDO_SESSAO=<64 caracteres hex>
```

- `uv run python -m emporio usuario criar carlos`: pede a senha duas vezes, sem mostrar, e imprime a linha `nome:hash`.
- `uv run python -m emporio usuario segredo`: gera o segredo que assina o cookie da sessão.
- `uv run python -m emporio usuario listar`: mostra os nomes configurados, sem os hashes.

## 2. Regras

| # | Regra |
|---|---|
| RL-01 | A senha nunca vai para o .env nem para o código: só o hash PBKDF2-SHA256, 600 mil iterações e sal aleatório de 16 bytes. Uma entrada sem hash (senha em claro) impede a inicialização |
| RL-02 | Sessão em cookie `HttpOnly`, `SameSite=Lax` (e `Secure` em HTTPS), assinada com HMAC-SHA256 e válida por 12 h |
| RL-03 | Sem `EMPORIO_SEGREDO_SESSAO`, o segredo é aleatório a cada início: funciona, mas as sessões caem ao reiniciar (aviso no terminal) |
| RL-04 | Usuário removido do .env perde o acesso, mesmo com uma sessão ainda válida |
| RL-05 | Depois de 5 senhas erradas seguidas do mesmo endereço, 60 s de espera. A mensagem não diz se o usuário existe |
| RL-06 | Depois do login, só volta para caminhos internos (`/...`); `//site` é recusado (redirecionamento aberto) |
| RL-07 | Assumir, devolver e responder registram o usuário, que aparece só no painel da loja |
| RL-08 | Sem usuários no .env, o modo demonstração (`--fake`) aceita `demo` / `demo1234`, mostrado na tela de login. Com o modelo real e sem usuários, ninguém entra até configurar um |

## 3. Critérios de aceite

- [x] **CL-01** Sem login, toda página do painel leva a `/login`; pedidos do HTMX recebem 401 com `HX-Redirect`.
- [x] **CL-02** Login certo volta para a página pedida; "Sair" encerra a sessão.
- [x] **CL-03** Senha errada não entra; a sexta tentativa seguida é bloqueada.
- [x] **CL-04** Cookie adulterado, de outro segredo ou vencido não vale.
- [x] **CL-05** `usuario criar` gera um hash que confere com a senha digitada e não contém a senha.

## 4. Limitações

- Sem papéis (todo usuário é vendedor) e sem troca de senha pela tela: muda-se o .env e reinicia.
- O limite de tentativas fica em memória (um processo).
- Proteção contra CSRF vem do `SameSite=Lax`; um painel exposto na internet pediria token de formulário e HTTPS.
