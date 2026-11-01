# Empório da Música: agente de atendimento

Protótipo de agente de atendimento por texto para a Empório da Música, loja fictícia de instrumentos musicais em Campo Grande/MS. Desafio técnico AI Engineer, Artefact.

> **Em construção.** Fases 0 a 5 concluídas (ver [SPEC-001](docs/specs/SPEC-001-agente-atendimento.md), Anexo B). Este README será completado na Fase 6 com decisões técnicas, avaliação, limitações e uso de assistentes de IA.

## Requisitos

- Python 3.12+ e [uv](https://docs.astral.sh/uv/)
- Chave do [OpenRouter](https://openrouter.ai/settings/keys) para usar o modelo real. Toda chamada exige Zero Data Retention (`provider.zdr = true`). Sem chave, use o modo demonstração (`--fake`)

## Como rodar

```bash
uv sync
cp .env.example .env                       # preencha OPENROUTER_API_KEY (modelo padrão: deepseek/deepseek-v4.1-flash)
uv run python -m emporio chat              # conversa interativa
uv run python -m emporio chat --debug      # mostra as tools chamadas, os argumentos e o resultado (mascarados)
uv run python -m emporio chat --fake       # modo demonstração: sem chave e sem modelo de linguagem
uv run python -m emporio chat -m "Quanto custa o Takamine GD20?" -m "e em quantas vezes?"   # sem interação
uv run pytest                              # testes (sem rede e sem chave)
uv run python -m evals.rodar --repeticoes 3   # avaliação com o modelo real -> docs/avaliacao.md
uv run pytest -m llm                       # o mesmo, como teste (CA-16 a CA-18)
uv run python scripts/gerar_exemplos.py    # regenera examples/conversas/
```

Durante a conversa: `/novo` recomeça e `/sair` encerra. O log de cada turno (JSON, com telefone e e-mail mascarados) fica em `logs/emporio.jsonl`.

## Fase 0

```bash
uv run python scripts/perfil_dados.py      # confirma os achados A1–A19 e gera docs/data_quality.md
uv run python scripts/comparar_modelos.py  # compara modelos com ZDR e gera docs/fase0-modelos.md
```

## Documentos

- [SPEC-001: agente de atendimento](docs/specs/SPEC-001-agente-atendimento.md)
- [Qualidade dos dados](docs/data_quality.md)
- [Avaliação com o modelo real](docs/avaliacao.md)
- [Exemplos de conversa](examples/conversas/)
- [Questionário que originou a spec](docs/processo/questionario-specs.md)
