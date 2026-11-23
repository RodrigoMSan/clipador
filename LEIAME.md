# Clipador

Busca os clipes mais vistos do streamer na Twitch, junta 3 a 6 clipes num vídeo de 65 a 90 segundos no padrão 9:16 (facecam em cima, gameplay embaixo, crédito do streamer e tela final com o nosso @) e envia no Telegram com os botões Aprovar, Reprovar e Editar legenda.

## Rodar na nuvem (GitHub Actions, sem PC ligado)

O arquivo `.github/workflows/clipador.yml` liga o bot nos servidores do GitHub em turnos de 6 horas, o dia todo. A cada turno ele restaura o que já foi feito (ramo `estado` do repositório), atende os botões do Telegram e monta os vídeos nos horários marcados. Os vídeos em 1080p ficam nas Releases do repositório, com link para baixar e postar.

Configuração (uma vez):

1. No repositório, vá em **Settings > Secrets and variables > Actions > New repository secret** e crie:
   - `TELEGRAM_TOKEN`: o token do BotFather
   - `TELEGRAM_CHAT_ID`: o número do seu chat
2. Na aba **Variables** (mesma tela), opcional: `CLIPADOR_ARROBA` (ex.: `@clipador`) e `CLIPADOR_HORARIOS` (ex.: `10:00,18:00`, horário de Brasília).
3. Na aba **Actions**, abra "Clipador" e clique em **Run workflow** para ligar na hora. Depois ele se religa sozinho a cada 6 horas.

Não deixe o bot ligado no PC ao mesmo tempo: dois bots com o mesmo token brigam pelas mensagens.

## Rodar no PC (dois cliques)

Dê dois cliques em **Abrir Clipador.bat**. Na primeira vez ele:

1. instala o Python e o FFmpeg, se faltarem (depois pede para abrir de novo);
2. instala os componentes do Clipador;
3. pede o token do BotFather e o nosso @, e descobre o seu chat quando você manda /start para o bot.

Das próximas vezes ele só liga o bot. A janela mostra a barra de progresso; pode minimizar. Para desligar, feche a janela.

Para mudar token, @ ou horários depois: abra o arquivo `.env` com o Bloco de Notas, ou apague o `.env` e abra o Clipador de novo para refazer a configuração.

## Usar

No chat do bot:

- `/gerar` monta um vídeo novo do alanzoka e envia para aprovação. Uma mensagem com barra de progresso mostra cada etapa.
- **Aprovar** move o vídeo para `dados/aprovados/`, de onde ele vai para a publicação.
- **Reprovar** pede o motivo. "Corte ruim" devolve os clipes para uma nova montagem; os outros motivos descartam os clipes.
- **Editar legenda**: a próxima mensagem que você mandar vira a legenda.
- `/pendentes` reenvia o que ainda não foi decidido; `/status` mostra o resumo.

- `/pausar` e `/retomar` desligam e ligam a geração automática.

O bot só responde ao chat do `TELEGRAM_CHAT_ID`.

## Rodar sozinho no seu PC

1. Teste antes com o **Abrir Clipador.bat**: mande `/gerar` e veja o vídeo chegar.
2. Feche essa janela e dê dois cliques em `instalar_inicio_automatico.bat`. A partir daí o Clipador liga sozinho, sem janela, sempre que o Windows iniciar, e religa sozinho se cair.
3. Nos horários de `CLIPADOR_HORARIOS` no `.env` (padrão 10:00 e 18:00) ele monta um vídeo e manda no Telegram. Você só aprova.
4. Para o PC não dormir: Configurações > Sistema > Energia > Suspensão: "Nunca" quando ligado na tomada.

O que acontece fica registrado em `clipador.log`. Para parar de vez, apague o arquivo `Clipador.vbs` da pasta de inicialização (o instalador mostra onde ele fica) e reinicie o PC.

Mais tarde, para rodar 24 horas sem o PC, o mesmo código vai para um servidor na nuvem.

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `config.py` | Streamers autorizados, duração, @, pastas |
| `coletar.py` | Lista os clipes mais vistos na Twitch |
| `montar.py` | Escolhe, baixa, acha a facecam, monta o 9:16 e junta |
| `telegram_bot.py` | Envia para aprovação e registra a decisão |
| `Abrir Clipador.bat` | Dois cliques: configura, instala e liga o bot com janela |
| `configurar.ps1` | Configuração inicial (token, @, chat) |
| `progresso.py` | Barra de progresso na janela e no Telegram |
| `iniciar_clipador.bat` | Liga o bot e religa se cair |
| `instalar_inicio_automatico.bat` | Faz o bot ligar junto com o Windows |
| `nuvem.py` | Salva o estado e guarda os vídeos quando roda no GitHub |
| `.github/workflows/clipador.yml` | Agenda os turnos do bot no GitHub Actions |
| `banco.py` | Guarda clipes usados e status dos vídeos (`dados/clipador.db`) |

## Limites desta versão

- A facecam é achada pelo rosto do streamer. Quando não há rosto visível (ou é uma live só de conversa), o clipe sai com o quadro inteiro no meio e fundo desfocado.
- Ainda sem legenda falada na tela (precisa de transcrição) e sem corte de silêncios.
- Publicação (Metricool) é o próximo passo: hoje o aprovado vai para a pasta `dados/aprovados/`.
