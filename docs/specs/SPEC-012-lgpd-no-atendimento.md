# SPEC-012: LGPD no atendimento

- **Status:** concluída
- **Data:** 2026-11-02
- **Autor:** Alberto Milet
- **Origem:** avaliação do app em relação à LGPD (Lei 13.709/2018), pedida pelo usuário em 02/11/2026, e o pedido seguinte: "escreva a spec 012 e implemente".

---

## 1. Problema

A base técnica já protegia bem os dados: minimização nas tools, máscara de telefone e e-mail, verificação do pedido, ZDR no provedor de IA e senha só como hash. A avaliação encontrou lacunas na relação com o titular:

1. O aviso de privacidade dizia "seus dados são usados só para este atendimento", mas as conversas ficavam guardadas sem prazo e passavam por um provedor de IA no exterior (arts. 6º, VI, e 9º).
2. Nenhum dado expirava, e o painel não tinha como apagar uma conversa (arts. 15 e 16).
3. Um pedido de exclusão virava um registro do tipo `outro`, "sem prazo de retorno", e ninguém conseguia atendê-lo (arts. 18 e 19).
4. CPF e CEP digitados pelo cliente ficavam em claro no histórico e nos logs (art. 46).
5. O telefone era guardado como SHA-256 sem chave, reversível por força bruta (arts. 12 e 13).
6. Operadores, transferência internacional e a coleta da origem do lead não estavam documentados (arts. 6º, VI, 33 e 37).
7. Ninguém registrava quem abriu, exportou ou apagou uma conversa no painel (arts. 37 e 46).
8. A recusa de devolução por arrependimento, decidida em código, não lembrava o direito de revisão (art. 20).

## 2. Solução

| Lacuna | O que muda |
|---|---|
| 1. Aviso | Aviso de privacidade honesto na primeira resposta: IA, finalidade, provedor sem retenção, prazo de 90 dias e como exercer direitos. Política completa em `docs/privacidade.md` |
| 2. Retenção | Expurgo de mensagens e logs com mais de 90 dias, ao iniciar a interface, a cada hora com ela no ar e por comando (`python -m emporio privacidade expurgar`) |
| 3. Direitos do titular | Tipo `privacidade` em `registrar_solicitacao`, com prazo de resposta de 15 dias informado ao cliente; no painel, exportar os dados de uma conversa (JSON) e apagá-los |
| 4. Texto livre | A máscara passa a cobrir CPF e CEP formatados |
| 5. Hash do telefone | HMAC-SHA256 com chave secreta; conversas antigas migram na primeira mensagem |
| 6. Documentação | `docs/privacidade.md`: controlador, finalidades, bases legais, operadores, transferência internacional, retenção, direitos e origem do lead |
| 7. Auditoria | Tabela `auditoria` no SQLite: quem abriu, exportou ou apagou cada conversa |
| 8. Decisão automatizada | Quando a devolução por arrependimento é negada, a tool orienta a Lia a oferecer a revisão pela equipe |

## 3. Escopo

### Faz parte

- [x] `emporio.rules.privacidade`: prazos e filtro do expurgo como funções puras
- [x] Máscara de CPF e CEP em `mascarar_texto`
- [x] `chave_do_telefone` com HMAC e migração preguiçosa do hash antigo
- [x] Expurgo do SQLite, de `logs/emporio.jsonl` e de `logs/alertas.jsonl`
- [x] Exportar e apagar os dados de uma conversa no painel, com registro em `auditoria`
- [x] `registrar_solicitacao(tipo="privacidade")` com prazo de 15 dias
- [x] Aviso de privacidade novo e linha no prompt para pedidos sobre dados pessoais
- [x] `docs/privacidade.md`

### **Não** faz parte

| Item | Por quê |
|---|---|
| Apagar o cadastro em `customers.csv` | Os CSVs são a base da loja, somente leitura no protótipo; o pedido fica registrado para a equipe |
| Expurgar `tickets.jsonl` | São o registro das solicitações, inclusive as de privacidade, guardado para cumprir obrigação legal (CDC e a própria LGPD, art. 16, I); o resumo já é mascarado |
| Perfis de acesso no painel | Exige um modelo de papéis; a auditoria cobre a rastreabilidade por enquanto |
| Nome do encarregado (DPO) | A loja não informou. `# TODO P-12`: o aviso e a política usam o e-mail de contato da loja até haver um encarregado nomeado |
| Mascarar endereço e nome em texto livre | Não há padrão confiável para reconhecê-los; fica como limitação |

## 4. Regras

| # | Regra |
|---|---|
| RL-01 | Conversas, mensagens e linhas de log sem atividade há mais de 90 dias são apagadas. A data vem do relógio real de gravação (`registrado_em`), nunca da data de referência do agente |
| RL-02 | Linha de log sem `registrado_em` (gravada antes desta spec) conta como expirada |
| RL-03 | O aviso de privacidade aparece na primeira resposta e diz: assistente com IA, finalidade (atendimento e pedidos), provedor de IA sem retenção, guarda por até 90 dias e que o cliente pode pedir para ver ou apagar os dados |
| RL-04 | Pedido do cliente sobre os próprios dados (ver, corrigir, apagar, saber o uso) é registrado com `tipo="privacidade"`, e a tool devolve o prazo de resposta de até 15 dias (art. 19, II), que a Lia informa |
| RL-05 | Apagar os dados de uma conversa remove a conversa e as mensagens do SQLite e as linhas dela em `emporio.jsonl` e `alertas.jsonl`, e registra a ação em `auditoria` |
| RL-06 | A exportação devolve, em JSON, os dados da conversa como estão guardados (já mascarados), sem o hash do telefone |
| RL-07 | A chave do HMAC vem de `EMPORIO_CHAVE_TELEFONE`; sem ela, é gerada uma vez e guardada ao lado do banco, fora do git. Telefone nunca em claro |
| RL-08 | CPF (`000.000.000-00`) e CEP formatado (`00000-000`) ou sem hífen depois da palavra "CEP" são mascarados; o CEP da loja, público, não |
| RL-09 | Abrir, exportar e apagar uma conversa no painel gravam usuário, ação, conversa e horário em `auditoria` |
| RL-10 | Devolução negada por arrependimento (fora do prazo ou compra na loja) vem sempre com orientação de oferecer a revisão do caso pela equipe |
| RL-11 | A auditoria do painel é guardada por 365 dias, para responsabilização (art. 6º, X), e depois apagada |
| RL-12 | Com a interface no ar, o expurgo roda de novo a cada hora e descarta o cache em memória das conversas afetadas; o prazo de 90 dias vale por mensagem, então uma conversa ativa perde as mensagens antigas |
| RL-13 | O Simulador não põe telefone nem nome em URL ou cookie: o navegador guarda um identificador aleatório e o servidor guarda o cliente simulado. `avisos.log` é gravado mascarado e entra no expurgo. O acesso direto ao histórico (`/atendimento/{id}/thread` sem HTMX) e o apagar do Simulador são auditados, e o apagar do Simulador também limpa os logs |

## 5. Critérios de aceite

- [x] **CL-01** Uma conversa sem atividade há 91 dias é apagada pelo expurgo; uma de 89 dias fica.
- [x] **CL-02** "Meu CPF é 123.456.789-09 e o CEP 79002-100" fica gravado como `***.***.***-09` e `79***-***`; o CEP da loja, 79202-333, continua visível.
- [x] **CL-03** O banco guarda o HMAC do telefone, não o SHA-256 puro; uma conversa gravada com o hash antigo é encontrada e migrada na mensagem seguinte.
- [x] **CL-04** No painel, "Apagar dados" remove a conversa do banco e dos logs e grava em `auditoria`; "Exportar dados" devolve JSON sem o hash do telefone.
- [x] **CL-05** `registrar_solicitacao(tipo="privacidade")`, confirmado, devolve o prazo de 15 dias no texto para o cliente.
- [x] **CL-07** Uma mensagem com mais de 90 dias numa conversa ativa é apagada, e a conversa continua com as recentes.
- [x] **CL-08** Depois de trocar de cliente no Simulador, nenhum cookie contém o telefone ou o nome.
- [x] **CL-06** A primeira resposta traz o aviso novo; as seguintes, não.

## 6. Limitações

- Endereço e nome em texto livre não são mascarados.
- O expurgo roda ao iniciar a interface, a cada hora enquanto ela recebe requisições e por comando; não há agendador fora do processo web. Um expurgo pelo terminal não limpa o cache de um painel já aberto.
- Bloqueios para produção apontados pela revisão do Codex (02/11/2026), fora do alcance do protótipo: confirmação de posse do contato (OTP) na verificação do pedido; gestão completa dos pedidos do titular (responsável, vencimento, resposta, conclusão, exportação além da conversa); formalização da transferência internacional e dos operadores.
- A auditoria fica no mesmo SQLite das conversas; quem tem acesso ao arquivo pode alterá-la.
- Os textos legais são de um protótipo e precisam de revisão jurídica antes de produção.
