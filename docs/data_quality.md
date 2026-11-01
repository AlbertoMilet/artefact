# Qualidade dos dados (Fase 0, SPEC-001)

Gerado por `scripts/perfil_dados.py`. Não edite à mão: rode o script de novo.

## Achados

| # | Achado | Confirmado | Evidência |
|---|---|---|---|
| A1 | Dois números de WhatsApp no manual | sim | §1.2 e capa: (67) 3341-4444; §7: (67) 3321-4500 |
| A2 | E-mail com e sem acento | sim | capa: contato@emporiodamusica.com.br; §1.2: contato@empóriodamusica.com.br |
| A3 | Parcela mínima contraditória (§3 × §3.1) | sim | tabela §3: mínimo R$ 100; §3.1: até 3x (parcela ≥ R$ 50), 4–6x ≥ R$ 80, 7–12x ≥ R$ 100 |
| A4 | Pedidos fora da regra de parcelamento da §3.1 | sim | pedido 9: R$ 349,90 em 6x = R$ 58,32 (mín. R$ 80,00, confirmed); pedido 16: R$ 429,90 em 6x = R$ 71,65 (mín. R$ 80,00, pending); pedido 18: R$ 459,90 em 12x = R$ 38,33 (mín. R$ 100,00, cancelled) |
| A5 | PIX não se acumula com promoção (§6.2) | sim | §6.2: "O desconto de PIX (5%) não se aplica sobre preços já promocionais" |
| A6 | Pedidos PIX com total igual ao preço atual (sem os 5%) | sim | pedidos 1 (delivered), 5 (delivered), 10 (confirmed), 13 (pending), 17 (cancelled) |
| A7 | Total diferente da soma calculada com preços atuais | sim | pedido 3: total R$ 3.450,00 × soma atual R$ 3.498,00; pedido 20: total R$ 1.400,00 × soma atual R$ 1.488,00. order_items não tem preço unitário histórico |
| A8 | Produto coming_soon presente em pedidos | sim | produtos ['130'] nos pedidos 3 (delivered), 14 (pending) |
| A9 | Status contra estoque | sim | descontinuados: 113 (estoque 0), 136 (estoque 13); ativos sem estoque: 96 Giannini GF-3D Dreadnought Sunburst |
| A10 | Nome e descrição citam marcas diferentes | sim | 135: nome Music Man × descrição Fender; 137: nome Yamaha × descrição Ibanez; 139: nome Yamaha × descrição Pearl; 140: nome Pearl × descrição Tama; 142: nome Korg × descrição Roland; 144: nome Roland × descrição Yamaha |
| A11 | `specs.strings` muda de sentido por categoria; não há coluna de marca | sim | Guitarras: ['6']; Baixos: ['4']; Violões: ['nylon', 'steel']; Ukuleles: ['nylon'] |
| A12 | Catálogo parcial e categorias vazias | sim | 65 produtos (manual: "mais de 300"); vazias: Instrumentos de Sopro (Madeiras), Instrumentos de Sopro (Metais), Cordas Orquestrais |
| A13 | Promoções sem datas; poucas ativas | sim | 25 promoções, 4 ativas (ids 12, 14, 19, 24); produtos com vários registros: 93, 96, 99; colunas: promotion_id, product_id, discount_percent, description, is_active |
| A14 | Frete: "acima"/"abaixo" de R$ 500 sem o caso igual | sim | §5.1: grátis acima de R$ 500,00; R$ 35,00 abaixo de R$ 500,00; municípios da região metropolitana não listados |
| A15 | Pedidos sem data de recebimento, canal, transportadora e endereço | sim | colunas de orders: order_id, customer_id, order_date, status, total_brl, payment_method, tracking_code, estimated_delivery, notes |
| A16 | Pedidos são um retrato de 2025–2026 | sim | datas de 2025-10-15 a 2026-03-22; 8 pedidos ainda pending/confirmed |
| A17 | Pedido ligado ao cliente só por customer_id | sim | clientes têm: customer_id, name, phone, email, city |
| A18 | "Takamine GD20" é único; "Takamine" é ambíguo | sim | GD20: 95 Takamine GD20 Dreadnought Natural; todos: 95 Takamine GD20 Dreadnought Natural; 100 Takamine GC5CE Elétrico Nylon Natural; 105 Takamine GN51CE Elétrico Aço Natural; 115 Takamine GC1CE Elétrico Nylon Natural |
| A19 | Política exige consultar o sistema para preço, estoque e prazo | sim | §7.1 e §7.3 |

Decisão de cada achado: SPEC-001, regras RN-xx e decisões D-xx.

## Integridade

- IDs duplicados: nenhum
- Referências órfãs entre CSVs: nenhuma
- `specs` com JSON inválido: nenhum
- Códigos de rastreio no formato da §5.3 (`BR` + 9 + `BR`): sim

## Fidelidade de `src/emporio/policies/manual.md` ao PDF

Comparação de vocabulário, sem as notas de revisão. Diferenças esperadas: rodapés do PDF
("Página", "Manual de Políticas e Procedimentos") e texto da capa.

- Palavras só no PDF: aqui, atualização, começa, emporiodamusica, junho, procedimentos, página, restrito, versão, última
- Palavras só no Markdown: nenhuma
