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

- **`always_on_top`/`pause_in_fullscreen` são config MORTA** (achado
  2026-09-03, ao portar o modal de configurações pro LOKI) - `config.py::
  MASCOT_PADRAO` declara os dois, mas nenhum lugar do código LÊ nenhum dos
  dois (`deve_pausar_autonomia`, `platform_windows.py`, já pausa por conta
  própria, sem checar `pause_in_fullscreen`; "sempre no topo" não tem
  nenhum `WindowStaysOnTopHint` condicional em lugar nenhum). Removidos do
  modal novo (`modal_configuracoes.py`) de propósito - manter um toggle
  que não faz nada seria pior que não ter o toggle. Pré-existente, não
  introduzido por esta mudança (o modal antigo da GAIA também os expunha
  sem eles fazerem nada). Decisão pendente: implementar de verdade ou
  remover as chaves de `MASCOT_PADRAO`.

## Roadmap original (fases 6-8, ver `ARQUITETURA.md`)

- **Fase 6** - novos Behaviors: Cursor Swing e Cursor Hunt (hoje
  desligados por padrão, "precisam de clipes próprios, ainda sem
  cobertura" - ver `mascot/modal_configuracoes.py::BEHAVIORS_LABELS`).
- **Fase 7** - Tug of War (cabo de guerra puxando o cursor) - opcional,
  desligado por padrão, hook de mouse por até 3s.
- **Fase 8** - cutover definitivo do Live2D/VTube Studio (remover
  `features/avatar_overlay/` da GAIA, PyQt5/OpenCV/websocket-client como
  dependências órfãs) - ainda não decidido, os dois convivem por
  enquanto.
