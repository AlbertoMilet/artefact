# SPEC-011: Pedidos do cliente pelo número do WhatsApp

- **Status:** concluída
- **Data:** 2026-11-02
- **Autor:** Alberto Milet
- **Origem:** pedido do usuário em 02/11/2026. O cliente perguntou "qual foi minha última compra?" e a Lia pediu número do pedido e telefone; "o agente devia saber cruzando customers com orders". Decisão do usuário: identificar o cliente pelo **número do WhatsApp do remetente**.

---

## 1. Problema

A SPEC-001 só mostra um pedido com número + telefone ou e-mail (RN-08) e nunca lista pedidos de um cliente (RN-09). Isso protege contra quem digita o telefone de outra pessoa, mas obriga o cliente a lembrar o número do pedido para perguntas simples como "qual foi minha última compra?".

No WhatsApp, o número do remetente não é digitado pelo cliente: vem do canal, que o confirmou por SMS. Ele serve como identificação mais forte que um telefone digitado.

## 2. Solução

O canal entrega o número do remetente junto com cada mensagem. O código procura esse número no cadastro (`customers.csv`) e guarda na sessão só o `customer_id`, nunca o número. Uma tool nova, `meus_pedidos`, cruza o cliente com `orders.csv` e `order_items.csv` e devolve os pedidos dele, do mais recente para o mais antigo. Os pedidos desse cliente também passam a valer em `consultar_pedido` e `verificar_arrependimento` sem pedir telefone ou e-mail.

Quem escreve de um número que não está no cadastro continua no fluxo da SPEC-001: número do pedido + telefone ou e-mail.

## 3. Escopo

### Faz parte

- [x] `cliente_do_telefone(clientes, telefone)`: função pura em `emporio.rules.verificacao`
- [x] `Agente.responder(..., telefone_remetente=...)`: identifica o cliente a cada mensagem
- [x] Tool `meus_pedidos`, sem argumentos
- [x] `consultar_pedido` autoriza os pedidos do cliente identificado pelo canal
- [x] Simulador: o campo telefone faz o papel do número do remetente
- [x] `python -m emporio chat --telefone "(67) 98432-1098"`

### **Não** faz parte

| Item | Por quê |
|---|---|
| Listar pedidos por telefone ou e-mail **digitado** | Qualquer um que saiba o telefone de outra pessoa veria o histórico dela (RN-09 continua valendo) |
| Receber o número do webhook real da Meta | O protótipo ainda não recebe mensagens da Cloud API (SPEC-004) |

## 4. Regras

| # | Regra |
|---|---|
| RP-01 | Só o número do remetente, entregue pelo canal, identifica o cliente. Telefone ou e-mail digitado na conversa nunca lista pedidos |
| RP-02 | O número confere quando os dígitos, sem o +55, são iguais aos do cadastro (DDD + número). Sufixo de 8 ou 9 dígitos não basta |
| RP-03 | Se nenhum cliente ou mais de um cliente tiver o número, não há identificação |
| RP-04 | A sessão guarda o `customer_id`, nunca o número; o número continua mascarado em log, histórico e `--debug` (RN-24) |
| RP-05 | `meus_pedidos` devolve no máximo 5 pedidos, do mais recente para o mais antigo, com data, status, total registrado e itens; nunca telefone ou e-mail |
| RP-06 | Pedido de outro cliente continua exigindo número + telefone ou e-mail (RN-08), e a verificação de um pedido de outro cliente não dá acesso aos pedidos do dono do número |
| RP-07 | Sem número do canal (evals, `chat` sem `--telefone`), `meus_pedidos` responde que não identificou o cliente e orienta a pedir o número do pedido |
| RP-08 | Com o cliente identificado, a Lia o chama pelo primeiro nome do cadastro (`customers.csv`), que tem preferência sobre o nome do perfil do WhatsApp (SPEC-010). Sem identificação, vale o perfil; sem os dois, a Lia pergunta como chamar o cliente |

## 5. Critérios de aceite

- [x] **CP-01** Dado o remetente (67) 98432-1098 (Pedro), `meus_pedidos` devolve os pedidos 19 (22/02/2026, cancelado) e 1 (15/10/2025, entregue), nessa ordem.
- [x] **CP-02** Dado o mesmo remetente, `consultar_pedido(1)` sem verificação é autorizado; `consultar_pedido(8)`, de outra cliente, não é.
- [x] **CP-03** Dado um remetente fora do cadastro, ou nenhum, `meus_pedidos` devolve `identificado: false`.
- [x] **CP-04** O número do remetente não aparece na saída das tools, no histórico nem no SQLite.
- [x] **CP-05** Dado o remetente (67) 98432-1098 com o perfil "Apelido" (ou vazio), a Lia é orientada a chamá-lo de "Pedro" e o painel mostra "Pedro · (67) 9****-1098".

## 6. Limitações

- O simulador aceita qualquer número no campo telefone, porque simula o canal. No WhatsApp real, o número vem da Meta.
- Um número de WhatsApp compartilhado (família, empresa) vê os pedidos do cadastro ligado a ele.
