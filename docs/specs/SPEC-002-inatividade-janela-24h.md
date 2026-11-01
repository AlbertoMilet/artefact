# SPEC-002: Inatividade do cliente na janela de 24 horas

- **Status:** concluída (rev. 3): correções da revisão do Codex de 01/11/2026
- **Data:** 2026-11-01
- **Autor:** Alberto Milet
- **Origem:** pedido do usuário em 01/11/2026, inspirado no agente de retenção do projeto Saúde Legal (`app/services/session_window.py`, `app/services/retention_agent.py`, `app/models/retention.py`)
- **Depende de:** SPEC-001 (agente, tools, relógio injetável, máscara de dados)

---

## 1. Contexto e problema

O agente da SPEC-001 só fala quando o cliente fala. No canal pensado para a loja, o WhatsApp (§7 do manual), o cliente costuma sumir no meio do atendimento:
- some depois de receber a lista de violões;
- some quando a Lia pergunta a data de recebimento do pedido;
- some antes de confirmar o registro de uma devolução.

A equipe perde essas vendas e solicitações.

Há duas restrições do canal e da política:
- **Janela de 24 horas do WhatsApp:** mensagem livre só vale até 24h depois da última mensagem **do cliente**. Mensagem da loja não reabre a janela. Fora dela, só template aprovado.
- **Tom da §7.1:** acolhedor, sem pressão. A LGPD (§9) exige respeitar quem não quer receber mensagens.

## 2. Objetivo

Quando o cliente fica em silêncio, a Lia avalia em momentos definidos se vale retomar a conversa: envia um lembrete útil e contextual, espera ou para. Ela nunca escreve fora da janela de 24h, nunca insiste com quem pediu para parar e nunca inventa preço ou promessa no lembrete.

## 3. Escopo

### Faz parte

- [x] Janela de 24h contada da última mensagem do cliente, com a situação calculada em código
- [x] Agenda de avaliações por tempo de silêncio (padrão: 30 min, 4 h e 21 h desde a última mensagem do cliente)
- [x] Bloqueios em código antes de qualquer decisão do modelo e de novo antes do envio
- [x] Decisão ENVIAR / ESPERAR / PARAR pelo LLM, com saída JSON validada e a mensagem conferida em código
- [x] Pedido para não receber mensagens ("pare", "não quero mais receber") detectado em código, sem depender do modelo
- [x] Última tentativa marcada quando faltam até 4 h para a janela fechar
- [x] Ao voltar depois de a janela fechar, o cliente começa uma sessão nova: a verificação do pedido e a proposta de registro expiram
- [x] Desligado por padrão (`RETENCAO_ATIVA=false`)
- [x] Demonstração no CLI: `/esperar 30m` avança um relógio simulado e roda a varredura; `/janela` mostra a situação da janela

### **Não** faz parte

| Item | Por quê |
|---|---|
| Templates aprovados da Meta para reabrir a janela | Não há integração com WhatsApp no protótipo; fora da janela, o agente simplesmente não escreve |
| Worker de varredura em produção, banco e reserva por versão | O protótipo roda em processo único no CLI; a função de varredura (`Retencao.varrer`) fica pronta para um agendador. Ela não é pura: chama o modelo, altera o acompanhamento e o histórico e registra log |
| Métricas de recuperação por etapa | Sem dados de produção |
| Lembrete com preço, estoque ou prazo | O lembrete não chama tools; valores no lembrete são proibidos (RN-01 da SPEC-001) |

## 4. Comportamento esperado

### 4.1 Fluxo

```
mensagem do cliente ──> ao_receber(): reancora a janela, zera o ciclo, detecta pedido para parar
resposta da Lia     ──> ao_responder(): registra a última mensagem automática
varredura(agora)    ──> para cada conversa com avaliação vencida:
                         bloqueios em código ── bloqueado ──> PARAR, ou reagendar (madrugada, intervalo mínimo)
                               │ livre
                         LLM decide (JSON) ── ENVIAR ──> mensagem conferida ──> envia e reagenda
                                           ├─ ESPERAR ─> reagenda (sugestão do modelo dentro dos limites)
                                           └─ PARAR ───> encerra o ciclo deste silêncio
```

### 4.2 Estados do acompanhamento

| Estado | Significado | Quem resolve | Transiciona para |
|---|---|---|---|
| `ativo` | O cliente acabou de falar; a primeira avaliação está agendada | varredura | `aguardando`, `lembrete_enviado`, `encerrado` |
| `aguardando` | Avaliado, nada enviado (o agente decidiu esperar) | varredura | `lembrete_enviado`, `encerrado`, `janela_fechada` |
| `lembrete_enviado` | Ao menos um lembrete neste silêncio | varredura ou cliente | `ultima_tentativa`, `encerrado`, `janela_fechada`, `ativo` |
| `ultima_tentativa` | Lembrete enviado faltando até 4 h para a janela fechar | varredura ou cliente | `janela_fechada`, `ativo` |
| `janela_fechada` | 24 h sem mensagem do cliente: nada mais é enviado | cliente | `ativo` (sessão nova) |
| `encerrado` | Parou: pedido do cliente, teto atingido, assunto resolvido ou encaminhado à equipe | cliente | `ativo` (exceto pedido para parar) |

### Regras de negócio

| # | Regra | Origem |
|---|---|---|
| RI-01 | A janela vale 24 h a partir da última mensagem **do cliente**; lembrete e resposta da Lia não reabrem nada | WhatsApp; Saúde Legal `session_window.py` |
| RI-02 | Nenhum envio nos últimos 30 min da janela (margem para entrega); depois disso, o estado vira `janela_fechada` | Saúde Legal |
| RI-03 | Avaliações em 30 min, 4 h e 21 h de silêncio (configurável). Avaliar não é enviar | Saúde Legal |
| RI-04 | No máximo 3 lembretes por silêncio e 6 avaliações; os contadores zeram quando o cliente responde | Saúde Legal |
| RI-05 | Intervalo mínimo de 20 min desde a última mensagem automática (resposta ou lembrete) | Saúde Legal |
| RI-06 | Horário silencioso: nada é enviado entre 21h e 8h de Campo Grande; a avaliação é reagendada para as 8h, se a janela permitir | Saúde Legal; §7.1 (acolhimento) |
| RI-07 | Pedido para não receber mensagens ("pare", "não quero mais receber"...) é detectado em código e encerra a retenção de vez naquela conversa; a conversa continua se o cliente voltar a escrever | LGPD (§9); Saúde Legal |
| RI-08 | O lembrete tem no máximo 60 palavras e uma pergunta, não contém valores em R$, não afirma estoque, entrega, frete, prazo nem parcelamento, não promete reserva ou cancelamento e não repete um lembrete já enviado. Mensagem que falha na conferência não é enviada. Limitação: é conferência por padrões, que reduz mas não elimina o risco de o modelo afirmar algo comercial com outras palavras | RN-01 e RN-22 da SPEC-001 |
| RI-09 | Faltando até 4 h para a janela fechar, a avaliação é a última tentativa: o modelo é avisado e só envia se houver algo útil | Saúde Legal |
| RI-10 | Saída inválida do modelo (JSON quebrado, ação desconhecida) vira ESPERAR, nunca envio | Princípio da SPEC-001: saída do LLM não autoriza ação sozinha |
| RI-11 | Solicitação de atendimento humano registrada encerra a retenção (a equipe assume) | Q 10.2 da SPEC-001 |
| RI-12 | Cliente que volta depois de a janela fechar começa uma sessão nova: `pedido_verificado` e `registro_proposto` expiram | RN-08 da SPEC-001 (autorização por sessão) |
| RI-13 | O contexto enviado ao modelo é o histórico já mascarado; o lembrete passa pela mesma máscara da resposta | RN-24 da SPEC-001 |
| RI-14 | Desligado por padrão; ligar é decisão explícita (`RETENCAO_ATIVA=true` ou `--retencao` no CLI) | Saúde Legal |
| RI-15 | Finalidade: o lembrete só continua o atendimento que o cliente começou. Promoção, oferta, novidade ou lançamento ficam bloqueados na conferência, porque exigem consentimento explícito (§9 do manual); a retenção não registra consentimento promocional | §9 do manual; revisão do Codex |
| RI-16 | Prazos distintos e nomeados: expiração da janela (24 h, limite absoluto), limite de envio de lembretes (expiração menos a margem) e "janela aberta" para respostas (expiração menos 60 s). A última tentativa conta da expiração real. Configuração inválida (ex.: margem negativa) é recusada | Revisão do Codex |
| RI-17 | O relógio é relido antes do envio (a chamada ao modelo leva tempo); o teto de avaliações é conferido antes de consultar o modelo; depois da última tentativa, a próxima avaliação só registra o fechamento da janela | Revisão do Codex |

### Casos de borda

| Situação | Comportamento |
|---|---|
| Cliente recebe a lista de violões e some | Em 30 min: lembrete contextual ("ficou com alguma dúvida sobre os violões?") |
| Cliente diz "depois eu vejo, estou no trabalho" e some | O modelo escolhe ESPERAR; nova avaliação mais tarde |
| Cliente diz "obrigado, era isso" | PARAR: assunto resolvido |
| Cliente escreve "pare de me mandar mensagem" | Encerrado de vez naquela conversa (RI-07), sem consultar o modelo |
| Avaliação às 22h | Reagendada para as 8h do dia seguinte, se ainda houver janela; senão, `janela_fechada` |
| Modelo devolve lembrete com "R$ 2.199,00" | Mensagem recusada (RI-08); nada é enviado; reagenda |
| Modelo devolve texto que não é JSON | ESPERAR (RI-10) |
| Cliente volta 25 h depois | Janela nova; verificação do pedido expirada (RI-12) |
| Cliente responde a um lembrete | O ciclo recomeça do zero (contadores zerados) |

## 5. Impacto técnico

| Arquivo | Mudança |
|---|---|
| `src/emporio/retencao/janela.py` | Janela de 24 h: expiração, aberta, rótulo |
| `src/emporio/retencao/modelos.py` | `Acompanhamento` e estados |
| `src/emporio/retencao/politica.py` | Funções puras: agenda, bloqueios, pedido para parar, conferência do lembrete |
| `src/emporio/retencao/agente.py` | Decisão com o LLM (prompt, JSON, validação) e varredura |
| `src/emporio/agent/agente.py` | `Conversa.acompanhamento`; ganchos ao receber e ao responder; sessão nova depois da janela |
| `src/emporio/rules/horario.py` | Relógio ajustável para a simulação no CLI |
| `src/emporio/cli.py` | `--retencao`, `/esperar`, `/janela` |
| `src/emporio/config.py` | Variáveis `RETENCAO_*` |

Variáveis novas: `RETENCAO_ATIVA` (false), `RETENCAO_AVALIACOES_MIN` (`30,240,1260`), `RETENCAO_MAX_LEMBRETES` (3), `RETENCAO_MAX_AVALIACOES` (6), `RETENCAO_INTERVALO_MIN` (20), `RETENCAO_ULTIMA_TENTATIVA_H` (4), `RETENCAO_MARGEM_ENVIO_MIN` (30).

## 6. Critérios de aceite

- [x] **CI-01** Dado a última mensagem do cliente às 10h de 25/03, a janela está aberta às 9h29 de 26/03 e fechada para envio a partir das 9h30 (margem de 30 min).
- [x] **CI-02** Dado um lembrete enviado às 11h, a janela continua expirando às 10h de 26/03 (lembrete não reabre).
- [x] **CI-03** Dado silêncio desde as 10h, as avaliações caem às 10h30, 14h e 7h do dia seguinte; a das 7h é reagendada para as 8h (horário silencioso), dentro da janela.
- [x] **CI-04** Dado "pare de me mandar mensagem", a retenção encerra sem chamar o modelo, e nenhuma varredura posterior envia nada.
- [x] **CI-05** Dado que o modelo devolve um lembrete com "R$", ou com mais de 60 palavras, ou com "reservei", ou igual a um já enviado, nada é enviado.
- [x] **CI-06** Dado saída do modelo que não é JSON, a ação é ESPERAR.
- [x] **CI-07** Dado 3 lembretes enviados no mesmo silêncio, a quarta avaliação encerra com `teto_de_lembretes`.
- [x] **CI-08** Dado um cliente com pedido verificado que volta 25 h depois, a consulta do pedido exige nova verificação.
- [x] **CI-09** Dado `/esperar 30m` no CLI com retenção ligada, a Lia envia um lembrete; com retenção desligada, nada acontece.
- [x] **CI-10** Com o modelo real: lista de produtos e silêncio → ENVIAR; "depois eu vejo" → ESPERAR; "obrigado, era isso" → PARAR.

## 7. Riscos e decisões

| Risco / decisão | Encaminhamento |
|---|---|
| Lembrete soar como pressão ou spam | Teto de 3, intervalo mínimo, horário silencioso, e o modelo pode ESPERAR ou PARAR; tom da §7.1 no prompt |
| Lembrete inventar informação | Sem tools no lembrete; valores em R$ proibidos; mensagem conferida em código |
| Custo de avaliar conversas paradas | No máximo 6 avaliações por silêncio, cada uma uma chamada curta sem tools |
| Mensagem proativa sem consentimento | Desligado por padrão; pedido para parar respeitado em código |
| Respostas vazias do modelo | Encontrado na implementação: com raciocínio ligado, o DeepSeek às vezes gastava todos os tokens de saída deliberando (`finish_reason=length`, conteúdo vazio). A decisão de retenção usa `reasoning: {enabled: false}` (só quando o modelo aceita o parâmetro nos endpoints ZDR) e uma nova tentativa para resposta vazia. Resultado: 12/12 nos cenários do CI-10 em 3 rodadas, cerca de 100 tokens e menos de 1,5 s por decisão |
| Lembrete recusado pela conferência | Ex.: duas perguntas, ou o orçamento citado pelo cliente ("até R$ 1.000"). Nada é enviado naquela avaliação; o prompt deixa essas regras explícitas |
