# SPEC-005: Origem do lead pelo emoji do link

- **Status:** concluída
- **Data:** 2026-11-01
- **Autor:** Alberto Milet
- **Origem:** pedido do usuário em 01/11/2026: "saber de onde veio o lead, pode ser um emoji ou símbolo (Instagram, TikTok, landing page do Google, YouTube; não precisa mais)".

---

## 1. Problema

A loja divulga o WhatsApp em vários canais, mas toda conversa chega igual. Sem saber de onde veio cada cliente, não dá para comparar os canais nem avisar o vendedor sobre o contexto do contato.

## 2. Solução

Cada canal divulga um link `wa.me` com a **mesma mensagem pré-preenchida** e um **emoji próprio no fim**:

| Canal | Emoji | Chave |
|---|---|---|
| Instagram | 📸 | `instagram` |
| TikTok | 🎬 | `tiktok` |
| Landing page (Google) | 🔎 | `google` |
| YouTube | ▶️ | `youtube` |

O agente confere a primeira mensagem, detecta o canal em código, tira o emoji antes de enviar o texto ao modelo e guarda a origem na sessão.

O emoji foi escolhido em vez de um código como `#IG` porque não parece rastreamento para o cliente e sobrevive ao link. Parâmetros UTM não servem: o WhatsApp não os repassa à conversa.

## 3. Escopo

### Faz parte

- [x] Detecção determinística do marcador (`emporio.rules.origem.detectar`), função pura
- [x] Marcador removido do texto antes do modelo e do histórico
- [x] Origem registrada no log dos turnos, no registro de solicitação e no alerta do vendedor
- [x] `python -m emporio origem links`: um link por canal, com o número oficial da loja ou `--numero`
- [x] `python -m emporio origem relatorio`: conversas por canal, a partir do log
- [x] `--debug` mostra a origem detectada

### **Não** faz parte

| Item | Por quê |
|---|---|
| Outros canais | O usuário limitou aos quatro |
| A Lia usar a origem na conversa | A origem é para a loja; o cliente não precisa saber que foi rastreado |
| Atribuição multitoque, custo por lead | Exige dados de campanha que o protótipo não tem |

## 4. Regras

| # | Regra |
|---|---|
| RO-01 | O marcador só vale no **fim** da mensagem, com ou sem o seletor de variação (`▶️` ou `▶`) e com espaços depois. Emoji no meio da frase não conta |
| RO-02 | Só a primeira mensagem da conversa é conferida, ou a primeira depois de a janela de 24 h fechar (SPEC-002). Mensagens seguintes não mudam a origem |
| RO-03 | O marcador sai do texto antes do modelo. Se a mensagem for só o emoji, o texto segue inteiro |
| RO-04 | Sem marcador, a origem fica vazia e o relatório a mostra como "desconhecida" |
| RO-05 | A detecção não depende do modelo e não muda nenhuma resposta da Lia |

## 5. Critérios de aceite

- [x] **CO-01** Dado "Olá! Quero mais informações 📸", então a origem é `instagram` e o modelo recebe "Olá! Quero mais informações".
- [x] **CO-02** Dado "Adoro 🎬 e quero um violão", então não há origem.
- [x] **CO-03** Dado um emoji de outro canal na segunda mensagem, então a origem não muda.
- [x] **CO-04** Dada uma solicitação registrada ou um alerta para o vendedor, então eles levam a origem ("Origem: 📸 Instagram.").
- [x] **CO-05** `origem links` gera os quatro links `wa.me` com o número oficial; `origem relatorio` conta as conversas por canal.

## 6. Limitações

- **O cliente pode apagar ou trocar o emoji.** A origem fica desconhecida ou errada; é uma medida aproximada, não prova.
- **Um cliente pode terminar a primeira mensagem com um desses emojis por acaso.** Os quatro foram escolhidos por serem raros no fim de uma pergunta sobre instrumentos (🎵 e 🎸 ficaram de fora por isso).
- **O relatório lê o log local** (`logs/emporio.jsonl`). Em produção, a origem iria para o banco junto com o contato.
