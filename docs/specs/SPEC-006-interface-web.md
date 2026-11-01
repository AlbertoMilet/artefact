# SPEC-006: Interface web do atendimento (estilo do painel ALJ)

- **Status:** concluída
- **Data:** 2026-11-01
- **Autor:** Alberto Milet
- **Origem:** pedido do usuário em 01/11/2026: "substitua a CLI por uma UI estilo da ALJ". O painel do projeto ALJ usa FastAPI, Jinja2, Bootstrap 5.3 e HTMX, com navbar de marca e um simulador de WhatsApp em balões.

---

## 1. Objetivo

A conversa com a Lia passa a ser feita numa página web, que é a interface padrão: `uv run python -m emporio` abre o navegador. O agente, as tools e as regras não mudam; a página só mostra.

## 2. Escopo

### Faz parte

- [x] **Atendimento (`/`)**: conversa em balões, roteiro de perguntas com um clique, chegada por canal (SPEC-005), painel "Esta conversa" (origem, pedido verificado, protocolos, modelo, data de referência) e, em cada resposta, as tools usadas com argumentos, resultado, tempo e custo
- [x] **Painel do vendedor (`/vendedor`)**: a fila de alertas (SPEC-003) atualizada a cada 2 s, com som sintetizado no navegador depois de "Ativar som"
- [x] Identidade da logo (verde-água, verde-petróleo, azul-marinho) sobre o desenho do ALJ
- [x] `python -m emporio ui [--fake] [--porta] [--host] [--sem-navegador]`; sem argumentos, abre a interface

### **Não** faz parte

| Item | Por quê |
|---|---|
| Login e várias lojas | Protótipo local: escuta só em 127.0.0.1 por padrão |
| Conversas persistentes | Ficam em memória, uma por navegador (cookie aleatório) |
| Simular silêncio da retenção (`/esperar`) | Continua no chat do terminal, que segue disponível para automação e testes |
| Build de front-end | Bootstrap e HTMX por CDN, como no ALJ |

## 3. Regras

| # | Regra |
|---|---|
| RU-01 | Todo texto do cliente e do modelo é escapado; das respostas só `**negrito**` e `_itálico_` viram HTML |
| RU-02 | A interface usa o mesmo `Agente` do CLI e dos evals; nenhuma regra de negócio na camada web |
| RU-03 | Um turno por vez no processo (trava), suficiente para o protótipo de um computador |
| RU-04 | Telefone e e-mail seguem mascarados no rastro, como no `--debug` (RN-09) |

## 4. Critérios de aceite

- [x] **CU-01** A página inicial mostra a conversa vazia, o roteiro e os canais.
- [x] **CU-02** Uma mensagem enviada por HTMX devolve a conversa com a resposta e as tools usadas.
- [x] **CU-03** Dois navegadores têm conversas separadas; "Nova conversa" limpa a atual.
- [x] **CU-04** `<script>` digitado pelo cliente aparece como texto.
- [x] **CU-05** Um pedido de vendedor aparece na conversa e no painel do vendedor, com a origem do lead.
