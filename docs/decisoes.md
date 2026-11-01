# Registro de decisões

Versão curta das decisões da [SPEC-001](specs/SPEC-001-agente-atendimento.md) (§7). Cada uma traz o contexto, a decisão, as alternativas descartadas e a consequência.

| # | Decisão | Contexto | Alternativas descartadas | Consequência |
|---|---|---|---|---|
| D-01 | Function calling com 7 tools tipadas, um agente, loop curto; regras em funções puras | O manual proíbe informar preço, estoque ou prazo sem consultar o sistema; os dados têm armadilhas (PIX × promoção, parcela mínima por faixa) | Agente de SQL, RAG sobre CSV, ReAct/LangGraph, multiagente | O LLM nunca faz contas; cada regra é testável isoladamente |
| D-02 | OpenRouter com `provider.zdr = true` em toda chamada, sem fallback | O agente envia dados de pedidos de clientes ao modelo | Provedor direto sem garantia de retenção; modelo local | Menos endpoints disponíveis por modelo; sem endpoint ZDR, resposta segura |
| D-03 | Modelo escolhido por teste comparativo | A ZDR restringe os provedores; a qualidade de tool use em português varia | Escolher por reputação | `docs/fase0-modelos.md` |
| D-04 | Manual em Markdown revisado, BM25 por subseção | 8 páginas, 25 trechos | Embeddings e banco vetorial; manual inteiro no prompt | Resposta citável por seção, determinística e sem dependência extra |
| D-05 | CLI, memória só da sessão, sem banco | O foco do desafio é o agente funcionando | API HTTP, UI web, persistência em SQLite | Serviço do agente independente da interface; persistência em "com mais tempo" |
| D-06 | SDK `openai` (base_url do OpenRouter) e Pydantic | O OpenRouter é compatível com a API da OpenAI | LangChain, PydanticAI | Poucas dependências; JSON Schema das tools gerado dos modelos |
| D-07 | Tools `verificar_arrependimento` e `registrar_solicitacao` | O questionário escolheu checar o prazo e registrar a solicitação | Deixar o LLM decidir a elegibilidade | Decisão de devolução em código; registro simulado com confirmação |
| D-08 | Conflitos do manual: telefone (67) 3341-4444, e-mail sem acento, parcelamento pela §3.1 | O manual se contradiz (A1, A2, A3) | Informar os dois valores | Suposições documentadas no README |
| D-09 | `detalhar_produto` devolve parcelas máximas e valor da parcela | "Em quantas vezes posso pagar?" é provável, e o LLM não pode fazer a conta | Só explicar a regra | Parcelamento calculado em código (CA-19) |
| D-10 | `deepseek/deepseek-v4.1-flash` | Fase 0: 3 modelos com 10/10; o DeepSeek teve melhor tom, menor latência e suporta `temperature` | `openai/gpt-6-luna` (recusa em inglês), `anthropic/claude-haiku-5.5` (lento e caro) | Evals finais: 126/126 sem falha crítica |
| D-11 | Tools `calcular_frete` e `consultar_promocoes` | Revisão final do Codex: o frete estava implementado mas fora do fluxo; campanhas eram respondidas sem consultar o CSV | Deixar o modelo interpretar o manual | Frete e promoções decididos em código, com casos nos evals |
| D-12 | Registro em dois passos, com a proposta guardada na sessão | Revisão final do Codex: a confirmação era só o modelo enviando `confirmado=true` | Confiar no argumento do modelo | Confirmação exige um turno do cliente entre a proposta e a gravação |
| D-13 | Raciocínio estendido ligado no agente principal e desligado na retenção | Na retenção, o raciocínio consumia todos os tokens de saída (respostas vazias). No agente, medido nos evals: ligado 126/126; desligado 116/126 (pulava tools e só pedia dados), 0,5 s mais rápido | Desligar em tudo; aumentar o limite de tokens | `LLM_RACIOCINIO` para experimentação; retenção com 12/12 nos cenários reais |
| D-14 | Três opções de modelo no CLI (`deepseek`, `haiku`, `gpt-sol`), todas com ZDR, configuráveis por `python -m emporio configurar` e trocáveis na conversa com `/modelo` | Pedido do usuário em 01/11/2026; os três têm endpoint ZDR com tools | Um modelo fixo | Evals: deepseek 126/126 (padrão mantido), haiku 41/42, gpt-sol 41/42 com uma recusa espúria em inglês |
