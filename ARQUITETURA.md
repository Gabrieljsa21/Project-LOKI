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

## Por que repositório próprio (extraído em 2026-09-03)

Decisão tomada em 2026-08-29, antes mesmo de qualquer código do Mascot
existir fora do `assistant`, por três motivos concretos:

- **LOKI não é obrigatório pra GAIA funcionar** - é presença visual opcional, diferente de cérebro/memória/ferramentas/voz.
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
