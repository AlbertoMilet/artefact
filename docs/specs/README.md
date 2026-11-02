# Specs

Cada funcionalidade ganha uma spec **antes** de virar código. A spec registra o _porquê_; o git guarda o _o quê_. As mensagens de commit citam a spec, por exemplo `feat: busca de produtos (spec 001)`.

| # | Funcionalidade | Status |
|---|---|---|
| [001](SPEC-001-agente-atendimento.md) | Agente de atendimento da Empório da Música | Fases 0 a 6 concluídas |
| [002](SPEC-002-inatividade-janela-24h.md) | Inatividade do cliente na janela de 24 horas (retenção) | concluída |
| [003](SPEC-003-alerta-sonoro-vendedor.md) | Alerta sonoro para o vendedor | concluída |
| [004](SPEC-004-conectar-whatsapp-da-loja.md) | Conectar o WhatsApp da loja (login com Facebook e código por SMS) | concluída (falta teste com app real da Meta) |
| [005](SPEC-005-origem-do-lead.md) | Origem do lead pelo emoji do link (Instagram, TikTok, Google, YouTube) | concluída |
| [006](SPEC-006-interface-web.md) | Interface web do atendimento, no estilo do painel ALJ | concluída |
| [007](SPEC-007-atendimento-humano.md) | Atendimento humano no painel: conversas, assumir e devolver à Lia; Simulador de WhatsApp | concluída |
| [008](SPEC-008-login-do-painel.md) | Login do painel com usuários no .env (senha só como hash) | concluída |
| [009](SPEC-009-configuracoes-no-painel.md) | Configurações no painel: modelo, persona, WhatsApp, origem dos leads, retenção | concluída |
| [010](SPEC-010-nome-do-cliente.md) | Chamar o cliente pelo primeiro nome do perfil do WhatsApp | concluída |
| [011](SPEC-011-pedidos-pelo-numero-do-whatsapp.md) | Pedidos do cliente pelo número do WhatsApp ("qual foi minha última compra?") | concluída |
| [012](SPEC-012-lgpd-no-atendimento.md) | LGPD no atendimento: aviso, retenção de 90 dias, direitos do titular, HMAC do telefone, auditoria | concluída |
| [013](SPEC-013-seguranca-do-painel.md) | Segurança do painel: CSRF, CSP, sessão revogável, limites, modo demonstração isolado | concluída |
| [014](SPEC-014-fotos-audios-videos-e-documentos.md) | Fotos, áudios, vídeos e documentos: marcador, resposta fixa sem LLM, alerta à equipe | concluída |

Documentos de apoio: [questionário que originou a spec](../processo/questionario-specs.md), [qualidade dos dados](../data_quality.md), [comparação de modelos](../fase0-modelos.md), [avaliação](../avaliacao.md), [decisões](../decisoes.md).
