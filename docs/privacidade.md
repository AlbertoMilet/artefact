# Política de privacidade do atendimento (protótipo)

Como o atendimento da Empório da Música trata dados pessoais, segundo a LGPD (Lei 13.709/2018). Descreve o que o código deste repositório faz ([SPEC-012](specs/SPEC-012-lgpd-no-atendimento.md)). É texto de protótipo e precisa de revisão jurídica antes de produção.

## Controlador e encarregado

- **Controlador:** Empório da Música, Rua 14 de Maio, 3200, Centro, Campo Grande/MS.
- **Encarregado (art. 41):** ainda não nomeado pela loja (`TODO P-12`). Até lá, os pedidos vão para contato@emporiodamusica.com.br ou para o próprio atendimento.

## Quais dados e para quê

A base de demonstração em `data/` (clientes, pedidos, produtos) veio do desafio e é fictícia: nomes, telefones e e-mails não são de pessoas reais. Ela fica no repositório público para o projeto rodar e ser avaliado. As proteções abaixo (máscara, HMAC, expurgo) valem para os dados que entram pelo atendimento.

| Dado | De onde vem | Finalidade | Base legal |
|---|---|---|---|
| Mensagens da conversa | O cliente | Responder ao atendimento | Execução de contrato e procedimentos preliminares (art. 7º, V) |
| Número do WhatsApp | O canal | Identificar o cliente e mostrar os pedidos dele (SPEC-011) | Execução de contrato (art. 7º, V) |
| Nome do perfil do WhatsApp | O canal | Tratar o cliente pelo nome (SPEC-010) | Legítimo interesse (art. 7º, IX) |
| Cadastro e pedidos (`customers.csv`, `orders.csv`) | Base da loja | Status, rastreio e devolução | Execução de contrato (art. 7º, V) |
| Canal de origem do lead (emoji do link) | O link divulgado | Saber qual canal traz clientes (SPEC-005). Fica ligado à conversa (e, por ela, ao cliente), não é anônimo; o relatório (`origem relatorio`) só mostra contagens por canal | Legítimo interesse (art. 7º, IX), a ponderar e documentar antes de produção |
| Solicitações registradas (`tickets.jsonl`) | O atendimento | Reclamação, devolução, troca e pedidos sobre dados | Obrigação legal (CDC e LGPD) e execução de contrato |

Promoções só com consentimento explícito (manual, §9); a retenção por inatividade (SPEC-002) vem desligada e não faz oferta.

## Com quem os dados são compartilhados

| Operador | O que recebe | Garantias |
|---|---|---|
| OpenRouter e o provedor do modelo de linguagem | O texto da conversa e os resultados das ferramentas | Toda chamada exige Zero Data Retention e `data_collection: deny`; sem nova tentativa fora dessas condições |
| Meta (WhatsApp Cloud API), quando conectado | As mensagens trocadas | Termos da Meta para o WhatsApp Business |

**Transferência internacional (art. 33):** os provedores ficam fora do Brasil. A base para a transferência (por exemplo, cláusulas contratuais padrão) precisa ser formalizada com cada operador antes de produção.

## Por quanto tempo

| Onde | Prazo |
|---|---|
| Mensagens das conversas (`logs/atendimento.db`) | Cada mensagem, até 90 dias; a conversa some quando fica vazia. O expurgo roda ao iniciar o painel, a cada hora com ele no ar e por `python -m emporio privacidade expurgar` |
| Logs de turnos, fila de alertas e `avisos.log` | Até 90 dias; o `avisos.log` é gravado já mascarado |
| Solicitações registradas (`tickets.jsonl`) | Guardadas como registro de atendimento (art. 16, I); o resumo é mascarado |
| Auditoria do painel | 365 dias, para responsabilização (art. 6º, X) |

## Segurança

- Fotos, áudios, vídeos e documentos não são lidos nem guardados: o histórico registra só um marcador como `[cliente enviou uma foto]` (SPEC-014).

- Telefone guardado no banco só como HMAC com chave secreta e mostrado mascarado. No Simulador, telefone e nome ficam no servidor; o navegador guarda só um identificador aleatório.
- Telefone, e-mail, CPF (formatado) e CEP (formatado, ou sem hífen depois da palavra "CEP") de clientes mascarados no histórico, nos logs, nos registros e no `--debug`. A máscara é por padrão de texto e não cobre todo formato possível.
- As ferramentas não devolvem telefone nem e-mail de clientes e não listam clientes; pedido só com verificação ou pelo número do WhatsApp do dono.
- Painel com login (senha só como hash PBKDF2) e auditoria de quem abriu (inclusive o acesso direto ao histórico), exportou ou apagou cada conversa, também pelo Simulador.

## Direitos do titular (art. 18)

O cliente pede no próprio atendimento ("quero ver/apagar meus dados"). A Lia registra o pedido com o tipo `privacidade`, informa o protocolo e o prazo de resposta de **até 15 dias** (art. 19, II). No painel, a equipe pode **exportar** os dados da conversa (JSON) e **apagá-los** do histórico e dos logs.

Decisões automatizadas (art. 20): a elegibilidade da devolução por arrependimento é calculada em código pelas regras da loja; quando a devolução é negada, a ferramenta orienta a Lia a oferecer a revisão do caso pela equipe (a redação final é do modelo).

## Limitações conhecidas

**Bloqueios para produção** (apontados na revisão do Codex de 02/11/2026):
- A verificação por número do pedido + telefone ou e-mail não prova que a pessoa controla aquele contato; seria preciso confirmação por código (OTP).
- O pedido do titular é registrado com prazo, mas não há gestão do atendimento (responsável, vencimento, resposta, conclusão), e a exportação cobre só a conversa, não cadastro, pedidos e registros.
- A transferência internacional e as responsabilidades dos operadores não estão formalizadas.

**Outras:**

- Endereço e nome digitados em texto livre não são mascarados.
- O cadastro em `customers.csv` não é apagado pelo painel: o pedido fica registrado para a equipe.
- Um número de WhatsApp compartilhado vê os pedidos do cadastro ligado a ele.
- O texto atual do cliente vai ao modelo sem máscara, porque a verificação do pedido precisa do telefone ou e-mail; só o histórico é mascarado.
- Um expurgo pelo terminal não limpa o cache em memória de um painel já aberto; o expurgo do próprio painel limpa.
- O manual da loja (§9) afirma conformidade com a LGPD; é material da loja e não foi alterado.
