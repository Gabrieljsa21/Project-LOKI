# TODO - Project LOKI

## Pendências herdadas da extração (2026-09-03)

- **Launchers/atalhos ainda não recriados** - o repo antigo (`assistant`)
  não tinha `.bat`/`.vbs` dedicados pro Mascot em si (ele subia junto com
  a GAIA); os 3 batch files do PIPELINE de animações
  (`AUTOMATIZAR_ANIMACOES.bat`/`IMPORTAR_ANIMACOES.bat`/
  `TESTAR_ANIMACOES.bat`) existiam lá mas não foram recriados aqui ainda -
  os scripts Python funcionam direto (`python scripts/automatizar_
  animacoes.py ...`), só falta o wrapper `.bat` de conveniência (mesmo
  padrão dos outros satélites, ver `Project-IRIS/iniciar_iris.bat`).
- **Sem atalho de desktop / inicialização oculta** ainda (mesmo padrão de
  `Project-IRIS/criar_atalho_desktop.vbs`/`iniciar_iris_oculto.vbs`) - não
  é urgente porque a GAIA já sobe o processo sozinha via
  `MascotSupervisor`; só faria diferença pra rodar 100% standalone sem a
  GAIA no dia a dia.

## Roadmap do plano original (`C:\Workspace\Project LOKI.md`)

- **Fase 6** - novos Behaviors: Cursor Swing e Cursor Hunt (hoje
  desligados por padrão, "precisam de clipes próprios, ainda sem
  cobertura" - ver `ui/qt_modais/mascot.py` da GAIA).
- **Fase 7** - Tug of War (cabo de guerra puxando o cursor) - opcional,
  desligado por padrão, hook de mouse por até 3s.
- **Fase 8** - cutover definitivo do Live2D/VTube Studio (remover
  `features/avatar_overlay/` da GAIA, PyQt5/OpenCV/websocket-client como
  dependências órfãs) - ainda não decidido, os dois convivem por
  enquanto.
- **Ações/GAIA (Menu SAO)** - os dois círculos desabilitados
  ("Ações"/"GAIA") ainda não têm conteúdo real: "Ações" seria o menu
  contextual reaproveitando `state_catalog.transicoes_validas_a_partir_
  de`, "GAIA" seria controles diretos da mascote (escala, opacidade,
  autonomia) sem precisar abrir o Painel da GAIA. Deferido de propósito
  pra uma rodada própria (não é uma correção pequena).
