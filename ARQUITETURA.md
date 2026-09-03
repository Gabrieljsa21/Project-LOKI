# Arquitetura - Project LOKI

Plano completo (todas as fases, histórico de decisões): `C:\Workspace\
Project LOKI.md`. Este arquivo cobre só as decisões estruturais que
sobrevivem além de uma fase específica.

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
falhar.

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

## Pipeline de novas animações

`scripts/automatizar_animacoes.py` (orquestrador) → `importar_animacao.py`/
`importar_lote_animacoes.py` (recorte/normalização de vídeo ou frames pro
runtime) → `validar_animacoes.py` (valida geometria/schema sem precisar
de Qt) → `visualizar_animacoes.py`/`auditar_continuidade_movimento.py`
(revisão visual humana das emendas iniciar→loop→parar).
