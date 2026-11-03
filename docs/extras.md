# Funcionalidades extras (opcionais)

Estes protótipos **não fazem parte da solução pedida pelo desafio**, que está no [README](../README.pt-br.md) ([English](../README.md)). Fiz depois de o agente estar pronto e avaliado, para explorar o que um atendimento por WhatsApp precisaria. O prompt avaliado nos evals é o mesmo com ou sem eles.

Depois de o agente estar pronto e avaliado, fiz oito protótipos do que um atendimento por WhatsApp precisaria. Cada um tem spec e testes. Os quatro primeiros passaram por revisão independente do Codex; os dois últimos nasceram de avaliações de LGPD e de segurança feitas pelo Claude Code e pelo Codex, com as correções revisadas de novo:

| Funcionalidade | Padrão | Experimentar |
|---|---|---|
| [Retenção na janela de 24 h](specs/SPEC-002-inatividade-janela-24h.md): lembrete contextual quando o cliente some, com bloqueios em código (pedido de parar, horário silencioso, máximo de 3) | desligada | `uv run python -m emporio chat --retencao --debug` e `/esperar 1d` |
| [Alerta para o vendedor](specs/SPEC-003-alerta-sonoro-vendedor.md): aviso quando o cliente pede um vendedor ou há encaminhamento | **aviso visual ligado no chat**; som só no vigia | `uv run python -m emporio vendedor` num segundo terminal |
| [Conectar o WhatsApp da loja](specs/SPEC-004-conectar-whatsapp-da-loja.md): login com Facebook, código por SMS e registro na Cloud API, retomável, com token cifrado | comando à parte | `uv run python -m emporio whatsapp conectar --simulado` |
| [Origem do lead](specs/SPEC-005-origem-do-lead.md): cada canal divulga um link do WhatsApp com um emoji no fim (📸 Instagram, 🎬 TikTok, 🔎 Google, ▶️ YouTube); o código detecta o canal na primeira mensagem e o tira antes do modelo | sempre ligada; sem marcador, origem desconhecida | `uv run python -m emporio origem links` e `origem relatorio` |
| [Nome do cliente](specs/SPEC-010-nome-do-cliente.md): a Lia chama o cliente pelo primeiro nome do perfil do WhatsApp. O perfil passa por um filtro em código; sem nome usável, ela pergunta uma vez como chamar o cliente | ligado quando o canal manda o perfil; sem perfil, o prompt é o dos evals | campo "Nome no perfil" no Simulador ou `chat --nome "Ana Paula"` |
| [Pedidos pelo número do WhatsApp](specs/SPEC-011-pedidos-pelo-numero-do-whatsapp.md): o número do remetente, que o WhatsApp confirma, é cruzado com `customers` e `orders`; a tool `meus_pedidos` lista até 5 pedidos, que dispensam a verificação por telefone ou e-mail; o nome do cadastro vence o do perfil. Telefone digitado nunca lista pedidos | ligado quando o canal manda o número; sem número, vale o fluxo da SPEC-001 | Simulador com o telefone (67) 98432-1098, ou `chat --telefone "(67) 98432-1098"` |
| [LGPD no atendimento](specs/SPEC-012-lgpd-no-atendimento.md): aviso de privacidade; histórico das conversas e logs de turnos apagados depois de 90 dias (a auditoria do painel fica 365 dias e `tickets.jsonl` não é expurgado; o expurgo roda ao iniciar, a cada hora com requisições e por comando); pedido do titular com prazo de 15 dias; exportar e apagar dados no painel, com auditoria; telefone como HMAC ([política](privacidade.md)) | sempre ligado | "quero apagar meus dados" no Simulador; no painel, "Dados pessoais (LGPD)" na conversa; `python -m emporio privacidade expurgar` e `privacidade auditoria` |
| [Segurança do painel](specs/SPEC-013-seguranca-do-painel.md): token CSRF nos POSTs com sessão e conferência de `Origin` (inclusive no login); CSP com nonce e arquivos locais; sessão revogável; limites de mensagens e de verificações de pedido; modo demonstração isolado | sempre ligado | `ui --host 0.0.0.0` recusa sem `--https-proxy`; 11 mensagens seguidas no Simulador |

**Efeitos no agente, mesmo com a retenção desligada:**
- O aviso visual de alerta aparece no chat. O som, por padrão, toca só no vigia; `ALERTA_SONORO=false` ou `--sem-som` o silenciam, e o aviso visual continua.
- Se o cliente voltar depois de 24 h de silêncio, a verificação do pedido e o registro em andamento expiram. O histórico da conversa continua.
- Um emoji de canal no fim da primeira mensagem é tirado do texto antes do modelo e vira a origem do lead.
- Foto, áudio, vídeo ou documento ([SPEC-014](specs/SPEC-014-fotos-audios-videos-e-documentos.md)) viram um marcador (`[cliente enviou uma foto]`): o arquivo nunca chega ao modelo nem ao disco, a Lia responde com um texto fixo (só lê texto; escreva o que precisa; defeito ou troca vão para a equipe) e, com pedido ou solicitação em andamento, a equipe recebe um alerta. No Simulador, botões 📷 🎤 🎬 📄; no terminal, `/foto`, `/audio`, `/video` e `/documento`.
- A primeira resposta traz o aviso de privacidade; depois de 5 verificações de pedido erradas na sessão, `consultar_pedido` recusa novas tentativas; no painel, acima de 10 mensagens por minuto (ou 200 por dia) na conversa, o modelo não é chamado.
- Com o nome do cliente (do cadastro, se o número do WhatsApp o identifica; senão, do perfil), o prompt ganha uma seção `# Cliente`. Sem número nem perfil (evals, `chat` sem `--telefone` e `--nome`), o prompt é idêntico ao avaliado.
- Os evals não passam número de remetente nem nome de perfil, então `meus_pedidos` e a seção `# Cliente` são cobertas por testes sem rede e por conversas manuais, não pelos evals.

A conexão do WhatsApp foi testada só com um transporte falso. Ela **não foi exercitada contra a Meta real**, e receber mensagens exige um webhook HTTPS que não existe neste protótipo. As principais variáveis dos extras estão em `.env.example`.

## Hospedagem

Um protótipo do painel está hospedado numa VPS (Docker no Easypanel, com HTTPS), com dados fictícios. Não é um atendimento em produção: não há webhook do WhatsApp nem observabilidade. Passo a passo em [deploy-easypanel.md](deploy-easypanel.md).
