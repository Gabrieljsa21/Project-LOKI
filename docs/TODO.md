# TODO - Project LOKI

Só pendências. Item concluído sai daqui: funcionalidade vai para
`FUNCIONALIDADES.md`, correção vai para o `CHANGELOG.md`. Pendências do lado
da GAIA (imagem anexada no Modo em Grupo, modelo de visão fixo no código)
ficam em `assistant/docs/TODO.md`, seção Mascot/LOKI.

## Validação ao vivo

### Proteção contra captura em screenshot, Discord e OBS

**Prioridade**: Média
**Complexidade**: Baixa
**Status**: aguardando o usuário. Implementação e testes isolados prontos
desde 2026-09-07 (`WDA_EXCLUDEFROMCAPTURE` na personagem, bubbles e campo de
entrada). Falta conferir no Windows real; métodos de captura incompatíveis e
câmera externa continuam fora da garantia.

### Reação à música do SIREN

**Prioridade**: Média
**Complexidade**: Baixa
**Status**: implementada em 2026-11-10 só com testes de regra (sem SIREN
tocando de verdade). Conferir ao vivo: ela vai sentar quando a faixa começa,
fica enquanto toca, volta ao normal até 10 s depois de pausar ou fechar o
SIREN. Um clipe próprio de dança ou de fone de ouvido deixaria a reação mais
clara do que o idle sentado.

## Conversation Overlay (Bubble Mode)

### Waveform do indicador "Te ouvindo" é decorativa

**Prioridade**: Baixa
**Complexidade**: Média
**Status**: as 3 barras oscilam por tempo, não por volume. Depende de um
canal de nível de áudio da GAIA para o Mascot, que ainda não existe.

### Fechar ou arrastar um bubble sozinho

**Prioridade**: Baixa
**Complexidade**: Média
**Status**: hoje só a pilha inteira some (inatividade, fim da conversa ou
arraste da personagem).

### Streaming real de texto

**Prioridade**: Baixa
**Complexidade**: Alta
**Status**: depende da GAIA, que manda `assistant_message` sempre inteira
(`final=True`). Quando houver streaming, atualizar o mesmo `Bubble` em vez de
criar um por pedaço.

### "Morph" indicador para resposta é uma aproximação

**Prioridade**: Baixa
**Complexidade**: Média
**Status**: `IndicadorVoz` e `Bubble` são widgets diferentes; a troca é um
fade no lugar. A solução de verdade é uma classe única com dois modos.

### Histórico só em memória

**Prioridade**: Baixa
**Complexidade**: Média
**Status**: `BubbleStack._historico_dados` some ao reiniciar o Mascot e cresce
sem limite durante a sessão (pesa só com muitas imagens anexadas). O
histórico durável vive na GAIA.

## Roadmap de comportamentos

### Fase 6: Cursor Swing e Cursor Hunt

**Prioridade**: Baixa
**Complexidade**: Alta
**Status**: desligados por padrão; precisam de clipes próprios.

### Fase 7: Tug of War

**Prioridade**: Baixa
**Complexidade**: Alta
**Status**: opcional, hook de mouse por até 3 s, sempre liberado por
clique/Esc/arraste/watchdog.

### Fase 8: cutover do Live2D/VTube Studio

**Prioridade**: Baixa
**Complexidade**: Média
**Status**: não decidido; os dois avatares convivem. Envolve remover
`features/avatar_overlay/` da GAIA e as dependências que só ele usa.

## Manutenção

### Git LFS para spritesheets

**Prioridade**: Baixa
**Complexidade**: Média
**Status**: decisão do usuário. O `.git` tem cerca de 182 MB e cresce a cada
reimportação de `spritesheet.webp`/`preview.webp`. Adotar LFS só para arquivos
novos é simples; migrar o histórico reescreve os commits e exige novo clone
em toda máquina, além de consumir a cota de LFS do GitHub.

### Nomes legados do CompanionPanel

**Prioridade**: Baixa
**Complexidade**: Baixa
**Status**: a chave `companion_panel_shortcut` e o apelido
`MascotApp.companion_panel` continuam por compatibilidade (config salva,
Painel da GAIA e `assistant/testes/testar_mascot_protocolo.py`). Renomear
exige mudar os dois repositórios juntos e migrar a config salva.

### Dividir `behavior_scheduler.py` e `menu_sao.py`

**Prioridade**: Baixa
**Complexidade**: Média
**Status**: 950 e 840 linhas. Dividir quando uma mudança grande passar por
eles, não como tarefa isolada.
