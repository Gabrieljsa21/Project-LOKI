# Project LOKI

Avatar animado da Galateia (GAIA) flutuando no desktop - presença visual
opcional, processo separado da assistente, consumido por ela via named
pipe local. 72+ clipes de animação reais (voo, sentar, dormir, ser
arrastada, reações raras), comportamento autônomo (Wander, Taskbar Sit,
variações sentadas) com física própria, e um CompanionPanel (janela de
conversa ancorada à personagem).

Arquitetura completa e decisões de design em [`ARQUITETURA.md`](ARQUITETURA.md).
Guia completo do fluxo vídeo → importação → catálogo → runtime em
[`ANIMACOES_GALATEIA.md`](ANIMACOES_GALATEIA.md). Plano original (todas
as fases, 0 a 8): `C:\Workspace\Project LOKI.md`.

## A origem do nome

Na mitologia nórdica, Loki é associado a metamorfose e mudança de forma -
a GAIA representa a personagem e identidade, LOKI controla a forma visual
que ela assume no desktop.

## Uso standalone

```bash
uv venv
uv pip install -e .
python -m mascot.process_main
```

Sem as variáveis de ambiente `GAIA_MASCOT_CANAL`/`GAIA_MASCOT_TOKEN`
(passadas pela GAIA quando ela sobe o processo de verdade), roda sozinho
em "modo demonstração" - útil pra testar animações/comportamentos sem
precisar da GAIA rodando. A bandeja do sistema tem um submenu "Forçar
animação" (playground de teste) além de Configurações/Sair.

Config e posição salva ficam em `data/mascot_config.json`/`data/
mascot_posicao.json`, criados sozinhos na 1ª execução.

## Consumido pela GAIA

`assistant/integrations/mascot/supervisor.py` sobe este processo a partir
do `.venv` PRÓPRIO deste repo (não do venv da GAIA) - `PROJETO_LOKI_DIR`
no `.env` da GAIA aponta pra onde este repo foi clonado, se não for a
pasta irmã padrão (`C:\Workspace\Project-LOKI`). O Painel da GAIA
("🧚 Mascot (LOKI)") lê/escreve a config deste repo direto por caminho de
arquivo (`integrations/mascot_config_client.py`, do lado da GAIA), sem
import Python cruzando repositórios.

## Testes

```bash
QT_QPA_PLATFORM=offscreen python testes/testar_mascot_assets.py
```

Cada `testes/testar_mascot_*.py` roda sozinho (sem framework), imprime
PASS/FAIL por caso. `scripts/validar_animacoes.py` confere que todo
clipe compartilha a geometria comum (`assets/galateia/animations/
geometry.json`) antes de qualquer import.

## Pipeline de novas animações

`scripts/automatizar_animacoes.py` orquestra a entrada de vídeos/frames
novos - descobre fontes ainda não registradas, cria entradas em
`data/animacoes_galateia.json` de forma atômica, infere metadados básicos
pela convenção dos ids, chama o importador (`importar_animacao.py`/
`importar_lote_animacoes.py`) e o validador, e audita o catálogo inteiro.
`scripts/visualizar_animacoes.py` é um visualizador simples pra revisar
os sprites finais.
