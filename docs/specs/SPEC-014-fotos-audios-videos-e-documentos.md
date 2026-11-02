# SPEC-014: Fotos, áudios, vídeos e documentos no chat

- **Status:** concluída
- **Data:** 2026-11-02
- **Autor:** Alberto Milet
- **Origem:** pergunta do usuário em 02/11/2026 ("como devemos tratar fotos, docs, áudio e vídeo conforme o desafio, lembrando que provavelmente não faremos conexão com o WhatsApp") e a recomendação aceita: reconhecer a mídia, não processá-la.

---

## 1. Problema

O desafio pede um agente de **mensagens de texto**, e o manual da loja não cita foto, vídeo nem nota fiscal em nenhum fluxo. Mesmo assim, no WhatsApp o cliente manda foto do instrumento com defeito, áudio e documento o tempo todo. Sem tratamento, o agente não teria resposta para isso.

## 2. Solução

A mídia vira um **marcador** (`[cliente enviou uma foto]`) e nunca chega ao modelo nem ao disco. A Lia responde com um texto fixo, sem chamar o LLM: por enquanto só lê texto, pede que o cliente escreva o que precisa e, se for defeito ou troca, oferece registrar a solicitação ou falar com a equipe. Se a mídia chega durante um atendimento de pedido ou de solicitação, a equipe recebe um alerta, porque aí o arquivo provavelmente importa.

## 3. Escopo

### Faz parte

- [x] `emporio.rules.midia`: tipos aceitos, marcador, texto da resposta e quando alertar a equipe (funções puras)
- [x] `Agente.receber_midia(conversa, tipo)`: resposta fixa, histórico com o marcador, alerta quando couber
- [x] Simulador: botões 📷 Foto, 🎤 Áudio, 🎬 Vídeo e 📄 Documento, que enviam só o marcador
- [x] `python -m emporio chat`: comandos `/foto`, `/audio`, `/video` e `/documento`

### **Não** faz parte

| Item | Por quê |
|---|---|
| Upload de arquivo de verdade | O desafio é de texto; e guardar mídia exigiria expurgo, máscara e exportação próprios (SPEC-012) |
| Transcrição de áudio e leitura de imagem | Exigiria outro modelo (multimodal, com ZDR) e nova comparação de modelos; fica em "com mais tempo" |
| Conexão real com o WhatsApp | Fora do protótipo (SPEC-004) |

## 4. Regras

| # | Regra |
|---|---|
| RM-01 | Tipos: `foto`, `audio`, `video`, `documento`. Outro tipo é recusado |
| RM-02 | O arquivo nunca é lido, guardado ou enviado ao modelo; o histórico e o log guardam só o marcador (minimização, LGPD art. 6º, III) |
| RM-03 | A resposta é fixa, sem chamar o LLM, e diz: só leio texto; escreva o que precisa; se for defeito ou troca, posso registrar ou passar para a equipe, com o contato da loja |
| RM-04 | Na primeira mensagem da conversa, a resposta leva o aviso de privacidade (SPEC-012) |
| RM-05 | Se a sessão tem pedido verificado, solicitação proposta ou registrada, a equipe recebe um alerta "cliente enviou {mídia}" e a conversa fica marcada como aguardando vendedor |
| RM-06 | Com um vendedor atendendo, a Lia não responde: o marcador fica no histórico para o vendedor |
| RM-07 | A mídia conta no limite de mensagens por conversa (SPEC-013 RS-05) |

## 5. Critérios de aceite

- [x] **CM-01** Uma foto no início da conversa recebe a resposta fixa com o aviso de privacidade, sem chamada ao LLM.
- [x] **CM-02** Uma foto depois de verificar um pedido gera alerta para a equipe e marca a conversa como aguardando vendedor.
- [x] **CM-03** O SQLite guarda `[cliente enviou uma foto]`, sem arquivo.
- [x] **CM-04** Na mensagem seguinte em texto, o modelo vê o marcador no histórico e pode continuar o assunto.

## 6. Limitações

- O cliente que só manda áudio precisa digitar; isso é uma perda real de experiência no WhatsApp.
- O alerta depende do contexto da sessão; uma foto de defeito mandada antes de qualquer pedido não gera alerta.
