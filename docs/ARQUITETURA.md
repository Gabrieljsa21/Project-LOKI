# Arquitetura - Project LOKI

Retrato ATUAL de como o LOKI é construído e por quê - editado por cima
quando uma decisão muda, nunca acumula histórico (isso é trabalho do
`CHANGELOG.md`; o que falta fazer é trabalho do `TODO.md`). Não existe
mais um documento de "plano" separado - o antigo `PLANO.md` (design de
antes da extração) foi triado e descontinuado em 2026-09-03: decisão
estrutural ainda válida virou seção aqui, achado/correção datada já
estava no `CHANGELOG.md` da GAIA, e protocolo aspiracional nunca
implementado foi descartado (`core/mascot_events.py` é a fonte de
verdade do protocolo real).

## Por que Python/PySide6 (spike 2026-08-28)

Comparado contra C#/.NET (WPF) - os dois únicos toolchains já instalados
nesta máquina - com um spike mínimo carregando um asset real numa janela
transparente/sempre-no-topo/clique-através. Python venceu em CPU (~1,6%
vs ~2,8%), memória (~80MB vs ~203MB), threads (5 vs 15) e qualidade de
renderização (o WPF vazou memória recriando `CroppedBitmap` por frame e
ainda saiu com bug de compositing de alpha que o Qt nunca teve). Combinado
com o pipeline de assets já pronto em Python e o LOKI nunca sendo
distribuído a terceiros (reduzindo a vantagem de empacotamento do .NET a
quase nada aqui, diferente do Argus - candidato real a C#/.NET
justamente por ser distribuído), a escolha foi clara.

## Princípios de design

1. **Assets reais antes de arquitetura imaginária** - o motor segue o formato que já existe, nunca o contrário.
2. **Autonomia rara, não hiperatividade** - movimento deve parecer vontade, não timer repetitivo.
3. **Animação dirigida, física contida** - clipes definem pose; física move o corpo inteiro (sem rig articulado por camadas).
4. **Transições válidas** - o scheduler nunca troca clipes incompatíveis (`transicoes_validas_a_partir_de`).
5. **O usuário sempre vence** - clique, `Esc`, arraste ou heartbeat perdido cancelam qualquer interação/comportamento autônomo.
6. **Falha isolada** - se o Mascot morrer, a GAIA continua funcionando normalmente.
7. **Movimento reduzido é requisito** - `reduce_motion` remove autonomia/efeitos decorativos, nunca chat ou estados funcionais.
8. **Uma personagem, não uma colônia** - nunca mais de um clipe tocando ao mesmo tempo pra ela (a janela efêmera do Voo do Caos, `chaos_flight.py`, existe por isso - o "caos" é uma entidade separada, não uma 2ª Galateia).
9. **Sem ações irrestritas** - o Mascot não executa shell, aplicativos nem ferramentas da GAIA; é presença visual, não um 2º agente.
10. **Segurança nunca depende de boa vontade** - nunca `BlockInput`; autonomia pausa sozinha em fullscreen/jogo/RDP/desktop seguro; um eventual hook de mouse (Tug of War) sempre libera por clique/Esc/arraste/watchdog, nunca só por confiar que vai soltar.

### Proteção opcional contra captura (2026-09-07)

O config `proteger_de_captura` é opt-in e desligado por padrão. Quando ativo, `platform_windows.py` pede ao Windows `WDA_EXCLUDEFROMCAPTURE` para todas as janelas superiores do LOKI: personagem, CompanionPanel, bubbles e composer. A aplicação também ocorre quando uma janela nova nasce; desativar usa `WDA_NONE` em todas as existentes.

A API depende do suporte do Windows e do aplicativo capturador. Qualquer falha retorna estado inativo sem derrubar a interface. O modal deixa essa limitação visível; validação automatizada cobre ativação, desativação e fallback, enquanto a matriz real de screenshot/Discord/OBS permanece no TODO.

### Estado musical recebido do SIREN (2026-09-07)

`mascot/playback_events.py` recebe por UDP local o schema `siren.playback.v1`. Ele valida tipo, sessão, faixa e sequência, descarta eventos repetidos ou atrasados e entrega o estado no thread principal do Qt. `MascotApp.playback_state` mantém faixa, pausa, posição e duração sem criar um segundo player.

O receptor só oferece contexto para uma reação visual futura. Nenhuma animação ou cena foi escolhida automaticamente nesta etapa; essa camada deverá respeitar `reduce_motion` e continuar usando o SIREN como fonte única de reprodução, fila e histórico.

## Por que repositório próprio (extraído em 2026-09-03)

Decisão tomada em 2026-08-29, antes mesmo de qualquer código do Mascot
existir fora do `assistant`, por três motivos concretos:

- **LOKI é uma presença visual opcional da GAIA**, separada do cérebro, da memória, das ferramentas e da voz.
- **Animações são pesadas e só crescem** - `.webp`/binários dentro do `assistant` inflariam o repo principal pra sempre, mesmo pra quem só quer a GAIA sem o Mascot.
- **Privacidade** - fronteira mais limpa entre "cérebro pessoal" (GAIA, dados sensíveis) e "presença visual" (LOKI), útil se um dia um precisar ficar mais compartilhável que o outro.

Executado quando 148MB/91 clipes já pesavam de verdade no repo principal.

## Responsabilidades (GAIA vs Mascot)

| GAIA | Mascot |
|---|---|
| persona, memória, ferramentas, LLM | clipe, pose e efeito visual |
| turnos e prioridades de conversa | animação, física e movimento local |
| playback de voz (TTS) | reação à amplitude/eventos de voz |
| permissão de behaviors (config) | execução segura dos behaviors |
| conteúdo do chat | renderização do CompanionPanel |
| supervisiona o subprocesso (liga/desliga) | heartbeat, readiness, modo demonstração |

## Desempenho atual

Medido isolado via `psutil` (não CPU/memória do sistema todo),
autonomia "viva": ~0,5% CPU médio / ~7,8% de pico (mesma ordem do idle
puro - indício de ruído de warmup/GC, não custo real dos behaviors).
Memória converge pra orçamento configurável (padrão 320MB) + ~30MB de
overhead do interpretador/Qt + a base fixa PERMANENTE em cache
(`AssetRepository.definir_pinados`) - **~442MB** (2026-09-04, achado ao
vivo: "ela trava ate p sentar... antes ela rodava lisa" - só as
TRANSIÇÕES de entrada de movimento/arraste/sentar/leque estavam pinadas,
nunca os LOOPS de repouso que tocam logo depois, então podiam ser
despejados e recarregar - travando - de novo; ver `CHANGELOG.md` pro
achado completo). O conjunto pinado hoje é as 8 direções de voo +
agarrar + sentar + leque (transições de entrada) MAIS os 6 clipes com a
tag `"idle"` no catálogo (os loops de repouso reais de flutuando/sentada/
leque) - 17 clipes ao todo, o resto do orçamento cobre o que estiver
tocando fora deles. Histórico completo da investigação (por que 320MB, os
bugs de cache que inflavam memória sem motivo) está no `CHANGELOG.md` da
GAIA; o achado dos loops de repouso não pinados está no `CHANGELOG.md`
deste repo (2026-09-04).

## Processo separado, protocolo explícito

`mascot/process_main.py` é uma aplicação Qt própria (`QApplication`
própria, nunca compartilhada com a GAIA) - roda como subprocesso,
supervisionado por `assistant/integrations/mascot/supervisor.py` do lado
da GAIA. A fronteira entre os dois é um protocolo EXPLÍCITO (JSON
delimitado por `\n` sobre `QLocalSocket`, named pipe local do Windows,
nunca porta TCP) - de propósito, pra nunca acoplar a UI visual ao
"cérebro" da GAIA. Handshake com token efêmero (gerado a cada boot pelo
supervisor, nunca fixo), heartbeat periódico, reconexão com backoff.

`core/mascot_events.py`/`mascot/protocol/transport.py` (aqui) e
`core/mascot_events.py`/`core/mascot_transport.py` (no `assistant`) são
CÓPIAS deliberadas do mesmo contrato - pequenos o bastante (138/63
linhas) pra não valer uma dependência formal entre repos; se um evento
novo for adicionado num lado, precisa ser replicado no outro.

## Contrato de asset (`mascot/asset_repository.py`)

Toda animação compartilha a MESMA geometria de célula/pivô
(`assets/galateia/animations/geometry.json`) - garante que a personagem
nunca "salta" ao trocar de clipe. `AssetRepository` descobre pastas com
`animation.json` válido, valida schema/dimensões/quantidade de células,
carrega sob demanda com cache LRU limitado por ORÇAMENTO DE MEMÓRIA real
(MB decodificados, não tamanho comprimido do `.webp` - configurável via
Painel da GAIA, `data/mascot_config.json::mascot_config.memoria_
orcamento_mb`), e cai pro fallback seguro (`flutuando_idle`) se um asset
falhar. `obter()` (síncrono, bloqueia a thread chamadora) é só pro
cold-start; todo caminho de RUNTIME usa `garantir_carregado_assincrono`
- essa regra tinha uma exceção não documentada (`BehaviorScheduler.
_iniciar_hop` usava `obter()` pros 3 clipes de cada salto, travando a UI
por até ~1,5s quando não estavam em cache) corrigida em 2026-09-04, ver
`CHANGELOG.md`.

## Grafo de estados (`mascot/state_catalog.py`)

Cada clipe é uma `EstadoAnimacao` (origem/destino/fallback/interrompível/
tags/multiplicador de velocidade) - dois catálogos convivem: entradas
HARDCODED neste módulo (histórico) e entradas DECLARATIVAS carregadas de
`data/animacoes_galateia.json` (`state.*` no manifesto de cada clipe) -
uma entrada explícita no Python sempre vence uma declarativa com o mesmo
id. `AnimationController.solicitar_transicao` só aceita ids cujo
`estado_origem` bate com o estado atual (`transicoes_validas_a_partir_
de`) - nunca toca algo fora do grafo.

`velocidade_multiplicador` é declarativo (não um argumento de quem chama
a transição) - fonte única da verdade sobre "esse clipe toca mais rápido
que o normal", lida pelo `AnimationController` não importa quem pediu a
transição (arraste real, `forcar_estado`, ou a bandeja do sistema).

## Config e dados (própria, desde a extração)

`mascot/config.py` lê/escreve `data/mascot_config.json` (chaves
`mascot_config`/`mascot_behaviors_config`) e `mascot/window.py` lê/
escreve `data/mascot_posicao.json` (posição salva por quantidade de
monitores conectados) - os dois SEMPRE relativos à raiz deste repo
(`Path(__file__).resolve().parents[1]`), nunca da GAIA. O Painel da GAIA
("🧚 Mascot (LOKI)") acessa o MESMO `mascot_config.json` direto por
caminho de arquivo (`assistant/integrations/mascot_config_client.py`,
resolvido via `PROJETO_LOKI_DIR`/pasta irmã padrão) - nunca um import
Python cruzando repositórios, já que os dois processos rodam em
venvs/interpretadores diferentes.

## Modal de configurações nativo (`mascot/modal_configuracoes.py`)

Fonte única de configuração desde 2026-09-03 (antes vivia só no modal
"🧚 Mascot (LOKI)" do Painel da GAIA) - pedido do usuário: "o loki tem que
conseguir se virar sozinho". `mascot/qt_widgets.py` é uma cópia deliberada
TRIMADA de `assistant/ui/qt_widgets.py` (mesmo raciocínio de `core/
mascot_events.py` acima, mesmo padrão de `Project-IRIS/iris/ui/qt_widgets.py`)
- só os widgets/helpers genuinamente usados aqui, zero dependência de GAIA.

Instância ÚNICA e persistente em `MascotApp._abrir_configuracoes` (`.show()`,
não `.exec()`) - acessível pela bandeja ("⚙️ Configurações...") e pelo item
"Configurações" do Menu SAO, os dois chamam o MESMO método. Como o modal roda no
MESMO processo que já lê `config_mascot`/`config_behaviors` POR REFERÊNCIA
a cada ciclo (`BehaviorScheduler`/`MascotWindow`), a maioria dos campos
aplica ao vivo, sem precisar reiniciar nada - só Escala e Orçamento de
memória (`AssetRepository`) continuam exigindo reinício, por não terem
caminho de "aplicar ao vivo" nesses dois componentes.

O modal "🧚 Mascot (LOKI)" da GAIA virou um atalho FINO: só o switch
"Ativado" (liga/desliga o SUBPROCESSO em si - só ela pode fazer isso, via
`MascotSupervisor`) e um botão que manda `mascot_events.
evento_settings_requested()` pelo bridge pedindo pro Mascot mostrar o
próprio modal - a GAIA nunca duplica os campos de configuração, só "vê" o
modal de lá e aciona.

## Nível 2 "Voz" do Menu SAO (`mascot/menu_sao.py`, corrigido 2026-09-06)

O item **Voz** deixou de ciclar o modo direto no clique (comportamento
original) - gerava ambiguidade entre "o texto mostra o estado atual" e "o
texto mostra a ação que vai executar". Agora o Nível 1 é só um INDICADOR
permanente do modo ativo (ícone `◉`/`🎙`/`⊘` + rótulo, lidos de
`companion_panel.modo_voz_atual`/`MODOS_VOZ_GLIFO`/`MODOS_VOZ_TEXTO` e
mantidos em sincronia pelo sinal `modo_voz_alterado`) e o clique abre um
**Nível 2**, substituindo temporariamente a coluna principal pelas 3
opções de voz + "‹ Voltar" (mesma coluna/pílulas do Nível 1, troca
INSTANTÂNEA, sem stagger próprio). A opção ativa recebe um destaque
permanente no contorno (`_CirculoMenu.definir_marcado`). Selecionar uma
opção chama `companion_panel.definir_modo_voz(modo)` (aplica na hora,
nunca uma 2ª captura) e retorna ao Nível 1 sozinho; "Voltar" ou Escape
fazem o mesmo sem mudar o modo. `companion_panel.py` continua sendo a
ÚNICA fonte de verdade do modo de voz - o Menu SAO nunca guarda estado
próprio, só lê/aciona.

## Conversation Overlay / "Bubble Mode" (`mascot/conversation_overlay/`, 2026-09-06)

Pedido do usuário: a conversa deixou de abrir um `CompanionPanel` grande
por padrão e passou a acontecer AO REDOR da própria GAIA - bubbles
flutuantes acima dela + um `InputBar` compacto abaixo, identidade visual
PRÓPRIA (navy/cristal-ciano/dourado discreto, `conversation_overlay/
estilo.py` - deliberadamente separada da paleta preta/dourada do
`companion_style.py`, usada só pelo painel tradicional).

**Camadas do pacote** (nomes sugeridos pelo próprio pedido):
`bubble.py` (`Bubble`/`IndicadorVoz` - pintados à mão, mesma técnica de
`menu_sao.py::_CirculoMenu`/`halo.py`, cada um sua PRÓPRIA janela
top-level como `CompanionPanel`/`MenuSAO` - necessário pra `move(x, y)`
valer em coordenadas absolutas de tela, já que `BubbleStack` reposiciona
cada bubble independente conforme a pilha cresce/encolhe) `>`
`bubble_stack.py` (`BubbleStack` - guarda só as últimas 3 mensagens,
empurra as antigas pra cima com fade E perda de destaque (opacidade de
repouso menor por distância do mais novo), timeout de inatividade de
15s, indicador de voz é singleton) `>` `input_bar.py` (`InputBar` -
único widget com `QLineEdit` de verdade, herda pintura/fade de `bubble.
_BolhaBase`) `>` `conversation_controller.py` (`ConversationController` -
ciclo de vida completo: `idle` `<->` `ativo` `<->` `ouvindo`/`processando`,
estados como STRING simples, mesmo estilo de `menu_sao.py::_estado`) `>`
`positioning.py` (`character_safe_rect`/regiões candidatas/decisão de
layout - 100% reaproveita `platform_windows.obter_work_area_da_tela`/
margem vazia do asset pra geometria, nunca duplica cálculo de
monitor/DPI).

**Posicionamento - reescrito 2026-09-06** (correção do usuário: a v1
ancorava o `InputBar` em `GAIA.bottom + gap` clampado só contra a work
area, sem NENHUMA zona de exclusão contra a própria GAIA - sentada na
barra de tarefas, sem espaço "abaixo", o clamp deslizava a barra de
volta pra CIMA do corpo dela). Modelo novo, estrutural:
1. `character_safe_rect` - bounding box VISÍVEL da GAIA (silhueta real,
   descontando margem vazia do asset, mesmo truque de `menu_sao.py::
   _calcular_ancoragem`) + margem de segurança (12px) - lida do asset
   ATUAL a cada chamada, acompanha pose/escala sozinha (flutuando/
   sentada/deitada/transformada/escala diferente), nunca hardcoded.
2. `regioes_candidatas` - 4 faixas de espaço LIVRE ao redor do safe rect
   (acima/abaixo/esquerda/direita), recortadas pela work area.
3. `escolher_layout_conversa` - decide UM lado pra bubbles+composer
   JUNTOS (nunca um de cada lado - "GAIA + bubbles + composer formam um
   pequeno sistema de layout ao redor dela"): tenta o vertical canônico
   (bubbles acima, composer abaixo - cabem de forma independente); se
   qualquer um dos dois não couber, os DOIS migram JUNTOS pra uma coluna
   lateral única (o lado com mais espaço), empilhados na mesma coluna -
   nunca atravessa/cobre o safe rect, mesmo em telas minúsculas ou
   GAIA/pose gigante (degrada saindo da work area no pior caso extremo,
   nunca invadindo a personagem). Decidido UMA VEZ por sessão de conversa
   (`ConversationController.entrar`, usando uma estimativa de PIOR CASO
   pro tamanho da pilha de bubbles) - o lado nunca muda no meio de uma
   troca de mensagens.

**Integração com o Menu SAO/clique direto**: "Conversar" (`menu_sao.py`)
e o clique direto na GAIA (`window.py::clicada`) agora chamam
`ConversationController.alternar()` em vez de abrir o `CompanionPanel`
direto - o painel tradicional (histórico completo, sem limite de
tamanho) virou o destino do "Ver completo" de um bubble que estourou
`bubble.ALTURA_MAXIMA_TEXTO` (`expandir_solicitado` -> `companion_panel.
mostrar_ancorada`), reaproveitando o MESMO caminho de envio
(`companion_panel.enviar_mensagem`, extraído de `_enviar` pra nunca
duplicar lógica) - o histórico do painel continua populado
silenciosamente mesmo escondido, então "Expandir" já abre com contexto
completo.

**Voz** (`ConversationController.notificar_estado_semantico`, chamado em
CIMA do MESMO `state_changed` que já existia, sem protocolo novo):
"listening"/"transcribing"/"thinking" mostram um indicador compacto
("🎙 Te ouvindo..."/"✦ Deixa comigo..."), ATIVANDO a conversa sozinha se
ela ainda não estava ativa (sem roubar foco de teclado - o usuário pode
só estar falando, sem olhar pro teclado).

**Wander/drag/autonomia**: MESMO padrão de bloqueio por motivo
(`SafetyController.bloquear_autonomia("conversation_overlay")`) que
`CompanionPanel`/`MenuSAO` já usam - o reset de cooldown do Wander ao
liberar já é genérico (`BehaviorScheduler` escuta `autonomia_alterada`),
nada novo precisou disso. Arraste real (`window.arraste_iniciado`) chama
`ConversationController.fechar_imediato()` - mesmo corte de `menu_sao.py::
fechar_tudo(imediato=True)`, nunca deixa bubble "preso no ar".

**Pipeline de conversa - confirmado 2026-09-06** (usuário pediu pra
verificar antes de mexer mais, achando que era mock): `InputBar.
enviar_solicitado` -> `ConversationController._ao_enviar_texto` (bubble
do usuário na hora) -> `texto_enviado` -> `companion_panel.
enviar_mensagem` -> `evento_chat_submitted` real pro bridge - MESMO
caminho que o `CompanionPanel` sempre usou, nunca um sistema de chat
separado. `run.py::_processar_chat_mascot_async` chama o MESMO
`despachar_turno` da voz, que já dispara `state_changed:"thinking"` pra
QUALQUER turno (não só voz) - por isso o indicador "✦ Deixa comigo..."
já aparece pra mensagens de TEXTO também, sem precisar de protocolo novo
(`ConversationController.notificar_estado_semantico` já escutava isso
pensando só em voz). Sem streaming de verdade hoje (`evento_assistant_
message` sempre com `id` novo e `final=True`, confirmado lendo `run.py`)
- o fluxo é sempre "Pensando..." -> texto completo de uma vez, nunca
atualização incremental do mesmo bubble.

**Erro de envio** (2026-09-06) - falha LOCAL (bridge indisponível/GAIA
desconectada, nunca vai existir uma resposta pra esse turno) agora tem
bubble PRÓPRIO (`Bubble` remetente `"erro"`, borda/texto em `estilo.ERRO`,
mesma assinatura da GAIA) - `CompanionPanel.falha_envio` (sinal novo) ->
`ConversationController.receber_erro`; antes esse aviso só existia no
histórico invisível do painel, nunca aparecia no Bubble Mode.

**InputBar reage a hover/foco** (2026-09-06, correção do usuário: "ainda
parece um campo Qt jogado na tela" - borda/glow eram ESTÁTICOS) -
`_atualizar_borda` alterna entre 3 estados (repouso quase sem destaque,
hover discreto, foco com glow leve) via `_BolhaBase.redefinir_borda`
(nova) - progressão sutil, nunca um brilho permanente.

**"Retângulo interno" ao digitar - causa real** (print real do usuário,
2 rodadas no mesmo dia até achar a causa certa: "n quero q fique esse
retangulo interno qnd começo a digitar"). 1ª tentativa (`outline: none`
no QSS do `QLineEdit`, teoria "retângulo de foco do Fusion") NÃO
resolveu - usuário confirmou com um 2º print, mesmo depois de reiniciar.
Causa de verdade: `_BolhaBase._glow` (`QGraphicsDropShadowEffect` de
TODO bubble/composer) usava `QColor(hex)` sem alpha pra cor da sombra -
nasce OPACA (255) por padrão. Com `offset(0, 0)` e blur > 0 (é assim que
hover/foco do `InputBar` funcionam, `redefinir_borda` aumenta o blur), uma
sombra OPACA desenha uma cópia borrada mas SÓLIDA da própria silhueta
bem colada na borda de verdade - parece um contorno/retângulo extra,
mais visível exatamente quando o campo ganha foco (blur maior, doc:
"aparece quando estou digitando"). Corrigido dando alpha 0.5 à cor do
glow - glow de verdade (translúcido), nunca um 2º contorno sólido.
`outline: none` continua no QSS (não fazia mal, só não era a causa).

**Botão de histórico** (2026-09-06, pedido do usuário: "ainda falta uma
forma de habilitar p mostrar histórico das mensagens q mandei e q ela
respondeu") - antes só existia o "Ver completo" de um bubble específico
que estourou o limite; agora o `InputBar` tem um botão próprio (🕘,
secundário - `TEXTO_SECUNDARIO`, nunca disputa destaque com o botão de
enviar) que abre o histórico completo a qualquer momento, mesmo sem
nenhum bubble estourado. `ConversationController.abrir_historico_completo`
é o caminho ÚNICO compartilhado por esse botão E pelo "Ver completo" de
um bubble - nunca duas lógicas fazendo a mesma coisa.

**Bubbles nunca ficavam visíveis apesar da mensagem/resposta funcionarem
de verdade** (achado ao vivo 2026-09-06, print real: usuário mandou uma
pergunta, a resposta chegou certinho no histórico do `CompanionPanel`,
mas nenhum bubble apareceu acima do composer) - não reproduzido offscreen
(fluxo completo com bridge fake mostra bubble corretamente, inclusive com
resposta atrasada além do timeout de inatividade - estado nunca reverte
sozinho). Suspeita principal: `Bubble`/`IndicadorVoz`/`InputBar` são
janelas top-level PRÓPRIAS sem parent (ver docstring de `bubble.py`) -
`WindowStaysOnTopHint` sozinho não garante posição relativa entre VÁRIAS
janelas "sempre no topo" concorrentes (outro app também always-on-top,
ex. overlay de app de chat) - `entrar()` (`_BolhaBase`) ganhou um
`raise_()` explícito depois do `show()`. Logging novo (`logging.
getLogger(__name__)` em `conversation_controller.py`/`bubble_stack.py`,
grava em `data/mascot.log` como o resto do Mascot) registra estado antes/
depois de `entrar`/`sair`/`fechar_imediato`/envio/resposta e a posição
exata de cada bubble criado - se acontecer de novo, o log tem a resposta
em vez de precisar adivinhar por print de tela.

**Confirmado com o log real** (2ª rodada, mesmo dia) - usuário está em
MULTI-MONITOR (GAIA numa tela secundária, `regiao`/`composer_pos` com x
na casa dos milhares) - o log mostrou os 2 bubbles criados com `visivel=
True` em coordenadas plausíveis, bem perto do composer que FUNCIONA
(mesma vizinhança de x). `raise_()` imediato (1ª tentativa) não resolveu
sozinho. Suspeita refinada: achado conhecido do Qt/Windows - `raise_()`
no MESMO tick de `show()` pode ser um no-op se o HWND nativo ainda não
foi mapeado - `QTimer.singleShot(0, self.raise_)` adicionado (empurra o
raise pro PRÓXIMO ciclo do event loop), em CIMA do `raise_()` imediato
(os dois juntos, nenhum removido - não dá pra confirmar qual resolve sem
tela real). Log também ganhou a geometria de verdade da GAIA (posição/
escala/tela) em `entrar()`, e o log de posicionamento de bubble passou a
registrar o ALVO calculado (`_reposicionar`) em vez da posição
transitória pré-animação (achado ao vivo: o log antigo fazia parecer que
o bubble mais novo nascia ACIMA do mais antigo - era só o valor lido
ANTES da animação de entrada assentar).

**Causa real da invisibilidade, achada com o log** (3ª rodada, mesmo dia
- usuário testou em monitor PRINCIPAL e SECUNDÁRIO, os dois falharam,
descartando de vez qualquer teoria específica de multi-monitor/DPI/
z-order-entre-apps): `QGraphicsDropShadowEffect` (`QGraphicsEffect`)
aplicado a uma janela TOP-LEVEL frameless `WA_TranslucentBackground` é
uma combinação conhecida por falhar silenciosamente no compositor do
Windows - a janela existe, `isVisible()` reporta `True`, ocupa a posição
certa (confirmado pelo log - bubble sempre "criado"/"visivel=True" com
coordenadas plausíveis), mas o conteúdo nunca é de fato pintado na tela.
Isso explica por que só o `InputBar` "funcionava": ele é construído bem
no início do `ConversationController` e só é mostrado bem depois (muitos
ciclos de event loop entre construção e 1º `show()` de verdade), enquanto
`Bubble`/`IndicadorVoz` são construídos E mostrados no MESMO instante -
mesma classe (`_BolhaBase`), mesmo efeito, timing diferente expondo o
mesmo bug de compositing. Corrigido removendo o `QGraphicsDropShadowEffect`
por completo - glow agora é pintado À MÃO em `paintEvent`
(`_BolhaBase._desenhar_glow`, um traço largo translúcido por baixo do
traço nítido da borda) - MESMA técnica já comprovada de `halo.py`
(`QRadialGradient` num `QPainter` comum, sem efeito gráfico nenhum,
usado há tempos no `MascotWindow`, também top-level translúcido, sem
NUNCA apresentar esse problema).

**Polimento visual** (2026-09-06, pedido do usuário depois do fluxo já
funcionar: "o Bubble Mode agora está funcional, mas visualmente ainda
parece um protótipo... quero que deixe de parecer 'três QWidgets
estilizados' e passe a parecer uma única linguagem de interação criada
especificamente para a GAIA") - `positioning.py`/`character_safe_rect`/
`escolher_layout_conversa` NÃO foram tocados (pedido explícito: "não mexa
novamente no algoritmo estrutural... se ele já está passando nos
testes"), só as constantes de espaçamento (`GAP_ENTRE_ELEMENTOS`
10→14px):

- **Largura por CONTEÚDO** (`bubble.py`) - `LARGURA_PADRAO` virou o TETO
  (nunca mais a largura fixa de todo bubble); cada `Bubble` mede o
  próprio texto e usa `clamp(natural, LARGURA_MINIMA=90, LARGURA_PADRAO
  =300)`. "Olá" e uma resposta de 3 linhas não ocupam mais a MESMA caixa.
- **Alinhamento por remetente** (`bubble.alinhamento` + `bubble_stack.
  _x_alinhado`) - usuário à DIREITA, GAIA à ESQUERDA, dentro do MESMO
  envelope de largura que `eixo_perpendicular` já ancorava corretamente
  (nunca recalcula region/monitor/DPI - só desloca dentro da coluna já
  decidida).
- **Hierarquia de cor** (`estilo.BORDA_NEUTRA`, novo) - bubble da GAIA
  deixou de usar borda CRISTAL (agora reservada pro usuário/interação/
  foco) - usa uma borda neutra, o destaque dela vira só a assinatura
  dourada. Bordas mais finas (1.0px em repouso, só o `InputBar` varia até
  1.6px focado - `redefinir_borda` ganhou um 4º parâmetro `largura_px`).
- **Assinatura `✦` virou elemento visual PRÓPRIO** (`ALTURA_CABECALHO_
  ASSINATURA`) - uma linha inteira acima do texto (dourada, fonte maior),
  nunca mais colada como prefixo na primeira palavra do texto.
- **Timestamp discreto** (`Bubble._hora_criacao`, `ALTURA_RODAPE`) -
  sempre no rodapé, `TEXTO_SECUNDARIO` com alpha baixo; "Ver completo ›"
  passou a dividir a MESMA linha em vez de uma reserva de altura
  condicional própria.
- **Espaçamento agrupado** (`GAP_MESMO_AUTOR=5` / `GAP_TROCA_AUTOR=10`,
  substituindo o `GAP_ENTRE_BUBBLES` único de antes) - mesmo autor
  consecutivo fica mais perto (grupo conversacional), trocar de autor
  abre mais espaço.
- **Indicador "processando" virou só `✦` + reticências** (antes "✦ Deixa
  comigo...") - "prefiro três pontos animados a manter um texto grande".
  Reticências trocaram de `.` pra `•`.
- **"Morph" aproximado indicador->resposta** (`Bubble.entrar(...,
  deslizar=False)`, `BubbleStack.adicionar_mensagem` rastreia se HAVIA
  indicador ativo) - são objetos Qt DIFERENTES (não dá pra transformar
  um no outro de verdade sem unificar as classes, decisão consciente de
  não fazer isso agora) - a aproximação é o bubble de resposta entrar SEM
  o deslizamento padrão, só fade "no lugar", em vez de destruir+recriar
  com o slide normal.
- **Composer com ícone único** (`InputBar`) - o botão de histórico (🕘)
  virou `✦` (MESMO glifo dourado da assinatura da GAIA) - resolve
  "histórico" e "identidade visual" com UM ícone só, nunca uma barra de
  ferramentas permanente.
- **Deliberadamente NÃO implementado** (pedido explícito do usuário,
  ambos opcionais no próprio doc): cauda de speech-bubble (ficou só com
  o símbolo `✦`) e "morph" de verdade via unificação de classes (a
  aproximação acima já entrega a sensação sem a complexidade de fundir
  `IndicadorVoz`/`Bubble`). **Nunca foi adicionado um painel/fundo por
  trás de bubbles+composer** - cada um continua sendo uma janela
  independente flutuando sobre o desktop, exatamente como o usuário
  pediu pra nunca mudar ("isso simplesmente recriaria o CompanionPanel
  sem título").

**Ajustes ao vivo 2026-09-07** (print real do usuário: uma resposta de 1 frase quebrou em 2 linhas estreitas sem necessidade, "dava p ter mandado em 1 linha"). `bubble.LARGURA_PADRAO` (o teto de largura de todo bubble) subiu de 300 para 380px. `character_safe_rect`/`escolher_layout_conversa` continuam intocados - só a constante mudou.

O bubble da GAIA ganhou um retrato de verdade no cabeçalho da assinatura (`assets/avatar_galateia_chat.png`, circular, 26px). Isso reverte a decisão original do Bubble Mode de nunca usar retrato. O usuário pediu explicitamente ("acho interessante coloca a foto da gaia nas mensagens dela"). Se o arquivo não existir, o bubble volta a usar o glifo dourado `✦` - nunca quebra por causa de um asset ausente. O bubble de erro continua só com o glifo, nunca o retrato, porque é aviso do sistema, não a GAIA respondendo de verdade.

**Retrato movido pra FORA do balão, no mesmo dia** (o usuário mandou uma referência visual: "esta assim hj [print do estado inline] queria q ficasse assim [print de referência]"). A referência mostrava três diferenças em relação à 1ª versão do retrato: o avatar fica ao LADO do balão, bem maior, não mais dentro de um cabeçalho interno; o usuário também tem um avatar (não só a GAIA); e as duas bordas (GAIA e usuário) brilham no mesmo ciano vívido, não mais uma borda neutra pra GAIA. As três mudanças foram implementadas:

- `bubble.TAMANHO_AVATAR` subiu de 26 para 60px e passou a ser desenhado FORA do retângulo do balão (`Bubble._desenhar_avatar`) - à esquerda pra GAIA/erro, à direita pro usuário. `_area_bubble`/`_x_bubble` (novos, em `_BolhaBase`/`Bubble`) guardam o retângulo do balão em si, deslocado pra abrir espaço pro avatar - fundo/borda/glow/texto/rodapé usam esse retângulo, nunca mais o widget inteiro. `LARGURA_AVATAR_AREA` (avatar + respiro) é descontada do orçamento de texto, e `LARGURA_PADRAO` subiu de 380 para 450 (380 + a reserva do avatar) - o teto do WIDGET INTEIRO continua sendo respeitado, então o invariante que `bubble_stack.py`/`positioning.py` dependem (nenhum item sai do envelope decidido por `escolher_layout_conversa`) nunca foi quebrado - **nem `bubble_stack.py` nem `positioning.py` precisaram mudar uma linha**.
- O usuário ganhou um avatar genérico (círculo cristal + silhueta simples desenhada à mão, sem precisar de nenhum asset novo) - antes só a GAIA/erro tinham avatar (cabeçalho de assinatura). Um brilho `✦` decorativo pequeno acompanha qualquer avatar, dourado pra GAIA/erro e cristal pro usuário, mesmo toque visual da referência.
- A borda do bubble da GAIA voltou a ser CRISTAL (era `estilo.BORDA_NEUTRA`, removida - ficou sem uso). Isso reverte a "hierarquia de cor" de 2026-09-06 ("cristal é só do usuário/interação, GAIA usa borda neutra") - a referência mostrou as duas bordas com o mesmo brilho, e a identidade própria da GAIA passou a vir do retrato (fora do balão, com o próprio anel dourado/azul pintado no arquivo), não mais do contorno. Os bubbles de mensagem (`gaia`/`usuario`/`erro`) também ganharam glow de verdade pela primeira vez (`_intensidade_glow`, antes só `InputBar` variava isso) - a cor do glow é derivada da própria cor da borda de cada um, então `erro` ganha um halo vermelho coerente de graça.
- O cabeçalho de assinatura interno (`ALTURA_CABECALHO_ASSINATURA`, uma linha reservada dentro do balão) foi removido - o avatar substitui essa função inteiramente, agora do lado de fora. Bubbles ficaram um pouco mais baixos como efeito colateral (menos uma reserva vertical fixa).

**Composer: largura igual ao bubble, campo multi-linha, anexo de imagem, emoji - mesmo dia** (pedido do usuário: "aumenta o tamanho do campo de digitar mensagem p ficar do tamanho da fala da gaia. E quero poder usar ctrl+v p enserir imagem nesse chat. E q aumente a altura p caber mais linhas... falta um botão de selecionar anexo e daqueles emoji", com referência visual de um composer com histórico/campo/anexo/emoji/enviar). `input_bar.py` reescrito:

- `LARGURA_PADRAO` do composer passou a ser literalmente `bubble.LARGURA_PADRAO` (450) - fonte única, nunca mais dois números soltos que por acaso combinavam.
- O campo virou `QPlainTextEdit` (era `QLineEdit`) - multi-linha, Enter envia/Shift+Enter quebra linha (`eventFilter`, mesmo mecanismo que já tratava Escape). Cresce em altura conforme o texto quebra linha (mede com `QFontMetrics.boundingRect`/`TextWordWrap`, mesma técnica de `bubble._truncar_para_altura`, em vez de mexer no layout interno do `QTextDocument`) até um teto de `ALTURA_MAXIMA_LINHAS` (4) linhas. O `InputBar` inteiro (janela top-level própria) cresce junto (`_atualizar_geometria`) sempre pra BAIXO (`QWidget.resize` não move o canto superior esquerdo por padrão) - crescer pra baixo nunca invade o espaço já reservado pros bubbles (que ficam acima do composer nos dois layouts possíveis de `positioning.py`), então **nem `positioning.py` nem `bubble_stack.py` precisaram mudar** - só o valor passado como `altura_composer` em `escolher_layout_conversa` (`conversation_controller.entrar`) trocou da altura de REPOUSO pra `input_bar.ALTURA_MAXIMA` (pior caso: 4 linhas + linha de anexo), reservando o espaço todo de uma vez.
- Ctrl+V com uma imagem na área de transferência (`QGuiApplication.clipboard().mimeData().hasImage()`) ou o botão 📎 (`QFileDialog`) anexam uma imagem - aparece como miniatura removível numa linha própria acima do campo (`_linha_anexo`, escondida por padrão); os dois caminhos convergem no mesmo `_definir_anexo`, nunca duplicado. Ao enviar, a imagem é redimensionada/comprimida (JPEG, thumbnail 1024x1024, qualidade 70 - **mesmo padrão de `capturar_tela_b64`** do lado da GAIA) e vira base64 (`_preparar_imagem_para_envio`) só nesse momento - a compressão acontece no lado do Mascot, antes de cruzar o pipe.
- O botão 😊 abre uma grade fixa de emoji comuns (popup `Qt.WindowType.Popup`, fecha sozinho ao perder o foco/clicar fora - nunca um `QMenu` nativo) que insere o glifo na posição do cursor.
- `InputBar.enviar_solicitado` mudou de `Signal(str)` pra `Signal(object)` (um dict `{"texto", "imagem_preview" (QPixmap pro bubble mostrar), "imagem_base64"/"imagem_mime" (já comprimidos, pro protocolo)}`) - carregar a imagem sem multiplicar parâmetros posicionais por toda a cadeia (`ConversationController.texto_enviado`/`CompanionPanel.enviar_mensagem` mudaram do mesmo jeito). `Bubble` ganhou um parâmetro `imagem: QPixmap | None` (miniatura desenhada dentro do balão, acima do texto, teto de `ALTURA_MAXIMA_MINIATURA` - nunca vira uma imagem em tela cheia).

**Pipeline de visão de verdade** (o usuário pediu o pipeline completo, não só a interface, depois de eu explicar que o LLM principal - `gpt-oss-120b` - não é multimodal): `core/mascot_events.py::evento_chat_submitted` ganhou `imagem_base64`/`imagem_mime` opcionais (compatível - `None` produz o MESMO dict de sempre); `TAMANHO_MAXIMO_MENSAGEM_BYTES` (o teto de tamanho de UMA mensagem no pipe Mascot<->GAIA) subiu de 64KB pra 4MB pra caber uma imagem JPEG comprimida com folga. Do lado da GAIA (`assistant/core/agent/turno.py`), descobri (pesquisando antes de implementar) que **já existia** um pipeline de visão pronto pro recurso de "ver a tela" (`client_vision`/`MODELO_VISAO`, hoje `qwen/qwen3.6-27b` na Groq, modelo PREVIEW) - reaproveitado 100%, nunca duplicado: uma imagem anexada dispara a MESMA chamada (`client_vision.chat.completions.create` com `content` em formato de lista `image_url`), só que descrevendo a foto do usuário em vez da tela; a descrição em TEXTO é injetada no histórico (`historico_api[-1]["content"] +=`) e a persona principal responde normalmente, com toda a lógica de tags/persona intacta - ela NUNCA recebe a imagem de verdade (não é multimodal), só a descrição. `despachar_turno`/`processar_ia`/`_gerar_e_falar_resposta_persona` ganharam `imagem_anexada_b64`/`imagem_anexada_mime` (default `None`, threaded através da cadeia inteira); o Modo em Grupo (`processar_ia_grupo`) ignora a imagem de propósito (escopo menor, nenhuma persona secundária tem `client_vision` dedicado ainda). Erro na análise vira um alerta de sistema honesto pra persona ("diga que não conseguiu ver a imagem"), nunca um crash nem uma invenção do que a imagem poderia conter.

**Bug real encontrado testando ao vivo, mesmo dia** (usuário mandou uma imagem de verdade e a resposta foi "não consegui abrir a imagem") - log do console da GAIA mostrou `HTTP 429` da Groq: `output tokens per minute (OTPM): Limit 1000, Requested 1024` - a conta tem um teto de 1000 tokens de SAÍDA por minuto pra `qwen/qwen3.6-27b` (modelo PREVIEW, tier `on_demand`), e o `max_tokens=1024` da chamada já excedia isso sozinho, rejeitando tudo antes de gastar qualquer token. Corrigido em `assistant/core/agent/turno.py` reduzindo pra `max_tokens=800` - **nos DOIS pontos** que chamam `client_vision` (imagem anexada E a Visão da tela/F9, que tinha o MESMO `max_tokens=1024` e o MESMO bug, nunca notado antes por falta de uso recente). Fica documentado como um limite REAL da conta pra este modelo preview - se um dia `MODELO_VISAO` mudar ou a conta subir de tier, vale reavaliar se 800 ainda é necessário ou se dá pra voltar a subir.

**Histórico completo (`CompanionPanel`) virou bubbles de verdade, mesmo dia** (2 achados do usuário testando ao vivo: "o historico n mostra a imagem q foi enviada" + "em vez de aparecer essa tela feia ai, quero q apareca as bubble, com uma barra lateral p permitir ver msgs mais antigas", com print mostrando a lista de texto simples de antes). Duas mudanças:

- **`bubble.Bubble` ganhou modo embutido** - `_BolhaBase.__init__` ganhou `janela_topo: bool = True` (quando `False`, pula `setWindowFlags`/a chamada adiada de `aplicar_protecao_captura` - não é uma janela de verdade, é um widget FILHO normal); `Bubble` ganhou `embutido: bool` (usa `janela_topo=not embutido`, e desliga o truncamento de texto - o histórico completo É o destino de "Ver completo", truncar de novo aqui não faria sentido) e `largura_maxima: int | None` (teto PRÓPRIO no lugar de `LARGURA_PADRAO`, que é pensado pro envelope flutuante do Conversation Overlay, não pra largura fixa de um painel). Os métodos de animação (`entrar`/`sair`/`mover_para`, que fazem `move()` em coordenadas absolutas) simplesmente nunca são chamados nesse modo - quem posiciona é o `QVBoxLayout` do painel, como qualquer widget filho comum.
- **`companion_panel.py::_redesenhar_mensagens` reescrito** - cada mensagem vira um `Bubble(..., embutido=True, largura_maxima=LARGURA_MAXIMA_BUBBLE_HISTORICO)` de verdade (mesmo avatar/miniatura de imagem/glow do Conversation Overlay), envolvido num `QWidget` wrapper com `QHBoxLayout` que alinha esquerda/direita/centro conforme `bubble.alinhamento` (`addStretch` do lado oposto) - o wrapper garante que `deleteLater()` limpa bubble+linha de uma vez, sem vazar widget órfão. `_mensagens` passou a guardar `(remetente, texto, imagem)` com o vocabulário do `Bubble` (`"gaia"`/`"usuario"`/`"sistema"`, não mais "Galateia"/"Você"/"Sistema" capitalizados - identidade agora vem do avatar, não de um prefixo de texto) - **corrige de propósito** o bug relatado ("historico n mostra a imagem") porque `enviar_mensagem` agora repassa `payload["imagem_preview"]` de verdade pro bubble em vez de só colar um emoji `🖼` no texto. A barra de rolagem da `QScrollArea` (que já existia, só que com o visual padrão do Fusion, fácil de nem notar contra o fundo escuro) ganhou QSS próprio (`_QSS_SCROLL`) - mais larga (14px), cor cristal, cantos arredondados - resolvendo o pedido de "barra lateral pra ver mensagens mais antigas" sem precisar de paginação/persistência nova (o teto de `MAXIMO_MENSAGENS=20` continua o mesmo - mensagens mais antigas que isso continuam sendo descartadas, não persistidas em disco). A borda do próprio painel também virou cristal (era `estilo.BORDA_SUTIL`, cinza genérico) pra combinar com os bubbles agora dentro dele. `import html`/`html.escape` saíram - `Bubble` desenha texto puro via `QPainter.drawText`, nunca interpreta HTML, então o escape que existia só pra blindar o `<b>` do `QLabel` antigo ficou sem uso. Teste cross-repo `assistant/testes/testar_mascot_protocolo.py` (verifica o dispatch `assistant_message`/`user_message` -> `CompanionPanel._mensagens`) atualizado pro novo vocabulário/formato de tupla.

**Revertido no MESMO dia - "Ver completo"/histórico não abre mais o `CompanionPanel` de jeito NENHUM, virou uma VIEW do próprio `BubbleStack`** (o usuário corrigiu o design acima: "vc entendeu errado. Quero remover essa tela separada de historico. Essas mensagens q mando e recebo e apagam a cada 15s, qnd eu clicar em historico elas tem de ficar visiveis e permanentes, permitindo voltar com scroll. E tem de ter um limite de altura tbm"). Confirmado por pergunta direta (`AskUserQuestion`) que a resposta certa era "o painel de histórico é para remover, só faz as bubble ficar visível" - nunca um container/QScrollArea novo, os bubbles CONTINUAM sendo janelas top-level flutuantes de sempre, só que muitos ao mesmo tempo. Mudanças:

- **`bubble_stack.py` ganhou "modo histórico"** - `_historico_dados: list[tuple[remetente, texto, imagem]]` guarda TODA mensagem desde que o `BubbleStack` foi criado, NUNCA trimado (sobrevive a `limpar()`/timeout de inatividade - só é descartado se o `BubbleStack` inteiro morrer). `alternar_historico()` LIGA/DESLIGA: ligado, esconde a pilha normal (≤3, `self._bubbles`) e reconstrói um `Bubble` NOVO por entrada de `_historico_dados` (`sem_truncamento=True` - novo parâmetro em `bubble.Bubble`, independente de `embutido`: mostra o texto INTEIRO sem "Ver completo", mas continua sendo uma janela FLUTUANTE de verdade, não um widget embutido) - empilhados numa "janela" VIRTUAL de altura limitada (`ALTURA_MAXIMA_HISTORICO = 500`, clampada contra a altura real da região que `positioning.py` já reservou - nunca ultrapassa isso, `positioning.py` continua intocado). Mensagens que chegam com o modo já ligado aparecem nele ao vivo (`_adicionar_bubble_historico`); ao desligar, os bubbles do histórico são descartados e a pilha normal reaparece com o conteúdo ATUALIZADO (`_reposicionar()`, que atualizava por baixo dos panos o tempo todo).
- **Scroll de verdade sem nenhum container novo** - `_BolhaBase` ganhou `wheelEvent`/o sinal `scroll_solicitado` (emite o delta bruto do Qt); `BubbleStack._ao_scroll_historico` ajusta um offset (`self._offset_scroll_historico`, clampado em `[0, altura_da_pilha_inteira - altura_da_janela]`) e reposiciona - bubbles fora da janela visível ficam `.hide()`n (nunca destruídos, voltam se rolar de volta). Rodinha "pra cima" (delta positivo) revela mensagens mais ANTIGAS, mesma convenção de qualquer chat.
- **`ConversationController.abrir_historico_completo`** (usado pelo "Ver completo" de um bubble truncado) virou "GARANTE aberto, nunca fecha"; o botão DEDICADO do `InputBar` ganhou `alternar_historico` (liga/desliga de verdade) - os dois convergem em `BubbleStack.alternar_historico`/a property `historico_ativo`. O sinal `expandir_solicitado` do `ConversationController` (que emitia pro `process_main.py` abrir o `CompanionPanel`) foi REMOVIDO - não existe mais nenhum caminho que mostre aquela janela.
- **`CompanionPanel` removido do runtime** - a correção inicial apenas deixou de chamar `.show()`, mas o `QWidget` oculto continuava sendo construído e ganhava um HWND quando a proteção contra captura chamava `winId()`. Depois de o problema reaparecer ao vivo, as duas responsabilidades não visuais restantes foram extraídas para `conversation_service.py`: um `QObject` que envia pelo bridge e mantém o estado de voz consumido pelo Menu SAO. `MascotApp` não instancia mais `CompanionPanel`; composer, mensagens e histórico continuam exclusivamente no Conversation Overlay/BubbleStack. Um alias de atributo preserva temporariamente o contrato cross-repo antigo, mas aponta para o serviço sem janela.

**2 achados testando ao vivo o modo histórico, mesmo dia:**

- **Bubbles "duplicados" (print real: uma cópia fantasma logo atrás de cada mensagem)** - confirmado por script que NÃO existe bubble/dado duplicado nenhum (`BubbleStack._bubbles`/`_historico_dados` sempre têm exatamente 1 entrada por mensagem) - é um artefato de COMPOSITING do Windows, a 4ª variação da mesma família de bugs desta sessão sobre janela top-level frameless translúcida sempre-no-topo (`QGraphicsDropShadowEffect` invisível, `winId()` prematuro travando em branco, `raise_()` de z-order na entrada). Aqui, `_BolhaBase._passo()` movia E esmaecia o widget no mesmo frame só com `update()` (agendado, pode atrasar/empilhar) - o DWM às vezes compunha um frame ANTIGO por cima do novo por um instante. Corrigido trocando `update()` por `repaint()` (síncrono, nunca adiado) nos 3 ramos da animação (`entrando`/`saindo`/`realocando`, este último agora sempre repinta, não só quando a opacidade muda) e chamando `raise_()` a cada frame também durante a animação (antes só na entrada) - mesma razão de sempre: várias janelas "sempre no topo" concorrentes podem perder a ordem entre si a qualquer momento, não só ao aparecer pela primeira vez.
- **Nenhuma pista visual de que o modo histórico está ligado** ("eu tenho q saber quando o botao de historico ta habilitado ou n") - `InputBar.definir_historico_ativo(ativo)` (novo) troca o estilo do botão `✦` entre dourado discreto (inativo) e um destaque cristal com fundo/borda (ativo), além do tooltip ("Ver histórico completo da conversa" ↔ "Fechar histórico completo"). `ConversationController.alternar_historico`/`abrir_historico_completo` chamam isso sempre que o modo muda; `sair()`/`fechar_imediato()` também sincronizam de volta pro estado inativo (já que `BubbleStack.limpar()` sempre desliga o modo histórico se estivesse ligado).

**Deixado para depois** (ver `TODO.md`): configurações do Bubble Mode
(timeout de inatividade, largura máxima, desligar bubbles inteiro) ainda
não estão no modal de Configurações; a waveform do indicador "ouvindo" é
decorativa (sem nível de áudio real, não existe esse canal vindo da
GAIA hoje); um bubble individual não pode ser arrastado/fechado por
conta própria (só a pilha inteira via inatividade/fim de conversa/
arraste da GAIA); sem streaming real de texto (o backend não manda
resposta em pedaços hoje).

## Gesture Wheel (`mascot/gesture_wheel.py`)

O item **Ações** do Menu SAO abre um único nível de medalhões circulares ao
redor da silhueta visível da GAIA. Ele consome a mesma fonte de transições
válidas da bandeja (`animacao_menu.ids_animacoes_validas`), portanto nunca
oferece um complemento incompatível com o estado atual. A personagem não é
reposicionada: a roda é completa no centro, semicircular em uma borda e usa
duas fileiras em quadrante nos cantos. Escape, botão direito ou clique fora
dos medalhões fecha; iniciar um arraste fecha Menu SAO e Gesture Wheel.

`data/gesture_wheel.json` controla quantidade (1–8), ordem/favoritas,
rótulos e símbolos. A configuração é lida a cada abertura. Lista `acoes`
vazia significa seleção automática; se nenhuma favorita configurada for
válida no estado atual, o componente também cai nessa seleção automática.
Enquanto aberta, a roda mantém o bloqueio de autonomia pelo motivo
`gesture_wheel`, independente do bloqueio `menu_sao`.

## Pipeline de novas animações

`scripts/automatizar_animacoes.py` (orquestrador) → `importar_animacao.py`/
`importar_lote_animacoes.py` (recorte/normalização de vídeo ou frames pro
runtime) → `validar_animacoes.py` (valida geometria/schema sem precisar
de Qt) → `visualizar_animacoes.py`/`auditar_continuidade_movimento.py`
(revisão visual humana das emendas iniciar→loop→parar).
