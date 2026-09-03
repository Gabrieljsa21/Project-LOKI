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
autônomo)."""
from __future__ import annotations

import html
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget

from core import mascot_events
from mascot import companion_style as estilo
from mascot import platform_windows

LARGURA = 420
ALTURA = 520
MAXIMO_MENSAGENS = 20

# 🔥 Ciclo simples (sem confirmação de volta - plano seção 9.2: "microfone
# controla o modo de voz existente, sem segunda captura") - mesmo
# vocabulário de `PainelQt.disparar_modo`/`evento_voice_toggle_requested`.
MODOS_VOZ_CICLO = (None, "voz_continua", "click_to_talk")
MODOS_VOZ_ROTULO = {
    None: "🎤 Voz desligada",
    "voz_continua": "🎤 Voz contínua",
    "click_to_talk": "🎤 Clique-pra-falar",
}


class CompanionPanel(QWidget):
    # 🔥 Sinal pra alternar visibilidade de QUALQUER thread com segurança
    # (mesmo motivo de `MascotSupervisor._enviar_solicitado` -
    # `integrations/mascot/supervisor.py`) - o hotkey global (lib `keyboard`,
    # `process_main.py`) roda num listener thread PRÓPRIO, não na thread do
    # Qt; chamar `alternar_visibilidade()` direto de lá mexeria em widgets
    # fora da thread dona. Emitir este sinal marshalla automaticamente pra
    # cá (a thread que criou este QWidget).
    alternar_visibilidade_solicitado = Signal()

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
        self._mensagens: list[tuple[str, str]] = []
        self._modo_voz_atual = None

        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(LARGURA, ALTURA)
        self.setStyleSheet(
            f"background-color: {estilo.SURFACE_COLOR}; border: 1px solid {estilo.BORDA_SUTIL}; border-radius: 10px;"
        )
        self.setWindowTitle("Galateia")

        self._montar_ui()
        self.alternar_visibilidade_solicitado.connect(self.alternar_visibilidade)
        self.hide()

    def _montar_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        titulo = QLabel("Galateia")
        titulo.setStyleSheet(f"color: {estilo.GAIA_GOLD}; font-weight: bold; font-size: 14px; font-family: '{estilo.FONTE_BASE}';")
        lay.addWidget(titulo)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border: none; background: transparent;")
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
        id_mensagem = uuid.uuid4().hex
        self._adicionar_mensagem("Você", texto)
        self._enviar_evento(mascot_events.evento_chat_submitted(id_mensagem, texto))

    def _pedir_parar(self) -> None:
        self._enviar_evento(mascot_events.evento_stop_speaking_requested())

    def ciclar_modo_voz(self) -> None:
        """Público (2026-09-02) - o Menu SAO ("Voz", `menu_sao.py`) chama o
        MESMO ciclo daqui em vez de duplicar estado de modo de voz próprio,
        pra rótulo do botão do painel e do menu nunca divergirem."""
        indice = MODOS_VOZ_CICLO.index(self._modo_voz_atual)
        self._modo_voz_atual = MODOS_VOZ_CICLO[(indice + 1) % len(MODOS_VOZ_CICLO)]
        self._botao_mic.setText(MODOS_VOZ_ROTULO[self._modo_voz_atual])
        self._enviar_evento(mascot_events.evento_voice_toggle_requested(self._modo_voz_atual))

    def _enviar_evento(self, mensagem: dict) -> None:
        bridge = self._obter_bridge()
        if bridge is None:
            self._adicionar_mensagem("Sistema", "Sem conexão com a GAIA (modo demonstração).")
            return
        bridge.enviar(mensagem)

    # ------------------------------------------------------------------
    def receber_resposta(self, mensagem: dict) -> None:
        texto = mensagem.get("text", "")
        self._adicionar_mensagem("Galateia", texto)

    def receber_mensagem_usuario(self, mensagem: dict) -> None:
        """Eco de um turno que NÃO veio daqui (voz contínua, clique-pra-
        falar, chat de texto do Painel principal - ver `core/mascot_events.
        py::evento_user_message`) - achado ao vivo (2026-09-01): "falei no
        modo de voz mas não apareceu no CompanionPanel", porque antes só as
        mensagens enviadas POR ESTA janela apareciam nela."""
        texto = mensagem.get("text", "")
        self._adicionar_mensagem("Você", texto)

    def _adicionar_mensagem(self, remetente: str, texto: str) -> None:
        self._mensagens.append((remetente, texto))
        self._mensagens = self._mensagens[-MAXIMO_MENSAGENS:]
        self._redesenhar_mensagens()

    def _redesenhar_mensagens(self) -> None:
        while self._lay_mensagens.count() > 1:
            item = self._lay_mensagens.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for remetente, texto in self._mensagens:
            # 🔥 `html.escape` - texto puro (sem parse de Markdown no MVP, ver
            # docstring do módulo), mas o rótulo `<b>` já faz o QLabel tratar
            # a string inteira como rich text, então o texto do usuário/GAIA
            # precisa vir escapado pra não ser interpretado como HTML.
            bolha = QLabel(f"<b>{html.escape(remetente)}:</b> {html.escape(texto)}")
            bolha.setWordWrap(True)
            bolha.setStyleSheet(f"color: {estilo.TEXT_COLOR}; padding: 4px; font-family: '{estilo.FONTE_BASE}';")
            self._lay_mensagens.insertWidget(self._lay_mensagens.count() - 1, bolha)
        barra = self._scroll.verticalScrollBar()
        if barra is not None:
            barra.setValue(barra.maximum())
