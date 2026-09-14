# -*- coding: utf-8 -*-
"""CompanionPanel (Project LOKI, Fase 4 MVP - 2026-09-01) - janela de texto
ancorada à personagem. Mora no MESMO subprocesso do Mascot
(`process_main.py`), nunca no processo da GAIA (plano, seção 6.2). Fala com
a GAIA só por protocolo (`MascotBridgeServer.enviar`/`evento_recebido`,
nunca import direto) - ver `core/mascot_events.py::evento_chat_submitted`/
`evento_stop_speaking_requested`/`evento_voice_toggle_requested`
(Mascot->GAIA) e `evento_assistant_message` (GAIA->Mascot).

Escopo deliberadamente enxuto (plano, seção 9; corte de escopo desta rodada
em `docs/TODO.md`): texto puro escapado (sem parse de Markdown), sem
sincronizar mensagens de outros canais (só mostra o que passa por AQUI),
ancora só no momento de abrir (não segue a personagem durante voo
autônomo).

**Deixou de ser a porta de entrada PADRÃO da conversa em 2026-09-06**
(Conversation Overlay/"Bubble Mode", `conversation_overlay/`).

**Nunca mais mostrado, 2026-09-07** (2ª revisão no mesmo dia - a 1ª
versão tinha virado o destino do "Ver completo"/histórico, mostrando
esta janela com os bubbles embutidos; o usuário corrigiu: "vc entendeu
errado... quero remover essa tela separada de histórico... só faz as
bubble ficar visível") - histórico completo e "Ver completo" agora são
uma VIEW do próprio `BubbleStack` (mesmos bubbles flutuantes de sempre,
sem painel/janela nova nenhuma - ver `conversation_overlay/bubble_stack.
py::alternar_historico`). Este painel continua existindo (construído,
nunca `.show()`n) só por DUAS responsabilidades que ainda são dele:
`enviar_mensagem` (o envio de verdade pro bridge - `Conversation
Overlay`/`InputBar` chamam isto pra mandar mensagem de verdade) e o modo
de voz (`modo_voz_atual`/`definir_modo_voz`/`modo_voz_alterado`, fonte
única que o Menu SAO usa pro indicador permanente do modo ativo).
`_adicionar_mensagem`/`_redesenhar_mensagens` continuam existindo (não
foram apagados - podem servir se este painel for mostrado manualmente de
novo por algum motivo futuro), mas só reconstroem os bubbles quando
`self.isVisible()` - nunca à toa numa janela que não aparece."""
from __future__ import annotations

import uuid

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget

from core import mascot_events
from mascot import companion_style as estilo
from mascot import platform_windows
from mascot.conversation_overlay import bubble as bubble_module
from mascot.conversation_overlay import estilo as estilo_overlay

LARGURA = 420
ALTURA = 520
MAXIMO_MENSAGENS = 20
MOTIVO_SEM_CONEXAO = "Sem conexão com a GAIA (modo demonstração)."
# Teto de largura de um bubble EMBUTIDO aqui (2026-09-07, ver
# `_redesenhar_mensagens`) - `LARGURA` menos margens do layout externo
# (12px cada lado) e uma folga pra barra de rolagem lateral nova/mais
# larga (`_QSS_SCROLL` abaixo) - nunca o teto do Conversation Overlay
# (`bubble.LARGURA_PADRAO`, pensado pro envelope flutuante, não pra
# largura FIXA deste painel).
LARGURA_MAXIMA_BUBBLE_HISTORICO = LARGURA - 2 * 12 - 24
# Barra de rolagem PRÓPRIA (2026-09-07, pedido do usuário: "quero... uma
# barra lateral p permitir ver msgs mais antigas" - a `QScrollArea` já
# existia e já permitia isso, só que com a barra padrão do Fusion, fina/
# cinza, fácil de nem notar que existe contra o fundo escuro) - mesma
# identidade cristal dos bubbles, bem mais larga/visível.
_QSS_SCROLL = f"""
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{
        background: {estilo_overlay.FUNDO_2}; width: 14px; margin: 0px; border-radius: 7px;
    }}
    QScrollBar::handle:vertical {{
        background: {estilo_overlay.cor_fundo_translucido(estilo_overlay.CRISTAL, 0.45)};
        min-height: 30px; border-radius: 7px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {estilo_overlay.cor_fundo_translucido(estilo_overlay.CRISTAL, 0.65)};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""

# 🔥 Ciclo simples (sem confirmação de volta - plano seção 9.2: "microfone
# controla o modo de voz existente, sem segunda captura") - mesmo
# vocabulário de `PainelQt.disparar_modo`/`evento_voice_toggle_requested`.
MODOS_VOZ_CICLO = (None, "voz_continua", "click_to_talk")
# Ícone PRÓPRIO por modo (corrigido 2026-09-06, pedido do usuário sobre o
# Menu SAO: o botão "Voz" ciclando direto no clique "gera ambiguidade
# sobre se o texto exibido representa o estado atual ou a ação que será
# executada" - o Nível 1 do Menu SAO agora usa estes glifos como
# INDICADOR PERMANENTE do modo ativo, ver `menu_sao.py::
# _atualizar_circulo_voz_nivel1`). Reaproveitados aqui também (botão do
# próprio painel) - MESMA fonte de ícone/texto pros dois lugares nunca
# divergirem do estado real (`MODOS_VOZ_ROTULO` abaixo só concatena os
# dois pro rótulo do QPushButton).
MODOS_VOZ_GLIFO = {
    None: "⊘",
    "voz_continua": "◉",
    "click_to_talk": "🎙",
}
MODOS_VOZ_TEXTO = {
    None: "Voz desligada",
    "voz_continua": "Voz contínua",
    "click_to_talk": "Push-to-talk",
}
MODOS_VOZ_ROTULO = {modo: f"{MODOS_VOZ_GLIFO[modo]} {MODOS_VOZ_TEXTO[modo]}" for modo in MODOS_VOZ_CICLO}


class CompanionPanel(QWidget):
    # 🔥 Sinal pra alternar visibilidade de QUALQUER thread com segurança
    # (mesmo motivo de `MascotSupervisor._enviar_solicitado` -
    # `integrations/mascot/supervisor.py`) - o hotkey global (lib `keyboard`,
    # `process_main.py`) roda num listener thread PRÓPRIO, não na thread do
    # Qt; chamar `alternar_visibilidade()` direto de lá mexeria em widgets
    # fora da thread dona. Emitir este sinal marshalla automaticamente pra
    # cá (a thread que criou este QWidget).
    alternar_visibilidade_solicitado = Signal()
    # Emitido toda vez que o modo de voz muda de verdade, qualquer que seja
    # a origem (ciclo do próprio botão OU seleção direta no Nível 2 do Menu
    # SAO, `definir_modo_voz` abaixo) - o Menu SAO escuta isto pra manter o
    # ícone/rótulo do botão "Voz" (Nível 1) sempre sincronizado com o
    # estado real, sem duplicar `_modo_voz_atual` (2026-09-06).
    modo_voz_alterado = Signal(object)
    # Falha LOCAL de envio (bridge indisponível - nunca vai existir uma
    # `assistant_message` de resposta pra esse turno) - o Conversation
    # Overlay escuta isto pra mostrar um bubble de erro discreto (doc,
    # 2026-09-06: "não quero uma QMessageBox"); o CompanionPanel em si já
    # registra o mesmo motivo no próprio histórico (`_enviar_evento`),
    # este sinal só existe pra outra UI saber que precisa reagir também.
    falha_envio = Signal(str)

    def __init__(self, mascot_window, bridge_provider, safety=None, parent=None):
        """`bridge_provider`: callable sem argumento que devolve o
        `MascotBridgeServer` atual (`None` em modo demonstração, ou se ainda
        não conectou) - callable em vez de referência direta porque o
        bridge só existe com `GAIA_MASCOT_CANAL`/`TOKEN` setados (ver
        `MascotApp._montar_bridge`).

        `safety`: `SafetyController` (2026-09-02, `GAIA_MENU_SAO.md`) -
        opcional (`None` só pros testes que não montam o resto do
        `MascotApp`) pra bloquear/liberar autonomia enquanto o painel está
        aberto (ver `showEvent`/`hideEvent` abaixo)."""
        super().__init__(parent)
        self._mascot_window = mascot_window
        self._obter_bridge = bridge_provider
        self._safety = safety
        self._mensagens: list[tuple[str, str, object]] = []  # (remetente bubble.py, texto, imagem QPixmap|None)
        self._modo_voz_atual = None

        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(LARGURA, ALTURA)
        # Borda CRISTAL (2026-09-07, era `estilo.BORDA_SUTIL`, cinza genérico)
        # - mesma identidade visual dos bubbles agora embutidos aqui dentro
        # (ver `_redesenhar_mensagens`), fundo continua o mesmo de sempre
        # (`SURFACE_COLOR` já é bem próximo do navy do Conversation Overlay).
        self.setStyleSheet(
            f"background-color: {estilo.SURFACE_COLOR}; border: 1px solid {estilo_overlay.CRISTAL}; border-radius: 10px;"
        )
        self.setWindowTitle("Galateia")

        self._montar_ui()
        self.alternar_visibilidade_solicitado.connect(self.alternar_visibilidade)
        self.hide()

        # 🔥 CORRIGIDO (2026-09-07, achado ao vivo: esta janela apareceu em
        # BRANCO depois de reiniciar a GAIA) - `aplicar_protecao_captura`
        # chama `widget.winId()`, que força a criação IMEDIATA do HWND
        # nativo do Windows. Chamada ANTES daqui (logo depois de
        # `setWindowFlags`, sem `setFixedSize`/estilo/`_montar_ui`/`hide`
        # ainda aplicados) força esse HWND a existir sem geometria/conteúdo
        # nenhum - a janela nativa nasce "congelada" no primeiro frame em
        # branco que o Windows conseguiu capturar, e nunca repinta direito
        # depois (mesma classe de bug de timing Qt/Windows já vista em
        # `bubble.py::_BolhaBase.entrar`, que precisou do mesmo adiamento
        # pro `raise_()`). Adiada pro FIM do construtor (depois de
        # `_montar_ui`/`hide`) via `QTimer.singleShot(0, ...)` - o HWND só é
        # forçado depois que a janela já tem conteúdo/estilo/estado certos.
        from mascot import config, platform_windows
        QTimer.singleShot(0, lambda: platform_windows.aplicar_protecao_captura(
            self, bool(config.carregar_config_mascot().get("proteger_de_captura")),
        ))

    def _montar_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        titulo = QLabel("Galateia")
        titulo.setStyleSheet(f"color: {estilo.GAIA_GOLD}; font-weight: bold; font-size: 14px; font-family: '{estilo.FONTE_BASE}';")
        lay.addWidget(titulo)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(_QSS_SCROLL)
        self._conteudo_mensagens = QWidget()
        self._lay_mensagens = QVBoxLayout(self._conteudo_mensagens)
        self._lay_mensagens.setContentsMargins(0, 0, 0, 0)
        self._lay_mensagens.addStretch(1)
        self._scroll.setWidget(self._conteudo_mensagens)
        lay.addWidget(self._scroll, stretch=1)

        linha_botoes = QHBoxLayout()
        self._botao_mic = QPushButton(MODOS_VOZ_ROTULO[None])
        self._botao_mic.clicked.connect(self.ciclar_modo_voz)
        linha_botoes.addWidget(self._botao_mic)

        botao_parar = QPushButton("⏹ Parar")
        botao_parar.clicked.connect(self._pedir_parar)
        linha_botoes.addWidget(botao_parar)
        lay.addLayout(linha_botoes)

        linha_input = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Digite uma mensagem...")
        self._input.returnPressed.connect(self._enviar)
        linha_input.addWidget(self._input, stretch=1)

        botao_enviar = QPushButton("Enviar")
        botao_enviar.clicked.connect(self._enviar)
        linha_input.addWidget(botao_enviar)
        lay.addLayout(linha_input)

        for botao in (self._botao_mic, botao_parar, botao_enviar):
            botao.setStyleSheet(f"""
                QPushButton {{
                    background-color: {estilo.HIGHLIGHT_COLOR}; color: {estilo.TEXT_COLOR};
                    border: none; border-radius: 6px; padding: 6px 10px;
                }}
                QPushButton:hover {{ background-color: {estilo.cor_com_alpha(estilo.GAIA_GOLD, 0.25)}; }}
            """)
        self._input.setStyleSheet(
            f"background-color: {estilo.HIGHLIGHT_COLOR}; color: {estilo.TEXT_COLOR}; border-radius: 6px; padding: 6px;"
        )

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._safety is not None:
            self._safety.bloquear_autonomia("companion_panel")

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if self._safety is not None:
            self._safety.liberar_autonomia("companion_panel")

    # ------------------------------------------------------------------
    def alternar_visibilidade(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.mostrar_ancorada()

    def mostrar_ancorada(self) -> None:
        """Público (2026-09-06) - MESMO "mostrar" que `alternar_visibilidade`
        já fazia no ramo `else` acima, extraído pro Conversation Overlay
        pedir "sempre mostrar" (nunca fechar) quando um bubble estoura o
        limite e oferece "Ver completo"/"Expandir"
        (`conversation_overlay/conversation_controller.py::_ao_expandir_bubble`)."""
        self._ancorar_junto_a_mascot()
        self.show()
        self.raise_()
        self._input.setFocus()

    def _ancorar_junto_a_mascot(self) -> None:
        """Calculado só na hora de abrir (não segue a personagem durante voo
        autônomo depois - simplificação deliberada de escopo, ver docstring
        do módulo). Abre do lado com mais espaço livre dentro da work area
        (exclui a barra de tarefas, `platform_windows.obter_work_area_da_tela`)."""
        janela = self._mascot_window
        tela = janela.screen()
        if tela is None:
            return
        area_x, area_y, area_w, area_h = platform_windows.obter_work_area_da_tela(tela)
        espaco_direita = (area_x + area_w) - (janela.x() + janela.width())
        espaco_esquerda = janela.x() - area_x
        if espaco_direita >= LARGURA or espaco_direita >= espaco_esquerda:
            x = janela.x() + janela.width() + 12
        else:
            x = janela.x() - LARGURA - 12
        x = max(area_x, min(x, area_x + area_w - LARGURA))
        y = max(area_y, min(janela.y(), area_y + area_h - ALTURA))
        self.move(x, y)

    # ------------------------------------------------------------------
    def _enviar(self) -> None:
        texto = self._input.text().strip()
        if not texto:
            return
        self._input.clear()
        self.enviar_mensagem({"texto": texto, "imagem_preview": None, "imagem_base64": None, "imagem_mime": None})

    def enviar_mensagem(self, payload: dict) -> None:
        """Público (2026-09-06) - MESMO caminho de envio usado pelo campo
        deste painel e pelo `InputBar` do Conversation Overlay
        (`conversation_overlay/conversation_controller.py`) - o histórico
        deste painel continua sendo populado silenciosamente mesmo
        escondido, então "Ver completo"/"Expandir" de um bubble já abre
        com o contexto inteiro, sem precisar re-enviar nada.

        `payload` (2026-09-07, Ctrl+V/anexo de imagem no Conversation
        Overlay) - dict `{"texto", "imagem_preview" (QPixmap|None -
        **corrigido no mesmo dia**: o histórico daqui mostrava só um
        marcador de texto "🖼", nunca a imagem de verdade, achado ao vivo
        pelo usuário - agora renderiza a miniatura de verdade, MESMO
        bubble do Conversation Overlay), "imagem_base64"/"imagem_mime"
        (já comprimidos, ver `input_bar.py`)}` - `_enviar` acima (campo
        nativo deste painel) sempre manda os 2 últimos como `None` (sem
        suporte a anexo aqui, só no overlay)."""
        texto = payload["texto"]
        id_mensagem = uuid.uuid4().hex
        self._adicionar_mensagem("usuario", texto, imagem=payload.get("imagem_preview"))
        evento = mascot_events.evento_chat_submitted(
            id_mensagem, texto,
            imagem_base64=payload.get("imagem_base64"), imagem_mime=payload.get("imagem_mime") or "image/jpeg",
        )
        if not self._enviar_evento(evento):
            self.falha_envio.emit(MOTIVO_SEM_CONEXAO)

    def _pedir_parar(self) -> None:
        self._enviar_evento(mascot_events.evento_stop_speaking_requested())

    @property
    def modo_voz_atual(self) -> str | None:
        """Público (2026-09-06) - o Nível 1 do Menu SAO lê isto pra saber
        qual ícone/rótulo mostrar como indicador permanente do modo ativo
        (`menu_sao.py::_atualizar_circulo_voz_nivel1`), sem duplicar
        estado próprio."""
        return self._modo_voz_atual

    def definir_modo_voz(self, modo: str | None) -> None:
        """Aplica um modo ESPECÍFICO direto (2026-09-06) - usado pelo
        Nível 2 do Menu SAO ("seleciona -> aplica imediatamente -> retorna
        ao Nível 1") além do ciclo do próprio botão do painel
        (`ciclar_modo_voz` abaixo só chama isto pro próximo passo do
        ciclo) - fonte ÚNICA que de fato muda `_modo_voz_atual`/manda o
        evento pra GAIA/emite `modo_voz_alterado`, pra nunca duas UIs
        divergirem do mesmo estado."""
        self._modo_voz_atual = modo
        self._botao_mic.setText(MODOS_VOZ_ROTULO[modo])
        self._enviar_evento(mascot_events.evento_voice_toggle_requested(modo))
        self.modo_voz_alterado.emit(modo)

    def ciclar_modo_voz(self) -> None:
        """Público (2026-09-02) - o botão de microfone do próprio painel
        usa isto; o Menu SAO ("Voz") passou a ter um Nível 2 de seleção
        direta em vez de ciclar (`definir_modo_voz` acima, 2026-09-06),
        mas os dois convergem no MESMO setter - rótulo do painel e do menu
        nunca divergem."""
        indice = MODOS_VOZ_CICLO.index(self._modo_voz_atual)
        self.definir_modo_voz(MODOS_VOZ_CICLO[(indice + 1) % len(MODOS_VOZ_CICLO)])

    def _enviar_evento(self, mensagem: dict) -> bool:
        """Devolve `False` quando não há bridge (modo demonstração/GAIA
        desconectada) - `enviar_mensagem` usa isso pra emitir `falha_envio`
        além de registrar no histórico deste painel; os outros usos
        (`ciclar_modo_voz`/`definir_modo_voz`/`_pedir_parar`) ignoram o
        retorno, o histórico silencioso já basta pra eles."""
        bridge = self._obter_bridge()
        if bridge is None:
            self._adicionar_mensagem("sistema", MOTIVO_SEM_CONEXAO)
            return False
        bridge.enviar(mensagem)
        return True

    # ------------------------------------------------------------------
    def receber_resposta(self, mensagem: dict) -> None:
        texto = mensagem.get("text", "")
        self._adicionar_mensagem("gaia", texto)

    def receber_mensagem_usuario(self, mensagem: dict) -> None:
        """Eco de um turno que NÃO veio daqui (voz contínua, clique-pra-
        falar, chat de texto do Painel principal - ver `core/mascot_events.
        py::evento_user_message`) - achado ao vivo (2026-09-01): "falei no
        modo de voz mas não apareceu no CompanionPanel", porque antes só as
        mensagens enviadas POR ESTA janela apareciam nela."""
        texto = mensagem.get("text", "")
        self._adicionar_mensagem("usuario", texto)

    def _adicionar_mensagem(self, remetente: str, texto: str, imagem=None) -> None:
        """`remetente`: vocabulário do `bubble.Bubble` (`"gaia"`/`"usuario"`/
        `"sistema"`, ver `_redesenhar_mensagens`) - não mais os rótulos
        capitalizados de antes ("Galateia"/"Você"/"Sistema"), já que cada
        bubble mostra sua PRÓPRIA identidade visual (avatar), sem precisar
        de um prefixo de texto pra dizer quem falou. `imagem` (2026-09-07,
        Ctrl+V/anexo no Conversation Overlay) - `QPixmap|None`, ver
        `enviar_mensagem`."""
        self._mensagens.append((remetente, texto, imagem))
        self._mensagens = self._mensagens[-MAXIMO_MENSAGENS:]
        # 2026-09-07: este painel nunca mais é mostrado de verdade
        # (histórico virou uma VIEW do próprio `BubbleStack`, ver
        # `bubble_stack.py`/`conversation_controller.py`) - reconstruir
        # `Bubble`s (custo real: escala de imagem, medição de fonte) toda
        # vez que uma mensagem chega, pra uma janela que NUNCA aparece,
        # seria desperdício puro. `isVisible()` guarda contra esse custo
        # sem apagar a lógica (continua funcionando se este painel for
        # mostrado manualmente de novo por algum motivo futuro).
        if self.isVisible():
            self._redesenhar_mensagens()

    def _redesenhar_mensagens(self) -> None:
        """Reconstrói o histórico inteiro como `Bubble`s embutidos
        (2026-09-07, pedido do usuário: "quero q apareca as bubble" em vez
        da lista de texto simples de antes, "essa tela feia") - MESMA
        pintura/avatar/miniatura de imagem do Conversation Overlay
        (`bubble.Bubble(..., embutido=True)`), só que como widget FILHO
        normal numa lista vertical rolável, alinhado esquerda/direita/
        centro conforme `bubble.alinhamento` (dentro de um `QWidget`
        wrapper por linha, pra `deleteLater()` limpar bubble+wrapper de
        uma vez, nunca vazar widget órfão)."""
        while self._lay_mensagens.count() > 1:
            item = self._lay_mensagens.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for remetente, texto, imagem in self._mensagens:
            bolha = bubble_module.Bubble(
                remetente, texto, imagem=imagem,
                embutido=True, largura_maxima=LARGURA_MAXIMA_BUBBLE_HISTORICO,
            )
            linha = QWidget()
            layout_linha = QHBoxLayout(linha)
            layout_linha.setContentsMargins(0, 0, 0, 0)
            if bolha.alinhamento == "direita":
                layout_linha.addStretch(1)
                layout_linha.addWidget(bolha)
            elif bolha.alinhamento == "esquerda":
                layout_linha.addWidget(bolha)
                layout_linha.addStretch(1)
            else:
                layout_linha.addStretch(1)
                layout_linha.addWidget(bolha)
                layout_linha.addStretch(1)
            self._lay_mensagens.insertWidget(self._lay_mensagens.count() - 1, linha)
        barra = self._scroll.verticalScrollBar()
        if barra is not None:
            barra.setValue(barra.maximum())
