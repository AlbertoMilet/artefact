# SPEC-003: Alerta sonoro para o vendedor

- **Status:** concluída (rev. 2)
- **Data:** 2026-11-01
- **Autor:** Alberto Milet
- **Origem:** pedido do usuário em 01/11/2026, inspirado no aviso de novo caso do painel do projeto Saúde Legal (`panel/panel.js`, `verificarNovosCasos` e `tocarAviso`)
- **Depende de:** SPEC-001 (registro de solicitação, máscara de dados)

---

## 1. Contexto e problema

Quando o cliente pede para falar com uma pessoa, ou quando a Lia registra uma reclamação, devolução ou troca, alguém da equipe precisa saber **na hora**. Hoje isso só fica no `tickets.jsonl` e na tela da conversa: o vendedor, ocupado no balcão, não percebe.

O Saúde Legal resolveu o mesmo problema no painel jurídico: um vigia consulta a fila a cada 20 s e toca um som sintetizado. Há dois padrões, um para encaminhamento automático e outro, mais longo e distinto, para pedido explícito do cliente, para o advogado reconhecer o caso quente sem olhar a tela. O aviso visual cobre o caso de som bloqueado ou mudo.

## 2. Objetivo

Avisar o vendedor, com som e texto, quando o cliente pedir atendimento humano ou quando o sistema encaminhar uma solicitação à equipe, com um som distinto para o pedido explícito.

## 3. Escopo

### Faz parte

- [x] Detecção determinística de pedido explícito por vendedor ou atendente na mensagem do cliente
- [x] Alerta de encaminhamento quando uma solicitação é gravada (reclamação, devolução, troca, outro, atendimento humano)
- [x] Fila de alertas em `logs/alertas.jsonl` (mascarada), lida por um vigia em outro terminal: `python -m emporio vendedor`
- [x] Som sintetizado, sem arquivo de áudio, com dois padrões (os mesmos do Saúde Legal); aviso visual sempre
- [x] Mudo: `--sem-som`, `/som` no chat, preferência salva `alerta_sonoro`
- [x] Primeira passada do vigia só registra o que já existe (abrir com a fila cheia não dispara alertas)

### **Não** faz parte

| Item | Por quê |
|---|---|
| Painel web, notificação push, WhatsApp para o vendedor | Protótipo em CLI; a fila em arquivo deixa isso pronto para um painel |
| Alerta para cada mensagem do cliente | Só os dois eventos acima; o resto seria ruído |

## 4. Comportamento esperado

| Evento | Quando | Padrão de som | Aviso |
|---|---|---|---|
| `pedido_vendedor` | O cliente pede vendedor, atendente, humano ou pessoa ("quero falar com um vendedor") | tríade ascendente tocada duas vezes (784, 1046,5 e 1318,5 Hz) | "🙋 Cliente pediu um vendedor: quer falar agora." |
| `encaminhamento` | Uma solicitação é gravada pela tool `registrar_solicitacao` | duas notas curtas (880 e 1174,7 Hz) | "📋 Nova solicitação encaminhada à equipe: reclamação (SIM-...)." |

### Regras

| # | Regra | Origem |
|---|---|---|
| RA-01 | O pedido explícito é detectado em código, por frases ("falar com um vendedor", "quero um atendente", "atendimento humano"...), sem depender do modelo | Saúde Legal (`EXPLICIT_LAWYER_REQUEST`) |
| RA-02 | Pedido explícito toca o padrão `vendedor`; encaminhamento toca o padrão `normal`. Os dois no mesmo turno: vale o `vendedor` | Saúde Legal (`PADROES_AVISO`) |
| RA-03 | Sem duplicar: o mesmo pedido explícito na mesma conversa só alerta de novo 10 min depois do último **alerta** (não do último pedido: quem insiste a cada 5 min volta a alertar); o registro de `atendimento_humano` logo depois de um pedido explícito vai para a fila sem tocar de novo | Saúde Legal (`vistos`) |
| RA-04 | O aviso visual sai sempre, mesmo com som mudo ou indisponível | Saúde Legal (toast e título da página) |
| RA-05 | A fila guarda tipo, motivo, conversa, protocolo e um trecho da mensagem do cliente **mascarado** | RN-24 da SPEC-001 |
| RA-06 | O vigia ignora o que já estava na fila quando abriu e toca uma vez por ciclo, mesmo com vários alertas novos (o aviso informa quantos) | Saúde Legal (`verificarNovosCasos`) |
| RA-07 | O som é sintetizado: `winsound.Beep` no Windows; campainha do terminal (`\a`) nos demais. Tocar não bloqueia a conversa | Saúde Legal (oscilador, sem arquivo) |
| RA-08 | O alerta é interno: a Lia não promete ao cliente que um vendedor vai chamá-lo (o registro segue simulado, RN-21) | SPEC-001 |

## 5. Critérios de aceite

- [x] **CA3-01** Dado "quero falar com um vendedor", então um alerta `pedido_vendedor` vai para a fila e o padrão `vendedor` é tocado.
- [x] **CA3-02** Dado "o vendedor de vocês me indicou este violão", então nenhum alerta.
- [x] **CA3-03** Dado o registro gravado de uma reclamação, então um alerta `encaminhamento` com o protocolo e o padrão `normal`.
- [x] **CA3-04** Dado um pedido explícito e, no turno seguinte, o registro de `atendimento_humano`, então o registro vai para a fila sem tocar de novo.
- [x] **CA3-05** Dado o vigia aberto com 3 alertas antigos na fila, então nada toca; com 2 alertas novos, toca uma vez e avisa "2 novos".
- [x] **CA3-06** Com `--sem-som`, nada é tocado, mas o aviso visual aparece.
- [x] **CA3-07** A fila não contém telefone nem e-mail completos.
