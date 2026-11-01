# Empório da Música: agente de atendimento

Protótipo de agente de atendimento por texto para a Empório da Música, loja fictícia de instrumentos musicais em Campo Grande/MS. Desafio técnico AI Engineer, Artefact.

> **Em construção.** Fase atual: **0, descoberta** (ver [SPEC-001](docs/specs/SPEC-001-agente-atendimento.md), Anexo B). Este README será completado na Fase 6 com instruções de uso, decisões técnicas, avaliação, limitações e uso de assistentes de IA.

## Requisitos

- Python 3.12+ e [uv](https://docs.astral.sh/uv/)
- Chave do [OpenRouter](https://openrouter.ai/settings/keys) para usar o modelo real. Toda chamada exige Zero Data Retention (`provider.zdr = true`)

## Fase 0

```bash
uv sync
cp .env.example .env                              # preencha OPENROUTER_API_KEY
uv run python scripts/perfil_dados.py             # gera docs/data_quality.md
uv run python scripts/comparar_modelos.py         # gera docs/fase0-modelos.md
```

## Documentos

- [SPEC-001: agente de atendimento](docs/specs/SPEC-001-agente-atendimento.md)
- [Qualidade dos dados](docs/data_quality.md)
- [Questionário que originou a spec](docs/processo/questionario-specs.md)
