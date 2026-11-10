# Funcionalidades - Project LOKI

Estado atual do que o usuário vê e usa. Histórico fica no `CHANGELOG.md`,
decisões técnicas em `ARQUITETURA.md`, pendências em `TODO.md`.

## Personagem na tela

- Janela transparente, sempre no topo, com a Galateia animada por clipes
  (94 pastas de animação em `assets/galateia/animations/`).
- Arrastar com o mouse: ela reage com um dos loops de "sendo carregada" e, ao
  soltar, cai com física até o piso (queda de bunda, de joelho ou heroica).
- A posição é lembrada por quantidade de monitores conectados.
- Alt + clique esquerdo em qualquer ponto: ela voa até lá (modificador e
  botão configuráveis).
- Depois de alguns minutos sem teclado e mouse (10 por padrão), ela finge
  dormir; acorda quando o usuário volta.

## Comportamentos autônomos

Ligados e desligados em Configurações, aba Movimento. A autonomia geral tem
quatro níveis (parada, sutil, viva, travessuras) e pausa sozinha em tela
cheia, jogo, RDP e desktop seguro.

- **Sentar na barra de tarefas** e levantar depois.
- **Variações sentadas**: espreguiçar, bocejar, mexer no cabelo, rir.
- **Vagar pela tela**: voo curto em 8 direções, entre os monitores permitidos.
- **Ouvir música do SIREN**: enquanto uma faixa toca no SIREN, ela vai sentar
  na barra e fica balançando as pernas; não levanta nem sai vagando até a
  música parar. As variações sentadas continuam.
- Cursor Swing, Cursor Hunt e Cabo de guerra existem como opção, desligados
  por padrão (sem clipes próprios ainda).

"Movimento reduzido" remove toda autonomia e os efeitos decorativos, mantendo
conversa e estados funcionais.

## Menu SAO

Rodinha do mouse para baixo sobre a personagem abre; para cima fecha. Quatro
botões que expandem ao passar o mouse:

- **Conversar**: abre a conversa por bubbles.
- **Voz**: mostra o modo ativo (voz contínua, push-to-talk, desligada); clicar
  abre as três opções.
- **Ações**: abre a roda de gestos.
- **Configurações**: abre o modal de configurações.

## Roda de gestos (Gesture Wheel)

- Mostra as animações escolhidas pelo usuário, em páginas trocadas pela
  rodinha do mouse ou pelas setas, numeradas de 1 até o total.
- Qualquer animação pode ser pedida a partir de qualquer estado: ela faz as
  transições necessárias sozinha (por exemplo, levanta antes de voar). "Sentar"
  leva até a barra de tarefas antes de sentar.
- Ctrl+F com o mouse sobre a roda filtra por nome. Esc fecha o filtro, e de
  novo fecha a roda.
- O editor (Configurações, aba Ações) escolhe quais animações entram, a ordem
  por arraste, o limite por página e a miniatura de cada uma.

## Conversa por bubbles

- Abre clicando na personagem, pelo Menu SAO ou por Ctrl+Shift+Espaço.
- Campo de texto abaixo dela; Enter envia, Shift+Enter quebra linha. Aceita
  imagem por Ctrl+V ou pelo botão de anexo, e tem seletor de emoji.
- Respostas aparecem como bubbles ao redor da personagem, com as 3 últimas
  visíveis. Somem depois de um tempo sem atividade (15 s por padrão).
- O botão de histórico mantém todas as mensagens da sessão visíveis, com
  rolagem pela rodinha.
- Indicadores "Te ouvindo" e "pensando" acompanham o estado de voz da GAIA.
- Sem a GAIA rodando (modo demonstração), a conversa não tem para onde enviar
  e mostra um bubble de erro.

## Halo

Brilho ao redor da personagem conforme o modo de voz ativo na GAIA.

## Bandeja do sistema

Mostrar, Clique-através, Centralizar, Modo seguro (pausa a autonomia),
Velocidade de voo (100% a 500%), Forçar animação, Configurações, Reiniciar
Mascot e Sair.

## Configurações

Modal próprio, em abas:

- **Geral**: autonomia, movimento reduzido, clique-através, proteção contra
  captura de tela, minutos AFK; e o card Conversa (tempo até os bubbles
  sumirem, largura máxima do texto).
- **Aparência**: opacidade, escala, estilo do Menu SAO.
- **Ações**: editor da roda de gestos.
- **Movimento**: velocidade de voo, atalho de "ir até aqui", monitores
  permitidos, comportamentos autônomos.
- **Sistema**: orçamento de memória do cache de animações e Reiniciar.

Quase tudo aplica na hora. Escala, largura do bubble e orçamento de memória
valem depois de reiniciar o Mascot.

## Integração com a GAIA

- A GAIA sobe o LOKI como subprocesso e conversa com ele por named pipe local
  (mensagens, estado de voz, halo). Se a GAIA fechar, o LOKI fecha junto.
- Reiniciar o Mascot pela bandeja ou pelas Configurações dele mantém o vínculo:
  o processo novo informa o PID e a GAIA passa a segui-lo.
- Rodando sozinho (`iniciar_loki.bat`), entra em modo demonstração: tudo
  funciona, menos a conversa.
