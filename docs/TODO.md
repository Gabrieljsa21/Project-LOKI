# TODO - Project LOKI

## Conversation Overlay / "Bubble Mode" (v1, 2026-09-06)

Primeira versão funcional (ver `ARQUITETURA.md`, seção "Conversation
Overlay") - pendências deliberadamente deixadas pra depois, não
esquecimento:

- **Validar ao vivo o modo de privacidade contra captura**: implementação e
  testes isolados concluídos em 2026-09-07. O toggle aplica
  `WDA_EXCLUDEFROMCAPTURE` ao Mascot, bubbles, campo de entrada e demais janelas
  abertas, com fallback seguro. Falta conferir visualmente screenshot, Discord
  e OBS no Windows real; métodos incompatíveis e câmera externa continuam fora
  da garantia. Status: aguardando validação do usuário.
- **Configurações do Bubble Mode ainda não estão no `ModalConfiguracoes`**
  (timeout de inatividade de 15s, largura máxima do bubble/input,
  desligar o Bubble Mode inteiro e voltar ao `CompanionPanel` sempre) -
  hoje só dá pra mudar editando `conversation_overlay/bubble.py`/
  `bubble_stack.py` na mão. Todo valor hardcoded lá é candidato a virar
  campo do modal, mesmo padrão do resto do LOKI.
- **Waveform do indicador "🎙 Te ouvindo..." é decorativa** (3 barras
  oscilando por tempo, não por volume real) - não existe hoje nenhum
  canal de nível de áudio vindo da GAIA pro Mascot; ligaria à
  `evento_heartbeat`/evento novo se um dia isso existir.
- **Um bubble individual não pode ser fechado/arrastado sozinho** - só a
  pilha inteira via timeout de inatividade, fim da conversa, ou arraste
  real da própria GAIA (`fechar_imediato`).
- **Sem streaming real de texto** (confirmado 2026-09-06 lendo `assistant/
  run.py` - `evento_assistant_message` sempre com `id` novo e `final=True`,
  nunca em pedaços) - o indicador "✦" + reticências sempre troca pro
  texto completo de uma vez (com uma aproximação de "morph", `Bubble.
  entrar(..., deslizar=False)` - ver `ARQUITETURA.md`, não é streaming de
  verdade); se um dia o backend ganhar streaming de verdade, dá pra
  atualizar o MESMO `Bubble` progressivamente em vez de criar um novo por
  chunk.
- **"Morph" indicador->resposta é uma aproximação, não uma transformação
  de verdade** (`IndicadorVoz` e `Bubble` continuam objetos Qt
  DIFERENTES - decisão consciente de não unificar as classes agora) - se
  um dia isso incomodar visualmente, a solução de verdade seria uma
  classe única que muda de "modo indicador" pra "modo mensagem" no
  próprio lugar, sem criar um widget novo.
- **Imagem anexada (2026-09-07) não funciona no Modo em Grupo** -
  `despachar_turno` ignora `imagem_anexada_b64` de propósito quando 2+
  personas estão ativas (`processar_ia_grupo` não recebe o parâmetro) -
  nenhuma persona secundária tem `client_vision` dedicado ainda, decisão
  de escopo menor (roleplay em grupo é o caso raro). Anexar imagem com o
  Modo em Grupo ligado hoje simplesmente não gera descrição nenhuma - a
  persona responde só ao texto, sem avisar que ignorou a imagem.
- **`configuracoes.py` não expõe o modelo de visão** (`MODELO_VISAO`,
  `qwen/qwen3.6-27b` na Groq) - hardcoded em `core/agent/llm_fallback.py`
  (assistant), fora da cadeia configurável (`CAMADAS_LLM`). É um modelo
  PREVIEW da Groq (pode ser descontinuado sem aviso, ver changelog deles)
  - se sumir, tanto a Visão da tela (F9) quanto a imagem anexada no
    Conversation Overlay quebram juntas (mesmo `MODELO_VISAO`).
- **Modo histórico (`BubbleStack._historico_dados`, 2026-09-07) guarda a
  sessão inteira só em MEMÓRIA, sem persistência em disco** (ver
  `ARQUITETURA.md` - "'Ver completo'/histórico... virou uma VIEW do
  próprio BubbleStack") - fechar o Mascot/reiniciar o processo perde o
  histórico inteiro (nunca gravado em arquivo); cresce sem limite
  enquanto o processo viver (mensagens de texto são pequenas, não é um
  problema real hoje, mas uma sessão MUITO longa com muitas imagens
  anexadas eventualmente pesaria memória). Se um dia precisar sobreviver
  a um restart, precisa de uma camada de persistência nova (arquivo
  próprio do Mascot) - hoje o histórico "de verdade" só existe do lado da
  GAIA (memória por persona/pessoa, `arquivo_memoria_persona`), nunca
  espelhado pro Mascot.

## Pendências herdadas da extração (2026-09-03)

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
