# SPEC-007: Atendimento humano no painel (conversas, assumir e devolver)

- **Status:** concluída
- **Data:** 2026-11-01
- **Autor:** Alberto Milet
- **Origem:** pergunta do usuário em 01/11/2026 ("onde o vendedor tem acesso às conversas?") e o pedido seguinte: fazer o sistema com essas funcionalidades e transformar a tela "Atendimento com a Lia" numa aba "Simulador de WhatsApp", como no projeto ALJ.

---

## 1. Problema

O vendedor recebia o alerta com um código de conversa, mas não tinha onde ler a conversa nem como responder. As conversas ficavam na memória do servidor e se perdiam a cada reinício.

## 2. Solução

Duas abas:

| Aba | Quem usa | O que faz |
|---|---|---|
| **Atendimento** (`/atendimento`) | a loja | lista as conversas (as que pediram vendedor primeiro) e os alertas recentes; abre o histórico completo; **Assumir conversa** pausa a Lia e libera a resposta do vendedor; **Devolver à Lia** retoma o atendimento automático |
| **Simulador de WhatsApp** (`/simulador`) | quem testa | você é o cliente, identificado pelo telefone; vê as respostas da Lia e do vendedor; tem roteiro de perguntas e chegada por canal |

O histórico fica em SQLite (`logs/atendimento.db`, fora do git; `EMPORIO_DB` muda o caminho).

## 3. Regras

| # | Regra |
|---|---|
| RH-01 | O telefone do cliente nunca é gravado em claro: a conversa é achada pelo hash SHA-256 do número e mostrada mascarada |
| RH-02 | Todo texto é gravado mascarado (telefone e e-mail), seja do cliente, da Lia ou do vendedor (RN-09, RN-24) |
| RH-03 | Com a conversa assumida, a Lia não responde; a mensagem do cliente vai para o histórico e para o contexto do agente |
| RH-04 | Ao devolver, a Lia recebe as falas do vendedor no contexto, marcadas como "[Vendedor da loja]" |
| RH-05 | Responder como vendedor exige assumir antes (sem isso, 409) |
| RH-06 | Abrir o simulador não cria conversa; ela nasce na primeira mensagem |
| RH-07 | Os alertas vão para o histórico da conversa e aparecem só no painel da loja; o cliente não os vê |
| RH-08 | Depois de reiniciar, o contexto do agente é recriado do histórico; o pedido verificado não volta (o cliente verifica de novo) |

## 4. Critérios de aceite

- [x] **CH-01** Uma mensagem no simulador cria a conversa, que aparece no painel com o telefone mascarado.
- [x] **CH-02** Depois de assumir, a resposta do vendedor aparece no simulador e a Lia não responde; depois de devolver, a Lia volta a responder.
- [x] **CH-03** Pedido de vendedor marca a conversa como "pediu vendedor", com alerta e origem do lead no painel.
- [x] **CH-04** O histórico sobrevive a um reinício, e o banco não tem o telefone do cliente nem o telefone digitado em claro.
- [x] **CH-05** Telefones diferentes no simulador geram conversas diferentes.

## 5. Limitações

- **Sem login:** qualquer um com acesso à porta abre o painel. O servidor escuta só em 127.0.0.1 por padrão; em produção, o painel precisaria de autenticação.
- **Um processo:** a trava de turno e o estado do agente em memória valem para um servidor só.
- **O canal ainda é simulado:** o webhook real do WhatsApp (SPEC-004) entraria no lugar do simulador, chamando a mesma função que recebe a mensagem do cliente.
