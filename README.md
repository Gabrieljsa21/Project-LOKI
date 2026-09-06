# Project LOKI

Avatar animado da Galateia (GAIA) flutuando no desktop - presença visual
opcional, processo separado da assistente, consumido por ela via named
pipe local. 72+ clipes de animação reais (voo, sentar, dormir, ser
arrastada, reações raras), comportamento autônomo (Wander, Taskbar Sit,
variações sentadas) com física própria, e um CompanionPanel (janela de
conversa ancorada à personagem).

Arquitetura completa e decisões de design em [`ARQUITETURA.md`](ARQUITETURA.md).
Guia completo do fluxo vídeo → importação → catálogo → runtime em
[`ANIMACOES_GALATEIA.md`](ANIMACOES_GALATEIA.md). Histórico completo
(features, correções, achados) em [`CHANGELOG.md`](CHANGELOG.md).

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

Pra rodar em segundo plano sem terminal (mesmo padrão dos outros
satélites): `iniciar_loki.bat` (sobe via `pythonw.exe`, sem console) ou
`iniciar_loki_oculto.vbs` (esconde também o console do próprio `.bat`).
`criar_atalho_desktop.vbs` cria um atalho "LOKI" na Área de Trabalho
apontando pro `.vbs` oculto - rodar uma vez só, depois de clonar o repo.
Em qualquer um dos dois modos, **Configurações** funciona normalmente. O
CompanionPanel pode abrir, mas enviar mensagens ainda depende da GAIA conectada.

Config e posição salva ficam em `data/mascot_config.json`/`data/
mascot_posicao.json`, criados sozinhos na 1ª execução.

O botão **Ações** do Menu SAO abre uma roda de gestos plana,
inspirada no menu de emotes de Don't Starve Together. No centro da tela os
botões formam um círculo; perto de bordas viram uma meia-roda; nos cantos,
duas fileiras curvas dentro de um quadrante. Em **Configurações → Roda de
ações** dá para escolher animações, páginas, quantidade por página, grupos e
uma imagem própria para cada botão. A rolagem sobre a GAIA ou a roda troca de
página; enquanto ela está aberta, a personagem permanece imóvel.
Uma lista `acoes` vazia usa automaticamente as animações válidas do estado
atual. Se preenchida, funciona como a lista ordenada de favoritas.

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
