# Questionário para a SPEC: agente de atendimento Empório da Música

- **Revisão:** 2, de 01/11/2026, depois da revisão do Codex (ver o histórico no fim)
- **Objetivo:** fechar as decisões que vão virar a `SPEC-001` do desafio técnico da Artefact (AI Engineer 2026) antes de escrever código.
- **Base:** enunciado (`Desafio Técnico AI Engineer 2026/desafio_tecnico_ai_eng_artefact.pdf`), dados (`data/*.csv`, `data/políticas_da_loja.pdf`) e o que aprendemos em dois projetos:
  - **ALJ** (`Alj/`): bot de WhatsApp com máquina de estados, extração de comprovante por LLM com queda para perguntas manuais, atendimento humano pelo painel, simulador no mesmo caminho do webhook, relógio injetável, auditoria e LGPD.
  - **Trato Fácil Empresas** (`Trato facil empresas/`): specs numeradas com Fase 0 de descoberta, tabela canônica de estados, regras numeradas e sincronizadas, critérios dado/quando/então, extração por LLM com validação dos campos críticos e máscara de dados pessoais em log.
- **Como responder:** marque uma opção por pergunta (ou várias onde estiver escrito "marque todas"), ou escreva a sua. A opção com **(rec.)** é a recomendação padrão: se você não responder, ela vale e entra no README como suposição documentada, como o enunciado pede ("assuma uma interpretação razoável, documente e siga em frente").

---

## 0. Conflitos e limitações observados nos dados e no manual

Conferi os seis CSVs e o PDF de políticas por script, e o Codex conferiu de novo. Cada item exige uma decisão, e a coluna "Pergunta" aponta onde ela é tomada. As linhas dos CSVs contam o cabeçalho como linha 1.

| # | Achado | Evidência | Pergunta |
|---|---|---|---|
| A1 | Dois números de WhatsApp diferentes | §1.2: "(67) 3341-4444"; §7: "(67) 3321-4500" | 7.2 |
| A2 | E-mail com acento num lugar e sem no outro | capa: `contato@emporiodamusica.com.br`; §1.2: `contato@empóriodamusica.com.br` | 7.2 |
| A3 | Parcela mínima contraditória dentro do manual | a tabela da §3 diz "parcela mínima R$ 100"; a §3.1 escalona: até 3x sem mínimo, exceto parcela abaixo de R$ 50; de 4x a 6x, mínimo de R$ 80; de 7x a 12x, mínimo de R$ 100 | 7.2 |
| A4 | Pedidos fora da regra de parcelamento da §3.1 | pedido 9: R$ 349,90 em 6x (≈ R$ 58 < 80); 16: R$ 429,90 em 6x (≈ R$ 72 < 80); 18: R$ 459,90 em 12x (≈ R$ 38 < 100, cancelado). O pedido 7, R$ 159,90 em 3x (≈ R$ 53), **respeita** a §3.1 | 6.8 |
| A5 | O PIX não se acumula com promoção | §6.2: "O desconto de PIX (5%) não se aplica sobre preços já promocionais"; promoções não se acumulam. Ex.: produto 121 com a promoção 14 sai de R$ 549 por R$ 439,20, sem os 5% a mais | 6.6 |
| A6 | Total dos pedidos com `payment_method=pix` igual ao preço atual, sem os 5% | pedidos 1, 5, 10, 13 (pendente) e 17 (cancelado). Não há decomposição do total nem prova de pagamento | 6.8 |
| A7 | Total diferente da soma calculada com os **preços atuais** | pedido 3: R$ 3.450 contra R$ 3.498; pedido 20: R$ 1.400 contra R$ 1.488. `order_items.csv` não tem preço unitário histórico, então isso não prova erro | 6.8 |
| A8 | Status atual de produto em tensão com o histórico | produto 130 está `coming_soon` hoje, mas aparece nos pedidos 3 (entregue) e 14 (pendente). O catálogo não tem histórico de status | 6.4 |
| A9 | Status contra estoque | 136 `discontinued` com estoque 13; 113 descontinuado com estoque 0; 96 (Giannini GF-3D) `active` com estoque 0 | 6.4 |
| A10 | Nome, descrição e specs se contradizem | 135: o nome diz Music Man, a descrição diz Fender Jazz Bass em Alder e as specs dizem Ash. 137: nome Yamaha, descrição Ibanez de 5 cordas, specs com 4 cordas. 139: Yamaha × Pearl. 140: Pearl × Tama. 142: nome Korg de 61 teclas × descrição Roland de 88. 144: Roland × Yamaha | 6.3 |
| A11 | `specs` muda de sentido por categoria e não existe coluna de marca | `strings` é material (`nylon`) nos violões e quantidade (`"4"`) nos baixos; a marca só aparece no nome | 6.3 |
| A12 | Catálogo parcial | 65 produtos contra "mais de 300" no manual; as categorias 6, 7 e 8 (sopros e cordas orquestrais) estão vazias. A ausência no CSV não prova que a loja não tem o produto | 6.5 |
| A13 | Promoções sem datas | 25 promoções, 4 ativas (12, 14, 19, 24). Não há início nem fim, então "inativa" não quer dizer necessariamente "encerrada"; os produtos 93, 96 e 99 têm vários registros, todos inativos | 6.6 |
| A14 | Frete com limite não definido | §5.1: grátis "acima de R$ 500" e R$ 35 "abaixo de R$ 500"; não diz o que vale com R$ 500 exatos nem se o valor considerado é antes ou depois do desconto. O manual também não lista quais municípios são "região metropolitana" | 6.7 |
| A15 | Faltam dados para decidir devolução e entrega | `orders.csv` não tem data efetiva de recebimento, canal da compra (online ou loja), transportadora, data de despacho nem endereço; o cliente tem só a cidade. O arrependimento (§4.1) vale para compra online e conta a partir do recebimento | 7.3 |
| A16 | Relógio contra atualidade dos dados | pedidos de out/2025 a mar/2026; hoje é 01/11/2026. Mudar a data do agente não atualiza os pedidos ("pendente" desde março) | 6.9 |
| A17 | Pedido ligado ao cliente só por `customer_id` | o cadastro tem nome, telefone e e-mail. Isso identifica o cadastro, mas não autentica quem está conversando | 8.1 |
| A18 | Nome abreviado e nome genérico | "Takamine GD20" resolve para um único produto (95, "Takamine GD20 Dreadnought Natural"); "quero um Takamine" é ambíguo (95, 100, 105, 115) | 6.3 |
| A19 | A política proíbe informar preço, estoque ou prazo sem consultar o sistema e manda sugerir alternativa quando falta estoque | §7.1 e §7.3 | 4.2 |

Também verificado: não há ID duplicado nem referência órfã entre os CSVs, e todo campo `specs` é um JSON válido. Os códigos de rastreio seguem o formato do manual (§5.3: `BR` + 9 caracteres + `BR`).

---

## 1. Objetivo e avaliação

**1.1 O que deve sobressair na entrega?** O enunciado avalia "lógica, clareza e iniciativa" e diz valorizar mais "como você resolve" do que "uma solução perfeita".
- [x] **(rec.)** Decisões justificadas e rastreáveis (spec → código → teste → exemplo), com um agente simples e critérios de qualidade medidos (seção 13)
- [ ] Arquitetura sofisticada (multiagente, grafo, RAG vetorial completo)
- [ ] Interface caprichada

**1.2 Prazo e horas disponíveis:** _(data do e-mail e horas reais; isso define o corte de escopo da seção 3)_

## 2. Persona e tom

**2.1 Nome e identidade do assistente?**
- [x] **(rec.)** Nome próprio curto ligado à loja, que se apresenta como assistente virtual, nunca como humano
- [ ] Sem nome ("Assistente do Empório")

**2.2 Tom:** a política (§7.1) pede "informal mas profissional, como um amigo que entende de música". Usa emoji?
- [x] **(rec.)** No máximo um emoji por mensagem e nunca em reclamação
- [ ] Nenhum
- [ ] Livre

**2.3 Tamanho das respostas** (canal pensado como WhatsApp)
- [x] **(rec.)** Curtas, com listas de até 5 itens e "quer ver mais?"
- [ ] Livres

**2.4 Segue o fluxo padrão da §7.2** (saudação com nome, entendimento, consulta, resposta, fechamento)?
- [x] **(rec.)** Sim, como regra do prompt, sem repetir a saudação a cada mensagem
- [ ] Não

## 3. Escopo

**3.1 Intenções do MVP** (marque todas)
- [x] **(rec.)** Informações da loja (endereço, horário, contato, formas de pagamento)
- [x] **(rec.)** Busca no catálogo com filtros (categoria, faixa de preço, marca, características)
- [x] **(rec.)** Preço e disponibilidade de um produto, com promoção ativa e condição no PIX
- [x] **(rec.)** Status e rastreio de pedido
- [x] **(rec.)** Políticas: troca, devolução, arrependimento, garantia, frete, parcelamento, privacidade
- [x] **(rec.)** Fora de escopo e acessórios (redirecionar com educação, §7.1)
- [x] **(rec.)** Reclamação e pedido de atendimento humano (ver 3.2)
- [ ] Simular parcelamento (valor e número de parcelas pela §3.1)
- [ ] Recomendação consultiva ("sou iniciante, qual violão?")

**3.2 Efeitos permitidos e encaminhamento.** Um arquivo local não encaminha nada a ninguém, então o agente não pode prometer "encaminhei para a equipe, retorno em 24h".
- [x] **(rec.)** Somente leitura. Para reclamação, devolução ou pedido de humano: informa os canais e o horário reais da loja e, se o cliente confirmar, gera um **registro simulado** (`tickets.jsonl`) com o texto "registrei sua solicitação (protótipo)". Sem alterar pedido nem estoque. O registro só é gravado depois da confirmação do cliente (lição do ALJ: dado é conferido antes de virar efeito, `conversation.py:361`)
- [ ] Somente leitura, sem registro nenhum
- [ ] Alterar dados (cancelar pedido, reservar estoque)

**3.3 Idioma**
- [x] **(rec.)** Português; responde no idioma do cliente se vier em outro, sem prometer suporte formal
- [ ] Só português

## 4. Arquitetura do agente

**4.1 Abordagem**
- [x] **(rec.)** Function calling com tools tipadas para os dados e uma tool para as políticas: um agente só, num loop curto. Regras de negócio (preço final, parcelamento, frete, elegibilidade) ficam em funções puras e testáveis; a saída do LLM sozinha nunca autoriza uma decisão de negócio (lição do ALJ: `AGENTS.md` proíbe confirmar pagamento por OCR)
- [ ] Agente de SQL (text-to-SQL num SQLite): flexível, mas arrisca consulta errada e exposição de clientes em lote
- [ ] RAG puro (CSV e PDF no vetor): ruim para preço e estoque exatos
- [ ] ReAct ou grafo (LangGraph) com roteador de intenção

**4.2 Garantia contra número inventado (A19)**
- [x] **(rec.)** Preço, estoque, status e prazo vêm só de tool, e as tools devolvem campos já calculados e ligados à entidade (produto, pedido, condição de pagamento). Os campos críticos são formatados a partir desse resultado, não reescritos livremente pelo LLM. Os testes conferem a ligação (o preço citado é do produto citado), não só a presença do número
- [ ] Só instrução no prompt
- [ ] Validador que confere se todo "R$" da resposta apareceu em alguma tool: fraco, porque não detecta número certo ligado ao produto errado

**4.3 Framework**
- [x] **(rec.)** SDK nativo do provedor e Pydantic para os schemas das tools: pouca dependência e fácil de explicar
- [ ] LangChain ou LangGraph
- [ ] PydanticAI, LlamaIndex ou outro: _____

**4.4 Estado explícito.** No ALJ, `conversation.py` é uma máquina de estados porque o fluxo era transacional.
- [x] **(rec.)** Conversa livre com tools; estado explícito só para a identificação do cliente (8.1) e a confirmação de registro (3.2)
- [ ] Máquina de estados para tudo

**4.5 Limites do loop e falhas de tool**
- [x] **(rec.)** No máximo N chamadas de tool por turno (ex.: 5) e um tempo limite; tool desconhecida ou argumento inválido devolvem um erro estruturado ao modelo, que tenta uma vez; falha persistente vira resposta segura (5.3). Nenhuma falha parcial é apresentada como resposta completa
- [ ] Sem limite

**4.6 Estratégia de prompt** (o enunciado pede isso no README)
- [x] **(rec.)** System prompt em camadas: (1) identidade e tom; (2) regras invioláveis (A19, escopo, privacidade, não prometer o que a política não dá); (3) quando usar cada tool; (4) o que fazer com informação insuficiente: perguntar uma coisa útil antes de encaminhar. Os dados e o texto do manual entram só como resultado de tool, nunca como instrução
- [ ] Prompt único e curto

## 5. Modelo e provedor

**5.1 Modelo principal**
- [x] **(rec.)** Escolher por teste: rodar o mesmo conjunto curto de perguntas (Fase 0, seção 6.1) em 2 ou 3 candidatos e registrar no README a qualidade de tool use em português, a latência, o custo e o que o avaliador precisa para rodar (chave, camada grátis ou download)
- [x] Já decidido: **OpenRouter com Zero Data Retention** em toda chamada (`provider.zdr = true`, sem fallback para endpoint sem ZDR). O modelo é escolhido por teste entre os que têm endpoint ZDR e suportam tools (SPEC-001, D-02 e D-03)

**5.2 Provedor trocável e LLM falso para testes.** No ALJ, `RECEIPT_EXTRACTOR=openrouter|claude|manual` e a interface `WhatsAppProvider` com `mock` e `cloud_api` deixam testar e simular pelo mesmo caminho do código real (`providers/base.py`, `simulator.py`).
- [x] **(rec.)** Sim: interface `LLMClient` com uma implementação real e uma falsa, roteirizada para os testes rodarem sem chave. Exemplos e métricas sempre dizem se vieram do modelo real ou do falso
- [ ] Um provedor fixo

**5.3 Falha do LLM** (rede, chave inválida, limite de uso)
- [x] **(rec.)** Mensagem cordial com os contatos e o horário da loja, mais log do erro; nunca stack trace para o cliente
- [ ] Repetir a chamada N vezes e depois a mensagem acima

**5.4 Temperatura e determinismo**
- [x] **(rec.)** Temperatura baixa e resultados de tool em ordem estável, para os evals serem reproduzíveis
- [ ] Padrão do provedor

## 6. Dados e ferramentas

**6.1 Descoberta e carga dos dados**
- [x] **(rec.)** Uma Fase 0 curta, como no Trato Fácil, adaptada a um projeto novo (sem as exigências de reuso de sistema legado): um script de perfil confirma os achados da seção 0 e gera `docs/data_quality.md`. Na inicialização, os CSVs são carregados para modelos Pydantic e validados
- [ ] Ler o CSV a cada chamada, sem validação

**6.2 Falha na carga** (CSV ausente, JSON de `specs` inválido, referência quebrada)
- [x] **(rec.)** Arquivo obrigatório ausente impede a inicialização com uma mensagem clara; linha inválida é descartada e registrada no log, e o agente continua com o resto
- [ ] Qualquer erro impede a inicialização

**6.3 Identidade do produto (A10, A11, A18)**
- [x] **(rec.)** O **nome** do produto é a fonte da marca e do modelo. A **descrição** não serve para afirmar atributos quando contradiz o nome ou as specs: nesses produtos o agente usa só nome, preço, specs e estoque e marca o produto em `data_quality.md`. `specs` é normalizado por categoria (`strings` vira `material_cordas` ou `num_cordas`). Busca aproximada (sem acento e sem caixa, fuzzy): um resultado forte responde direto; vários resultados viram uma lista curta para o cliente escolher (lição do ALJ, RB-08: nunca escolher sozinho entre candidatos)
- [ ] Confiar na descrição
- [ ] Outra precedência: _____

**6.4 Status de produto (A8, A9)**
- [x] **(rec.)** `active` com estoque: disponível, com preço. `active` sem estoque: indisponível no momento e sugere alternativas (§7.3). `discontinued`: fora do catálogo e sugere equivalente (§7.3), ignorando o estoque (136). `coming_soon`: "em breve", sem prometer data. O status vale só para hoje; o agente não tira conclusões sobre pedidos antigos a partir dele
- [ ] Outra regra: _____

**6.5 Produto que não está no CSV (A12)**, ex.: um saxofone
- [ ] **(rec.)** "Não encontrei esse modelo disponível no nosso sistema agora", mais a oferta de falar com a equipe. Não afirmar que a loja não vende a categoria (o manual diz que vende) e não inventar produto,
- [x] Quando o produto solicitado não constar no CSV:

Informar: “Não encontrei esse produto disponível no nosso sistema agora.”

Se houver alternativas semelhantes no CSV, oferecer essas opções e explicar brevemente a diferença, usando apenas informações cadastradas.

Se não houver alternativas adequadas, oferecer contato com a equipe para consultar disponibilidade ou encomenda.

Não afirmar que a loja não vende a categoria, nem inventar produtos, preços ou disponibilidade.

Exemplo — saxofone sem alternativa cadastrada:
“Não encontrei um saxofone disponível no nosso sistema agora. Quer falar com a nossa equipe para consultar a disponibilidade?”

Exemplo — modelo específico com alternativa cadastrada:
“Não encontrei esse modelo disponível no nosso sistema agora, mas encontrei [modelo cadastrado]. Quer conhecer essa opção ou prefere falar com a nossa equipe sobre o modelo que procura?”

**6.6 Preço final e promoções (A5, A13)**
- [x] **(rec.)** Uma função pura calcula o preço final. Com promoção ativa: preço original, percentual e preço promocional juntos (transparência, §6.2), **sem** os 5% do PIX. Sem promoção: preço de tabela e preço no PIX (−5%). Promoção perguntada pelo nome e inativa: "essa promoção não está ativa no sistema", mais o preço atual, sem dizer quando terminou. Havendo duas promoções ativas para o mesmo produto, vale a maior, e isso fica documentado
- [ ] Outra regra: _____

**6.7 Filtros, parcelas e frete (A3, A14)**
- [x] **(rec.)** Filtro "até R$ X" usa o melhor preço à vista válido para o produto (promocional ou PIX) e mostra qual condição atende ao filtro. Parcelas seguem a §3.1, a regra mais detalhada, e o conflito com a tabela da §3 vai para o README. O valor da parcela é arredondado para centavos e a diferença vai na primeira parcela. Frete: R$ 500,00 exatos pagam a taxa (só "acima" é grátis), o valor considerado é o final, e o agente não calcula frete fora de Campo Grande (o manual exige CEP, peso e dimensões: responde com as modalidades e prazos da §5.2)
- [ ] Outra interpretação: _____

**6.8 Divergências de pedido (A4, A6, A7)**
- [x] **(rec.)** O agente informa o que está registrado (status, data, total, forma de pagamento, rastreio) sem recalcular a venda com os preços de hoje. Se o cliente questionar o valor, diz que o total registrado é aquele e que não há detalhamento suficiente para conferi-lo, e oferece a equipe. As divergências vão para `data_quality.md` e para as Limitações do README
- [ ] Sinalizar a divergência por conta própria

**6.9 Relógio (A16)**
- [x] **(rec.)** Relógio injetável (data, hora e fuso `America/Campo_Grande`), padrão = hora real, e `DATA_REFERENCIA` opcional para os testes (lição do ALJ: `now` injetado em `conversation.py:185`). O README diz que os pedidos são um retrato de 2025–2026 e que o status deles não muda com o relógio
- [ ] Data fixa no passado para todos os prazos fazerem sentido

**6.10 Lista de tools** (confirme ou ajuste)
- [x] **(rec.)** `buscar_produtos(texto?, categoria?, preco_max?, marca?, so_disponiveis=True, limite=5)`
- [x] **(rec.)** `detalhar_produto(produto_id)`: preço de tabela, preço final, condição no PIX, estoque, status, specs normalizadas
- [x] **(rec.)** `consultar_pedido(pedido_id, verificacao)`: ver 8.1
- [x] **(rec.)** `consultar_politicas(pergunta)`: ver seção 7
- [x] **(rec.)** `info_loja()`: endereço, contatos, horário e "aberto agora?"
- [ ] `simular_parcelamento(produto_id, parcelas)`: usa o preço final e a §3.1
- [ ] `registrar_solicitacao(tipo, resumo)`: só se 3.2 permitir

**6.11 Dinheiro e datas**
- [x] **(rec.)** `Decimal` ou centavos internamente (lição do ALJ, `AGENTS.md`: "valores sempre em centavos inteiros"); exibição `R$ 1.899,00` e `dd/mm/aaaa`
- [ ] Outra: _____

## 7. Políticas (PDF)

**7.1 Como o agente consulta as políticas?** O PDF tem 8 páginas.
- [x] **(rec.)** Converter o PDF uma vez para Markdown revisado e dividido por seção (§1–§10) e servi-lo pela tool `consultar_politicas`, com busca BM25 ou por palavra-chave que devolve as seções inteiras com o número. Sem resultado bom: devolve o índice das seções para o modelo escolher, ou responde que vai confirmar com a equipe
- [ ] Manual inteiro no system prompt (com cache de prompt): o mais simples e confiável, mas gasta tokens em toda mensagem
- [ ] RAG vetorial: exagero para 8 páginas; justificar se escolher

**7.2 Conflitos dentro do manual (A1, A2, A3): qual valor prevalece?**
- [x] **(rec.)** Telefone e WhatsApp: (67) 3341-4444, que aparece na capa e na tabela de dados da empresa. E-mail: a versão sem acento. Parcelamento: a §3.1, porque é a mais detalhada. Cada escolha entra no README como suposição
- [ ] Informar os dois valores ao cliente
- [ ] Outra: _____

**7.3 "Me arrependi, posso devolver?" (A15)** (cenário sugerido no enunciado)
- [x] **(rec.)** Pedir o número do pedido e a verificação (8.1). Se o pedido não estiver `delivered`, explicar o status e o que fazer. Se estiver entregue, perguntar **a data em que recebeu** e **se a compra foi online**. Dentro de 7 dias corridos e online (§4.1): explicar as condições (embalagem original, sem uso, reembolso na mesma forma em até 10 dias úteis, frete por conta da loja) e oferecer o registro (3.2). Fora do prazo ou compra na loja: dizer que o arrependimento não se aplica e apresentar as alternativas da política (troca por preferência em 7 dias, defeito em 30 dias, garantia de 90 dias mais a do fabricante), sem transformar arrependimento em defeito. Sem os dados: explicar a regra de forma condicional. Nunca usar `estimated_delivery` para negar
- [ ] Só explicar a política, sem olhar o pedido

## 8. Identificação do cliente e privacidade

**8.1 O que exigir para mostrar um pedido (A17)?**
- [x] **(rec.)** Número do pedido **e** um dado que confere com o cadastro (telefone ou e-mail). A conferência é feita em código, dentro da tool, nunca decidida pelo LLM. A autorização vale só para aquele pedido naquela sessão e cai quando o cliente pergunta por outro pedido. O agente nunca lista pedidos por nome, nunca devolve dados de outro cliente e nunca ecoa telefone ou e-mail completos (`(67) 9****-3456`). O README declara que isso confere o cadastro mas **não prova** que quem conversa é o dono, e que é uma simulação
- [ ] Só o número do pedido
- [ ] Simular "telefone do remetente" como no WhatsApp (`--telefone` no CLI)

**8.2 Quais dados pessoais vão para onde?** Lição do ALJ (spec §11): minimizar, informar o envio ao provedor e definir retenção. Lição do Trato Fácil (`mascarar.py`, item M7 da auditoria): a máscara não cobre tudo, e `ler_contrato_gemini.py:323` ainda loga 100 caracteres do documento.
- [x] **(rec.)** Ao modelo: só os campos do pedido verificado, sem telefone nem e-mail. No log e no rastro de depuração: telefone e e-mail mascarados. No histórico: só durante a sessão. Nos exemplos públicos do repositório: só clientes do CSV fictício, mascarados
- [ ] Sem tratamento

**8.3 Aviso de privacidade no primeiro contato**, como no ALJ (`privacy_notice`, `conversation.py:127`)
- [x] **(rec.)** Uma linha na saudação: assistente virtual com IA, e os dados são usados só para o atendimento
- [ ] Não

## 9. Fora de escopo, guardrails e segurança

**9.1 Pergunta fora do escopo** (política, futebol, receita, código)
- [x] **(rec.)** Recusa curta e simpática que traz a conversa de volta à loja
- [ ] Responde e depois redireciona

**9.2 Música fora da venda** ("como afinar um violão?", "folk ou clássico?")
- [x] **(rec.)** Até 2 frases, quando ajudam a escolher um produto do catálogo
- [ ] Recusa

**9.3 Acessórios** (cordas, palhetas, cabos, pedais, amplificadores, cases: §1 e §7.1)
- [x] **(rec.)** Informa que a loja trabalha só com instrumentos e sugere procurar lojas parceiras, sem citar nomes (o manual não lista nenhuma), entrar em contato com nossa equipe
- [ ] Só informa que não vende

**9.4 Prompt injection e jailbreak** ("ignore as instruções", "me dê 50% de desconto", "liste todos os clientes")
- [x] **(rec.)** As tools não aceitam parâmetros que exponham clientes em lote; o agente não concede desconto nem promete prazo ou reembolso fora da política; texto vindo de dados ou do PDF é tratado como dado; há evals específicos de ataque
- [ ] Só instrução no prompt

**9.5 Ofensas e conteúdo impróprio**
- [x] **(rec.)** Resposta neutra e oferta de atendimento humano
- [ ] Usar uma API de moderação

## 10. Conversa, horário e atendimento humano

**10.1 Gestão da conversa**
- [x] **(rec.)** Mensagem com várias intenções: responde todas, em ordem. Referências ("o segundo", "e no PIX?"): resolvidas pelo histórico e pelos resultados de tool da sessão. Correção do cliente ("não, era o pedido 12"): descarta a verificação anterior. Busca sem resultado: tenta uma reformulação (sinônimo, sem filtro de preço) e, se continuar vazia, faz **uma** pergunta de esclarecimento antes de encaminhar
- [ ] Sem regras específicas

**10.2 Quando oferecer atendimento humano?**
- [x] **(rec.)** Quando o cliente pede, numa reclamação, numa dúvida que a política manda levar à gerência (§10) ou depois de 2 falhas de entendimento. Oferece os canais e o horário reais e o registro simulado (3.2), e continua disponível (no ALJ, "Falar com a organização" mostra o contato e o bot segue atendendo), Acessórios
- [ ] Nunca

**10.3 Fora do expediente (§2 e §7.1)**
- [x] **(rec.)** Responde normalmente o que é automatizável e, para o que precisa de pessoa, informa o horário de retorno (seg–sex 9h–18h, sáb 9h–13h, fuso `America/Campo_Grande`). Feriados vêm de um calendário configurável (nacionais, estaduais e municipais de Campo Grande) e horários especiais (Black Friday, Natal) são configuráveis, com a limitação documentada
- [ ] Só a mensagem de "fora do horário"

## 11. Memória

**11.1 Memória e persistência**
- [x] **(rec.)** Memória da sessão (mensagens e resultados de tool), com uma janela das últimas N trocas. Persistência entre sessões fica fora do MVP e entra em "com mais tempo" (no WhatsApp seria por telefone, como no ALJ)
- [ ] SQLite por sessão, com retomada
- [ ] Sem memória

## 12. Interface e execução

**12.1 Interface**
- [x] **(rec.)** CLI interativo; o serviço do agente não depende da interface (como no ALJ, "serviços testáveis isoladamente"), então uma API ou UI pode entrar depois sem refatorar
- [ ] CLI e API FastAPI `POST /chat`
- [ ] UI simples (Streamlit ou Gradio)

**12.2 Rastro de ferramentas e fontes** (`--debug`: tools chamadas, argumentos, resultado resumido, seções do manual usadas)
- [x] **(rec.)** Sim; é a base dos exemplos de conversa e ajuda o avaliador a ver como o agente chegou à resposta
- [ ] Não

**12.3 Como o avaliador roda?**
- [x] **(rec.)** Versão do Python fixada, dependências travadas (`uv.lock` ou `requirements.txt` com versões), `.env.example` com o mínimo, um comando que funciona em Windows, macOS e Linux (`python -m emporio chat`) e um script Python que reproduz os exemplos (sem depender de `make`)
- [ ] Docker obrigatório

## 13. Avaliação, testes e diagnóstico

**13.1 Testes automatizados**
- [x] **(rec.)** pytest em três níveis: (a) unidade das funções puras e tools, com oráculos escritos à mão, independentes do código testado (ex.: preço do produto 121 no PIX = R$ 439,20); (b) conversas completas com o LLM falso; (c) evals com o LLM real, marcados `@pytest.mark.llm`, fora da execução padrão
- [ ] Só testes manuais

**13.2 Conjunto de evals**
- [x] **(rec.)** Casos cobrindo cada intenção de 3.1, cada achado da seção 0, os limites (R$ 500 exatos, 7.º dia, parcela no limite, promoção inativa) e os ataques de 9.4. Fatos são verificados por regra; algumas falhas são críticas e reprovam o caso inteiro (inventar preço, vazar dado de cliente, prometer reembolso fora da política). README com uma tabela por categoria e a indicação de modelo real ou falso
- [ ] Só os exemplos do enunciado

**13.3 Tom (persona)**
- [x] **(rec.)** Revisão humana com uma rubrica curta; LLM como juiz é opcional
- [ ] LLM como juiz para tudo

**13.4 Critérios de aceite dado/quando/então** (template do Trato Fácil, `TEMPLATE.md` §6)
- [x] **(rec.)** Sim; cada critério vira um teste ou um eval
- [ ] Não

**13.5 Diagnóstico e custo**
- [x] **(rec.)** Log JSON por turno (id da conversa, tools com argumentos e duração, tokens, latência, erro), com dados pessoais mascarados; tokens e custo estimado por conversa no README. Tracing externo (Langfuse, OpenTelemetry) fica em "com mais tempo"
- [ ] print

## 14. Entregáveis do desafio

**14.1 Estrutura do repositório**
- [x] **(rec.)** `src/emporio/{agent,tools,rules,data,policies,llm,cli}`, `data/`, `docs/specs/SPEC-001.md` (template do Trato Fácil), `docs/data_quality.md`, `docs/decisoes.md` (ADRs curtos), `examples/conversas/`, `tests/`, `evals/`, `README.md`, `AGENTS.md`
- [ ] Um único pacote, sem subdivisão

**14.2 Commits e entrega.** O enunciado pede repositório **público no GitHub**, histórico com progresso real, nada de force-push, nada alterado depois do prazo e o link enviado em resposta ao e-mail.
- [x] **(rec.)** Um commit por incremento verde, com a spec citada na mensagem (padrão do Trato Fácil: `feat: busca de produtos (spec 001)`), a spec commitada primeiro, a tag `entrega` no último commit antes do prazo e o envio do link por e-mail
- [ ] Livre

**14.3 Exemplos de conversa (3 a 5; pelo menos 1 não trivial)**
- [x] **(rec.)** Cinco conversas em `.md`, geradas pelo CLI com o modelo real e `--debug`:
  1. Violões até R$ 1.000 (filtro, só disponíveis, promoção sem acumular com PIX)
  2. Preço do "Takamine GD20", seguido de "e um Takamine elétrico?" (nome abreviado, depois lista para escolher)
  3. Status e rastreio de pedido (verificação, pedido enviado e pedido pendente)
  4. "Me arrependi, posso devolver?" (verificação, pergunta da data e do canal, prazo de 7 dias, registro simulado)
  5. Endereço e "estão abertos agora?", seguidos de um acessório, uma pergunta fora do escopo e uma tentativa de prompt injection
- [ ] Os 4 sugeridos no enunciado, sem mudança

**14.4 Seções do README** (confirme)
- [x] **(rec.)** Como rodar · Arquitetura (diagrama) · Estratégia de prompt (4.6) · Decisões e alternativas descartadas · Suposições (cada achado da seção 0 com a decisão) · Avaliação (tabela) · Limitações e próximos passos · Uso de assistentes de IA

**14.5 "Uso de assistentes de IA"** (o enunciado diz que pode contar a favor)
- [x] **(rec.)** Descrever o workflow efetivamente usado, com exemplos: que ferramentas, em que etapas (questionário, spec, código, revisão), o que foi aceito e o que foi recusado das sugestões (ex.: esta revisão do Codex corrigiu achados e teve uma afirmação recusada depois de conferida) e onde houve decisão humana
- [ ] Menção breve

**14.6 "Com mais tempo"** (marque todas)
- [x] Integração com WhatsApp Cloud API (adaptador e simulador do ALJ)
- [x] Persistência entre sessões e painel de atendimento humano
- [x] Encaminhamento real de tickets
- [x] RAG vetorial e reranking quando o manual crescer
- [x] Tracing e painel de qualidade
- [x] Frete por CEP e checkout
- [] cli gerencial

**14.7 Regras para o agente de código (`AGENTS.md`)**, no estilo do anexo da spec do ALJ
- [x] **(rec.)** Nada de preço, estoque, status ou prazo sem tool · regras em funções puras com teste · não implementar o que estiver marcado `PENDENTE` · dinheiro em Decimal ou centavos · dados pessoais mascarados · todo comportamento novo entra com teste
- [ ] Outras: _____

---

### Próximo passo

Com as respostas, escrevo `docs/specs/SPEC-001-agente-atendimento.md` no template do Trato Fácil (contexto, objetivo, escopo e o que fica fora, tabela canônica de estados, regras numeradas, casos de borda, critérios dado/quando/então, riscos) e o plano de incrementos.

### Histórico de revisões

- **Rev. 3 (01/11/2026):** questionário respondido. Decisão nova: OpenRouter com ZDR. Respostas consolidadas em `docs/specs/SPEC-001-agente-atendimento.md`; pendências P-01 (prazo) e P-02 (simular o valor das parcelas) registradas lá.

- **Rev. 2 (01/11/2026), depois da revisão do Codex, conferida nos arquivos:**
  - **Removido** o antigo achado "trechos truncados no PDF". O erro foi da minha extração, que cortava as linhas em 400 caracteres; o PDF está completo.
  - **Achados novos:**
    - o PIX não se acumula com promoção (§6.2);
    - a parcela mínima se contradiz dentro do manual (§3 contra §3.1);
    - produtos com nome, descrição e specs contraditórios;
    - `specs` muda de sentido por categoria e não há coluna de marca;
    - promoções sem datas;
    - frete com R$ 500 exatos não definido;
    - faltam dados para decidir devolução e entrega.
  - **Corrigidos:**
    - pedidos fora da regra de parcelamento: 9, 16 e 18 (o 7 respeita a §3.1);
    - 25 promoções, não 24;
    - o GD20 é nome abreviado, não ambiguidade;
    - Giannini sem estoque é o id 96;
    - divergências de total são calculadas contra preços atuais, não contra o preço histórico.
  - **Recomendações alteradas:**
    - devolução pergunta a data de recebimento e o canal, sem usar `estimated_delivery`;
    - a garantia contra número inventado verifica a ligação com a entidade, não só a presença do número;
    - a identificação do cliente é declarada como simulação e aplicada em código;
    - o registro de solicitação é simulado e confirmado pelo cliente antes;
    - o MVP fica em CLI com memória da sessão;
    - LLM como juiz passa a opcional;
    - a escolha do modelo é feita por teste;
    - relógio com hora, fuso e calendário configurável.
  - **Perguntas novas:**
    - limites do loop e falhas de tool;
    - estratégia de prompt;
    - falha na carga dos dados;
    - preço usado no filtro, parcelas e frete;
    - gestão da conversa (várias intenções, referências, correções, busca sem resultado);
    - quais dados vão ao modelo e aos exemplos;
    - exemplo de status e rastreio.
  - **Juntadas:**
    - avaliação e diagnóstico (antigas 1.3, 13 e 14);
    - efeitos e encaminhamento (antigas 3.2 e 10.1);
    - descoberta dos dados (antigas 6.1 e 16.1).
  - **Retiradas** as opções caricatas.
  - **Recusada uma afirmação do Codex:** os códigos de rastreio têm 8 caracteres no meio. Conferido: têm 9, como o manual diz.
