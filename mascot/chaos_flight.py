# -*- coding: utf-8 -*-
"""Janela secundária efêmera pro personagem "caos" (`state_catalog`/
`data/animacoes_galateia.json`: `caos_voando_loop`) subir sozinho até
sair do monitor, separado da Gaia - achado com o usuário 2026-09-02:
"o trazendo-caos_para_flutuando termina com o caos separado da gaia, e é
ele que tem que subir todo monitor", enquanto ELA continua na PRÓPRIA
janela fazendo `flutuando_idle` normalmente. Como `AnimationController`/
`MascotWindow` só tocam UM clipe por vez (uma personagem, não uma
colônia - `ARQUITETURA.md`, "Princípios"), mostrar as duas coisas se movendo de forma
independente ao mesmo tempo precisa de uma segunda janela, só pra isso -
sem estado, sem grafo, sem clique, some sozinha quando sai da tela.

Alinhamento com o vídeo anterior (`trazendo-caos_para_flutuando`): o
caos aparece sempre no mesmo canto daquela cena (medido a mão, varredura
de alpha no último quadro real) e o loop dele (`caos_voando_loop`) o
desenha quase no mesmo lugar dentro da PRÓPRIA célula - `iniciar()` usa
os dois pontos pra a troca de vídeo pra janela não pular de lugar.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QWidget

from mascot import platform_windows
from mascot.asset_repository import AnimationAsset, carregar_geometria_esperada

logger = logging.getLogger(__name__)

ANIMATION_ID = "caos_voando_loop"

# ponto (px, dentro da célula 612x344 comum) onde o caos aparece no
# ÚLTIMO quadro real de `trazendo-caos_para_flutuando` - varredura de
# alpha (metade direita da célula, pra não pegar a Gaia), bbox
# (400,118)-(526,209), centro arredondado.
PONTO_CAOS_NO_VIDEO_ANTERIOR = (463, 164)

# ponto (px, dentro da própria célula de `caos_voando_loop`) onde o caos
# fica desenhado nesse loop - mesma varredura de alpha, bbox
# (480,119)-(526,202), centro arredondado.
PONTO_CAOS_NO_PROPRIO_LOOP = (503, 160)

DURACAO_SUBIDA_MS = 2000.0
PASSO_MS = 16


class ChaosFlightWindow(QWidget):
    """Sobe em linha reta a partir do ponto de ancoragem até sair por
    cima da tela atual, tocando `caos_voando_loop` em cachimbo (loop) o
    tempo todo - sem duração combinada com a subida (`DURACAO_SUBIDA_MS`
    manda na física, o loop só continua girando por cima)."""

    encerrado = Signal()

    def __init__(self, ponto_ancora_tela: QPoint, escala: float = 1.0, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._asset = AnimationAsset.carregar(ANIMATION_ID, carregar_geometria_esperada())
        self._indice_quadro = 0

        largura = max(1, round(self._asset.cell_width * escala))
        altura = max(1, round(self._asset.cell_height * escala))
        self.resize(largura, altura)
        self.move(
            ponto_ancora_tela.x() - round(PONTO_CAOS_NO_PROPRIO_LOOP[0] * escala),
            ponto_ancora_tela.y() - round(PONTO_CAOS_NO_PROPRIO_LOOP[1] * escala),
        )

        self._timer_quadro = QTimer(self)
        self._timer_quadro.timeout.connect(self._avancar_quadro)
        self._timer_quadro.start(self._asset.frame_duration_ms)

        tela = self.screen() or QApplication.primaryScreen()
        _area_x, area_y, _area_w, _area_h = platform_windows.obter_work_area_da_tela(tela)
        self._limite_saida_y = area_y - self.height()
        distancia_total = max(1.0, self.y() - self._limite_saida_y)
        self._passo_subida_px = distancia_total / DURACAO_SUBIDA_MS * PASSO_MS

        self._timer_subida = QTimer(self)
        self._timer_subida.timeout.connect(self._subir)
        self._timer_subida.start(PASSO_MS)

        self.show()

    def _avancar_quadro(self) -> None:
        self._indice_quadro = (self._indice_quadro + 1) % self._asset.frame_count
        self.update()

    def _subir(self) -> None:
        nova_y = self.y() - self._passo_subida_px
        if nova_y <= self._limite_saida_y:
            self._encerrar()
            return
        self.move(self.x(), round(nova_y))

    def _encerrar(self) -> None:
        self._timer_quadro.stop()
        self._timer_subida.stop()
        self.hide()
        self.encerrado.emit()
        self.deleteLater()

    def paintEvent(self, event) -> None:  # noqa: D401 - Qt override
        pintor = QPainter(self)
        pintor.drawPixmap(self.rect(), self._asset.frames[self._indice_quadro], self._asset.frames[self._indice_quadro].rect())


def iniciar(ponto_ancora_tela: QPoint, escala: float = 1.0) -> ChaosFlightWindow:
    """Fábrica fininha só pra manter `window.py` sem precisar conhecer
    `AnimationAsset`/`carregar_geometria_esperada` diretamente."""
    return ChaosFlightWindow(ponto_ancora_tela, escala=escala)
