# SPEC-004: Conectar o WhatsApp da loja (login com Facebook e código por SMS)

- **Status:** concluída (rev. 2): testada com o provedor simulado e com as chamadas reais conferidas sem rede; falta o teste com um app da Meta de verdade
- **Data:** 2026-11-01
- **Autor:** Alberto Milet
- **Origem:** pedido do usuário em 01/11/2026, baseado no projeto BaixaAI: o marco "um app da Meta, vários números" (`spec/MARCO-um-app-varios-numeros.md`) prevê que cada cliente entre pelo mesmo app da Meta, com o próprio portfólio via **Embedded Signup**, e deixa esse fluxo para uma spec futura. O BaixaAI não tem esse código; o cliente da Graph API dele (`app/providers/whatsapp/meta/client.py`, v25.0) serve de referência de versão e de chamadas.
- **Decisões do usuário:** é a **loja** conectando o próprio WhatsApp (não o comprador); cliente real da Graph API atrás de uma interface, com provedor simulado para testes e demonstração.

---

## 1. Contexto e problema

A Lia só atende pelo CLI. Para atender pelo WhatsApp (o canal do §7 do manual), a loja precisa conectar o número dela à WhatsApp Cloud API. Esse processo é manual e cheio de etapas na Meta:
1. login no Facebook com permissão sobre a conta do WhatsApp Business;
2. escolha ou cadastro do número;
3. código de confirmação por SMS no celular da loja;
4. registro do número com um PIN de duas etapas;
5. assinatura dos webhooks.

Quem erra uma etapa não sabe onde parou.

## 2. Objetivo

Um comando guiado, `python -m emporio whatsapp conectar`, que faz o login com a conta do Facebook do dono da loja e conecta o número de WhatsApp da loja: envia o código por SMS, confirma, registra e assina os webhooks. Ele retoma de onde parou e guarda o token cifrado.

## 3. Escopo

### Faz parte

- [x] Login com Facebook (OAuth 2.0 com `state` contra CSRF) por um servidor local de retorno (`http://localhost:8765/callback`), troca do código por token e por token de longa duração
- [x] Validação do token (`debug_token`): app certo, token válido, permissões exigidas; contas do WhatsApp Business (WABA) autorizadas vêm das `granular_scopes`
- [x] Listar os números da WABA ou cadastrar um número novo
- [x] Código de confirmação por SMS (ou ligação), confirmação do código, registro com PIN de 6 dígitos e assinatura dos webhooks do app na WABA
- [x] Estado da conexão salvo e retomável (`whatsapp status`, `whatsapp conectar` continua da última etapa)
- [x] Token cifrado com Fernet (chave em `WHATSAPP_CHAVE_CIFRA`); sem chave, o token não é salvo
- [x] Provedor simulado (`--simulado`) para demonstração e testes, sem Meta e sem SMS de verdade

### **Não** faz parte

| Item | Por quê |
|---|---|
| Receber e responder mensagens pelo webhook | Exige servidor HTTPS público; é o passo seguinte (README, "com mais tempo") |
| Embedded Signup com o SDK JavaScript da Meta (popup, `config_id`) | Exige página web em domínio aprovado; no CLI o mesmo resultado sai do OAuth padrão com as permissões do WhatsApp |
| Verificação do negócio, revisão do app e Tech Provider na Meta | Feitas no painel da Meta, fora do código |
| Guardar o PIN de duas etapas | O PIN é do dono da loja; o sistema só o envia no registro |

## 4. Comportamento esperado

### 4.1 Etapas (retomáveis)

| Etapa | Significado | Próxima ação |
|---|---|---|
| `nao_conectado` | Nada feito | login com Facebook |
| `autenticado` | Token válido, WABA escolhida | escolher ou cadastrar o número |
| `numero_escolhido` | Número definido (`phone_number_id`) | enviar o código por SMS |
| `codigo_enviado` | Código enviado ao celular da loja | digitar o código |
| `verificado` | Número confirmado na Meta | registrar com PIN |
| `registrado` | Número ativo na Cloud API | assinar webhooks |
| `conectado` | Webhooks assinados: pronto para receber mensagens | nada |

Número já verificado na Meta pula o SMS (vai a `verificado`); número já ativo (`CONNECTED`) vai a `registrado`.

### 4.2 Regras

| # | Regra | Origem |
|---|---|---|
| RW-01 | O `state` do OAuth é aleatório e conferido no retorno; diferente, o login é recusado | OAuth 2.0 (CSRF) |
| RW-02 | O token só é aceito se `debug_token` disser válido, do mesmo app (`META_APP_ID`) e com `whatsapp_business_management` e `whatsapp_business_messaging` | Meta |
| RW-03 | O número é normalizado para o Brasil (código do país 55 + DDD + número) antes de ser cadastrado | BaixaAI (`_format_phone`) |
| RW-04 | Código de confirmação tem 6 dígitos; até 5 tentativas erradas por código; pedir outro código só depois de 60 s | Limites da Meta (proteção local) |
| RW-05 | PIN de registro: exatamente 6 dígitos; nunca salvo nem mostrado | Meta |
| RW-06 | Token nunca aparece em tela nem em log; salvo só cifrado (Fernet). Sem `WHATSAPP_CHAVE_CIFRA`, os IDs são salvos e o token não, com aviso | Trato Fácil (`crypto.py`), sem derrubar o app quando falta a chave |
| RW-07 | Erro da Meta vira mensagem clara com o código do erro; a etapa não avança | — |
| RW-08 | Arquivo da conexão (`.emporio_whatsapp.json`) fora do git | RN-24 da SPEC-001 |

## 5. Critérios de aceite

- [x] **CW-01** Dado o retorno do OAuth com `state` diferente, então o login é recusado.
- [x] **CW-02** Dado um token de outro app ou sem `whatsapp_business_messaging`, então a conexão não avança.
- [x] **CW-03** Dado "(81) 99999-0000", então o cadastro envia `cc=55` e `phone_number=81999990000`.
- [x] **CW-04** Dado o código errado 5 vezes, então é preciso pedir outro; pedir outro antes de 60 s é recusado.
- [x] **CW-05** Dado o fluxo completo no provedor simulado, então a etapa termina em `conectado` e a conexão salva não contém o token em claro.
- [x] **CW-06** Dado `conectar` interrompido em `codigo_enviado`, então a próxima execução pede o código, sem refazer o login.
- [x] **CW-07** As chamadas reais usam os endpoints e parâmetros da Graph API v25.0 (testado sem rede).
