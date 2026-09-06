# -*- coding: utf-8 -*-
"""Halo (brilho auxiliar) ao redor da personagem. SEM asset novo de propósito - a Galateia é
100% vídeo/animação pré-renderizada (não um rig ao vivo tipo VTube Studio),
e gerar uma variação de CADA clipe pra CADA cor de halo não escala. O halo
é pintado por cima do quadro atual (`QPainter`, gradiente radial), a mesma
técnica já usada em `ui/qt_widgets.py::Switch`/`CheckboxQuadrado` (pintura
à mão, não imagem).

**Redesenhado (2026-09-02, pedido do usuário: "Acho q esse halo é
essencial apenas p questao de voz")** - a 1ª versão (Fase 5, 2026-09-01)
reagia a ESTADO SEMÂNTICO da conversa (listening/transcribing/error) +
EMOÇÃO persistida, mas na prática quase nunca aparecia: nenhum caminho
real de voz chamava `notificar_estado("listening", ...)` (só teste),
"thinking"/"speaking"/"idle" não tinham cor própria, e sem uma emoção
não-neutra marcada o halo simplesmente ficava sem nada pra mostrar -
achado ao vivo pelo usuário ("qnd comecei falar com ela sumiu, em momento
algum voltou"). Substituído por um sinal mais estável: o halo agora
reflete o MODO DE VOZ atual (`PainelQt.modo_de_voz_atual`, `run.py`) -
dourado em voz contínua (inclui "ouvir som do PC", mesma família de
"escuta sempre ligada"), verde em clique-pra-falar, nenhum halo com a voz
desligada. Dura o tempo inteiro do modo (não um pulso transitório de
alguns segundos), então nunca mais "desaparece sem explicação".

**Fácil de substituir depois (pedido do usuário, 2026-09-01: "faz de uma
forma que seja fácil substituir depois")** - toda a lógica de ESTADO
(`definir_modo_voz`, decide cor) é separada da lógica de DESENHO
(`pintar`). Se um dia existir arte de verdade pro halo (ex.: um PNG/GIF
de brilho), só `pintar()` precisa mudar (trocar o gradiente por um
`drawPixmap`) - `MascotWindow` continua igual, ela só chama
`self._halo.pintar(...)` sem saber COMO o brilho é desenhado."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QRadialGradient

COR_VOZ_CONTINUA = "#d4af6a"  # dourado (mesmo tom de GAIA_GOLD, companion_style.py)
COR_CLICK_TO_TALK = "#7bc47f"  # verde suave, mesmo tom pastel dos outros

# "ouvir_pc" (escutar áudio do PC em vez do microfone) é outra forma de
# escuta contínua - mesma cor de "voz_continua", nunca uma 3ª cor própria
# só pra essa variante.
CORES_POR_MODO = {
    "voz_continua": COR_VOZ_CONTINUA,
    "ouvir_pc": COR_VOZ_CONTINUA,
    "click_to_talk": COR_CLICK_TO_TALK,
}

INTENSIDADE = 0.45


class Halo:
    """Estado puro (`definir_modo_voz`) + desenho (`pintar`) - de propósito
    SEM QObject/sinal, não precisa de `QApplication` rodando pra testar a
    lógica de decisão de cor (só `pintar` usa Qt de verdade, via
    `QPainter` recebido de quem chama)."""

    def __init__(self) -> None:
        self.cor_hex: str | None = None

    def definir_modo_voz(self, modo: str | None) -> None:
        self.cor_hex = CORES_POR_MODO.get(modo or "")

    @property
    def ativo(self) -> bool:
        return self.cor_hex is not None

    def pintar(self, painter: QPainter, centro: QPointF, raio_base: float) -> None:
        """Chamado de dentro do `paintEvent` de quem instanciar (`MascotWindow`),
        ANTES de desenhar o quadro da animação por cima (o halo fica atrás
        da personagem, nunca cobrindo ela). `raio_base` já deve refletir a
        escala atual da janela - quem chama decide o tamanho, este método
        só pinta."""
        if self.cor_hex is None or raio_base <= 0:
            return
        cor_cheia = QColor(self.cor_hex)
        cor_cheia.setAlphaF(INTENSIDADE)
        cor_vazia = QColor(self.cor_hex)
        cor_vazia.setAlphaF(0.0)

        gradiente = QRadialGradient(centro, raio_base)
        gradiente.setColorAt(0.0, cor_vazia)
        gradiente.setColorAt(0.72, cor_cheia)
        gradiente.setColorAt(1.0, cor_vazia)

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradiente)
        painter.drawEllipse(centro, raio_base, raio_base)
        painter.restore()
