# SPEC-013: Segurança do painel e do agente

- **Status:** concluída
- **Data:** 2026-11-02
- **Autor:** Alberto Milet
- **Origem:** avaliação de segurança feita em 02/11/2026 (Claude Code, nota 7,5) e a do Codex (7,0), e o pedido do usuário para implementar as prioridades combinadas.

---

## 1. Problema

O núcleo estava bem protegido: as tools autorizam os pedidos em código, a senha é guardada só como PBKDF2, o texto é escapado, o token da Meta é cifrado e o ZDR é obrigatório. As duas avaliações encontraram falhas no servidor web e na operação:

1. O login de demonstração (`demo` / `demo1234`, mostrado na tela) usava o banco real de conversas.
2. A proteção contra CSRF dependia só do `SameSite=Lax`, que não separa portas: outro serviço em `localhost` podia enviar formulários com o cookie do painel.
3. Com `--host 0.0.0.0`, o painel rodava em HTTP puro; os scripts vinham de CDN sem SRI; não havia cabeçalhos de segurança.
4. "Sair" e trocar a senha não revogavam o cookie de sessão, válido por 12 h.
5. Não havia limite de mensagens por conversa (custo do LLM) nem de tentativas de verificação de pedido, e o tempo de resposta do login revelava quais usuários existem.
6. Telefone com pontos (`67.91234.5678`) escapava da máscara, e a auditoria de leitura podia ser pulada com o cabeçalho `HX-Request`.

## 2. Solução

| # | O que muda |
|---|---|
| 1 | O modo demonstração usa um banco próprio (`logs/demo.db`), e o login de demonstração só vale com o servidor neste computador (loopback) |
| 2 | Token CSRF por sessão em todo POST autenticado (campo `csrf` ou cabeçalho `X-CSRF-Token`) e conferência de `Origin` em todo POST, inclusive o login |
| 3 | Fora do loopback, o servidor só sobe com `--https-proxy` (TLS num proxy na frente) e o cookie passa a ser sempre `Secure`. Bootstrap e HTMX servidos localmente. Cabeçalhos: CSP com nonce, `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy` e `Cache-Control: no-store` |
| 4 | Cada sessão tem um identificador; "Sair" o revoga (lista guardada no SQLite), e a sessão traz a impressão do hash da senha, então trocar a senha derruba as sessões |
| 5 | Limite de 10 mensagens por minuto e 200 por dia por conversa (acima disso, resposta fixa sem chamar o LLM); 5 tentativas de verificação de pedido por sessão; PBKDF2 contra um hash falso para usuário inexistente; limite de tentativas de login também por usuário |
| 6 | Máscara cobre telefone com pontos e espaços; a auditoria de leitura deduplica no servidor (uma por usuário e conversa a cada 5 min), sem depender de cabeçalho |

## 3. Escopo

### Faz parte

- [x] Itens 1 a 6 acima, com testes
- [x] Cookie de `state` do OAuth no painel com `Secure` sob HTTPS
- [x] `logs/.chave_telefone` criada com permissão restrita; dicionário de clientes simulados com tamanho máximo

### **Não** faz parte

| Item | Por quê |
|---|---|
| Confirmação de posse do contato por código (OTP) na verificação do pedido | Exige canal de envio de código; continua bloqueio para produção (SPEC-012) |
| Perfis de acesso (atendente e administrador) | Exige modelo de papéis; a auditoria cobre a rastreabilidade por enquanto |
| Trava global de um turno por vez no painel | Mudar para execução por conversa é refatoração maior; o limite por conversa reduz o abuso |
| Auditoria de dependências (pip-audit) | Exige baixar a ferramenta; fica como passo de CI |

## 4. Regras

| # | Regra |
|---|---|
| RS-01 | Sem usuários configurados e com o modelo de demonstração, o painel usa `EMPORIO_DB_DEMO` (padrão `logs/demo.db`), nunca o banco real |
| RS-02 | O login de demonstração e qualquer endereço fora do loopback sem `--https-proxy` fazem o comando `ui` recusar a inicialização |
| RS-03 | Todo POST com sessão exige token CSRF igual ao HMAC do identificador da sessão; todo POST com `Origin` de outra origem (ou `null`) é recusado com 403 |
| RS-04 | A sessão leva identificador aleatório e impressão do hash da senha; revogada ou com senha trocada, deixa de valer |
| RS-05 | Mais de 10 mensagens em 60 s ou de 200 em 24 h na mesma conversa: a mensagem é guardada, o LLM não é chamado e o cliente recebe uma resposta fixa com o contato da loja |
| RS-06 | Na mesma sessão, depois de 5 verificações de pedido que não conferem, `consultar_pedido` recusa novas tentativas por verificação; os pedidos do dono do número do WhatsApp continuam acessíveis |
| RS-07 | Login com usuário inexistente gasta o mesmo PBKDF2 que um existente; o bloqueio por tentativas vale por endereço e por usuário |
| RS-08 | A auditoria de leitura registra no máximo um "abriu" por usuário e conversa a cada 5 minutos, em qualquer rota que mostre o histórico |

## 5. Critérios de aceite

- [x] **CS-01** Em modo demonstração, conversas vão para o banco de demonstração; o banco real não é tocado.
- [x] **CS-02** POST autenticado sem token, ou com `Origin: http://localhost:3000`, recebe 403.
- [x] **CS-03** As respostas trazem CSP com nonce, `X-Frame-Options: DENY` e `nosniff`; as páginas não carregam nada de fora.
- [x] **CS-04** Depois de "Sair", o mesmo cookie não abre o painel; depois de trocar a senha também não.
- [x] **CS-05** A 11ª mensagem em um minuto recebe a resposta fixa sem chamar o LLM.
- [x] **CS-06** A 6ª verificação errada de pedido na sessão é recusada, mesmo com o telefone certo.
- [x] **CS-07** `67.91234.5678` sai mascarado.

## 6. Limitações

- A lista de sessões revogadas e os contadores de limite ficam neste processo e no SQLite local; com vários servidores, precisariam de um armazenamento comum.
- A CSP mantém `style-src 'unsafe-inline'` por causa de estilos inline do Bootstrap e do HTMX.
