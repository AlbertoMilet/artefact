# Instruções para agentes de código (Empório da Música)

- Specs vigentes: `docs/specs/SPEC-001-agente-atendimento.md` (agente) e `docs/specs/SPEC-002-inatividade-janela-24h.md` (retenção). Regras são citadas por número (RN-xx, RI-xx), decisões por D-xx, critérios de aceite por CA-xx e CI-xx.
- Specs 003 (alerta para o vendedor): a detecção de pedido explícito é determinística (`emporio.alertas.deteccao`); evals e exemplos usam `alertas=False`.
- SPEC-004 (WhatsApp da loja): token da Meta nunca em tela, log ou arquivo em claro; PIN nunca salvo; testes usam o ProvedorSimulado ou um transporte falso (nada de rede).
- A janela de 24 h conta só da última mensagem do cliente (`emporio.retencao.janela`); nada é enviado por iniciativa da loja fora dela, e a retenção fica desligada por padrão.
- Implemente em incrementos pequenos, cada um com testes passando, e cite a spec no commit: `feat: busca de produtos (spec 001)`.
- Nada de preço, estoque, status, prazo ou valor de parcela que não venha de tool (RN-01). As tools devolvem valores já formatados; o LLM não faz contas.
- Regras de negócio ficam em `src/emporio/rules/` como funções puras (sem banco, rede ou LLM), com testes unitários e valores esperados escritos à mão. Se um teste falhar, confira a regra no manual (`src/emporio/policies/manual.md`) antes de mudar o código ou o teste.
- Dinheiro em `Decimal`; datas com fuso `America/Campo_Grande`; relógio sempre injetado (`emporio.rules.horario`).
- Toda chamada ao OpenRouter leva `provider.zdr = true`. Nunca adicione fallback sem ZDR nem parâmetros que o modelo não suporte nos endpoints ZDR.
- Telefone e e-mail de clientes: nunca na saída das tools, mascarados em log, `--debug`, histórico e exemplos (RN-09, RN-24).
- Tools devolvem erro estruturado (`{"erro": ...}`), nunca exceção para o agente.
- Testes padrão (`uv run pytest`) rodam sem rede e sem chave; o que precisa do modelo real leva `@pytest.mark.llm`.
- Não implemente nada marcado como PENDENTE na spec: deixe `# TODO P-0N`.
- Antes de mudar prompt ou tools, rode `uv run python -m evals.rodar` e compare com `docs/avaliacao.md`.
