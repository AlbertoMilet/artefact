# SPEC-009: Configurações no painel (modelo, persona, WhatsApp, origem, retenção)

- **Status:** concluída
- **Data:** 2026-11-01
- **Autor:** Alberto Milet
- **Origem:** pedido do usuário em 01/11/2026: "falta o local onde o usuário configura as LLMs e a persona do agente, o local onde se conectar com o zap e as demais funcionalidades".

---

## 1. Solução

Uma aba **Configurações** no painel, com sub-abas, todas atrás do login (SPEC-008):

| Aba | O que faz | Onde guarda |
|---|---|---|
| **Modelo e comportamento** | escolhe entre os 3 modelos com ZDR (ou outro slug), liga ou desliga o raciocínio estendido, define a data de referência | `.emporio.json` |
| **Persona** | nome, tratamento (a/o), tom (amigável, profissional, descontraído), emojis e instruções da loja; mostra como o agente se apresenta | `.emporio.json` |
| **WhatsApp** | o fluxo da SPEC-004 passo a passo: login com Facebook, número, código por SMS ou ligação, PIN, assinatura do app; modo simulado ou Meta real | `.emporio_whatsapp*.json` (token cifrado) |
| **Origem dos leads** | os links `wa.me` por canal (número e mensagem editáveis, botão copiar) e as conversas por origem | — |
| **Retenção** | as regras da janela de 24 h em vigor | `.env` |

As escolhas valem na próxima mensagem: o painel monta outro agente com a nova configuração, sem reiniciar. O `.emporio.json` é o mesmo do `python -m emporio configurar`.

## 2. Regras

| # | Regra |
|---|---|
| RC-01 | A persona muda só identidade e tom. As regras invioláveis, o uso das tools e as proteções do prompt não são editáveis; as instruções da loja (até 600 caracteres) entram depois das regras, com a frase de que as regras prevalecem |
| RC-02 | A persona padrão reproduz exatamente o prompt avaliado nos evals (teste que compara o texto) |
| RC-03 | Configuração inválida (modelo sem ZDR, slug malformado, persona inválida) não é gravada e o agente anterior continua |
| RC-04 | Chave do OpenRouter, segredo do app da Meta e chave de cifra ficam só no `.env`; a tela mostra só se estão configurados |
| RC-05 | O PIN do WhatsApp passa só para a Meta e nunca é guardado; sem `WHATSAPP_CHAVE_CIFRA`, o token fica só em memória enquanto o servidor roda |
| RC-06 | No modo real, o login com Facebook usa `state` em cookie (10 min) e o retorno em `/configuracoes/whatsapp/callback`, que precisa estar em `META_REDIRECT_URI` |

## 3. Critérios de aceite

- [x] **CC-01** As cinco abas abrem só com login e nenhuma mostra a chave do OpenRouter.
- [x] **CC-02** Salvar o modelo grava `.emporio.json` e vale na próxima mensagem; um modelo inválido não é gravado.
- [x] **CC-03** Salvar a persona muda o nome nas telas e no prompt; "Voltar ao padrão" restaura a Lia.
- [x] **CC-04** O WhatsApp simulado vai do login ao app assinado pelo painel, e o PIN não aparece no arquivo salvo.
- [x] **CC-05** A aba de origem gera os quatro links e conta as conversas por canal.

## 4. Limitações

- O fluxo real da Meta pelo painel não foi exercitado contra a Meta de verdade (o mesmo vale para a SPEC-004).
- A retenção aparece só para consulta: o painel ainda não tem o agendador que mandaria os lembretes sozinho.
- Mudanças de tom ou instruções não foram avaliadas; o painel lembra de rodar os evals depois de mudar.
