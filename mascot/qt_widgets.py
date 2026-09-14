# -*- coding: utf-8 -*-
"""Widgets reutilizáveis em PySide6, vendorizados de `Project G.A.I.A/
assistant/ui/qt_widgets.py` (mesmo padrão de `Project-IRIS/iris/ui/
qt_widgets.py`) - só o subconjunto genuinamente usado pelo modal de
configurações do LOKI (`mascot/modal_configuracoes.py`) e pelo bootstrap
da `QApplication` (`mascot/process_main.py`). Trazido conforme a
necessidade foi aparecendo (2026-09-04: `criar_frame_item`/`criar_lineedit`,
pra alinhar `gesture_wheel_editor.py` com o mesmo padrão visual do modal
Avatar Virtual da GAIA) - o arquivo original ainda tem mais widgets/helpers
usados só por outras telas do Painel (FlowLayout de cards, textbox, link
clicável) que continuam de fora por não serem necessários aqui - zero
dependência de GAIA em nada abaixo.

Cópia deliberada, não import cruzando repositórios (mesmo raciocínio de
`core/mascot_events.py`, ver `docs/ARQUITETURA.md`) - se o original mudar uma
regra de estilo que também vale aqui, replicar manualmente."""
import os

from PySide6.QtCore import Qt, QRect, QRectF, QPoint, QSize, QTimer, QPropertyAnimation, QEasingCurve, Property, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPainterPath, QPen, QIcon, QIntValidator, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QMessageBox, QPushButton, QLineEdit, QScrollArea, QWidget, QSlider,
    QStyledItemDelegate, QStyle, QTabWidget,
)

BG_COLOR = "#0d0d0f"
SURFACE_COLOR = "#1a1a1d"
HIGHLIGHT_COLOR = "#28282c"
BORDA_SUTIL = "#2f2f34"
GAIA_GOLD = "#d4af6a"
GAIA_GOLD_HOVER = "#e3c284"
GAIA_SILVER = "#d9d9dc"
TEXT_COLOR = "#f1efe9"
TEXT_DIM = "#8f8d8a"
FONTE_BASE = "Segoe UI"

COR_HOVER_ITEM = "#33333a"
COR_BOLINHA_SWITCH_LIGADO = HIGHLIGHT_COLOR
COR_BOLINHA_SWITCH_DESLIGADO = TEXT_COLOR


def cor_com_alpha(cor_hex, alpha):
    cor_hex = cor_hex.lstrip("#")
    r, g, b = (int(cor_hex[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


class ModalBase(QDialog):
    """QDialog base pra TODO modal - habilita minimizar/maximizar (o Qt só dá
    botão de fechar por padrão pra QDialog)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)


class Switch(QCheckBox):
    """Toggle animado (trilho + bolinha deslizando) - texto ao lado troca
    sozinho entre `texto_on`/`texto_off` conforme o estado."""

    def __init__(self, texto_on, texto_off, cor=GAIA_GOLD, marcado=False,
                 cor_bolinha_ligado=COR_BOLINHA_SWITCH_LIGADO,
                 cor_bolinha_desligado=COR_BOLINHA_SWITCH_DESLIGADO,
                 icone_arquivo=None, parent=None):
        super().__init__(parent)
        self.texto_on = texto_on
        self.texto_off = texto_off
        self.cor = QColor(cor)
        self._pixmap_icone = None
        if icone_arquivo and os.path.exists(icone_arquivo):
            self._pixmap_icone = QPixmap(icone_arquivo).scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.cor_bolinha_ligado = QColor(cor_bolinha_ligado)
        self.cor_bolinha_desligado = QColor(cor_bolinha_desligado)
        self._pos_bolinha = 1.0 if marcado else 0.0
        self.setCursor(Qt.PointingHandCursor)
        self.setChecked(marcado)
        self.setText(texto_on if marcado else texto_off)
        self.setFont(QFont(FONTE_BASE, 11))
        self.stateChanged.connect(self._ao_mudar_estado)

        self._anim = QPropertyAnimation(self, b"pos_bolinha")
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def _obter_pos_bolinha(self):
        return self._pos_bolinha

    def _definir_pos_bolinha(self, valor):
        self._pos_bolinha = valor
        self.update()

    pos_bolinha = Property(float, _obter_pos_bolinha, _definir_pos_bolinha)

    def _ao_mudar_estado(self, estado):
        marcado = bool(estado)
        self.setText(self.texto_on if marcado else self.texto_off)
        self._anim.stop()
        self._anim.setStartValue(self._pos_bolinha)
        self._anim.setEndValue(1.0 if marcado else 0.0)
        self._anim.start()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def sizeHint(self):
        fm = self.fontMetrics()
        largura_maior_texto = max(fm.horizontalAdvance(self.texto_on), fm.horizontalAdvance(self.texto_off))
        largura_icone = (self._pixmap_icone.width() + 6) if self._pixmap_icone else 0
        return QSize(46 + 8 + largura_icone + largura_maior_texto, 26)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        largura_trilho, altura_trilho = 42, 21
        y_trilho = (26 - altura_trilho) / 2
        cor_trilho = self.cor if self.isChecked() else QColor(HIGHLIGHT_COLOR)
        painter.setBrush(cor_trilho)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, int(y_trilho), largura_trilho, altura_trilho, altura_trilho / 2, altura_trilho / 2)

        raio_bolinha = altura_trilho / 2 - 2
        x_bolinha = 2 + raio_bolinha + self._pos_bolinha * (largura_trilho - altura_trilho)
        cor_bolinha = self.cor_bolinha_ligado if self.isChecked() else self.cor_bolinha_desligado
        painter.setBrush(cor_bolinha)
        painter.drawEllipse(QPoint(int(x_bolinha), int(y_trilho + altura_trilho / 2)), int(raio_bolinha), int(raio_bolinha))

        x_texto = largura_trilho + 8
        if self._pixmap_icone:
            painter.drawPixmap(x_texto, int((26 - self._pixmap_icone.height()) / 2), self._pixmap_icone)
            x_texto += self._pixmap_icone.width() + 6

        painter.setPen(QColor(TEXT_COLOR))
        painter.setFont(self.font())
        painter.drawText(QRect(x_texto, 0, self.width() - x_texto, 26), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        painter.end()


class CheckboxQuadrado(QCheckBox):
    """Checkbox quadrado (vazio quando desmarcado, preenchido de dourado com
    check branco quando marcado) - pintado via `QPainter`, não QSS."""

    def __init__(self, texto="", marcado=False, cor=GAIA_GOLD, icone_arquivo=None, parent=None):
        super().__init__(parent)
        self.cor = QColor(cor)
        self.setCursor(Qt.PointingHandCursor)
        self.setChecked(marcado)
        self.setText(texto)
        self.setFont(QFont(FONTE_BASE, 11))
        self._pixmap_icone = None
        if icone_arquivo and os.path.exists(icone_arquivo):
            self._pixmap_icone = QPixmap(icone_arquivo).scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    _TAMANHO_CAIXA = 17

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def sizeHint(self):
        fm = self.fontMetrics()
        largura_icone = (self._pixmap_icone.width() + 6) if self._pixmap_icone else 0
        altura = max(self._TAMANHO_CAIXA, fm.height()) + 4
        return QSize(self._TAMANHO_CAIXA + 8 + largura_icone + fm.horizontalAdvance(self.text()), altura)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        tam = self._TAMANHO_CAIXA
        y_caixa = (self.height() - tam) / 2

        if self.isChecked():
            painter.setBrush(self.cor)
            painter.setPen(Qt.NoPen)
        else:
            painter.setBrush(QColor(HIGHLIGHT_COLOR))
            painter.setPen(QColor(BORDA_SUTIL))
        painter.drawRoundedRect(QRectF(0, y_caixa, tam, tam), 5, 5)

        if self.isChecked():
            caminho = QPainterPath()
            caminho.moveTo(tam * 0.22, tam * 0.55)
            caminho.lineTo(tam * 0.42, tam * 0.75)
            caminho.lineTo(tam * 0.80, tam * 0.30)
            caneta = QPen(QColor(BG_COLOR), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(caneta)
            painter.translate(0, y_caixa)
            painter.drawPath(caminho)
            painter.translate(0, -y_caixa)

        x_texto = tam + 8
        if self._pixmap_icone:
            painter.drawPixmap(x_texto, int((self.height() - self._pixmap_icone.height()) / 2), self._pixmap_icone)
            x_texto += self._pixmap_icone.width() + 6

        painter.setPen(QColor(TEXT_COLOR))
        painter.setFont(self.font())
        painter.drawText(QRect(x_texto, 0, self.width() - x_texto, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        painter.end()


class DelegadoItemDropdown(QStyledItemDelegate):
    """Pinta cada linha do popup do dropdown via `QPainter` direto (QSS
    `::item:selected`/`::item:hover` não renderiza nesta stack de Qt)."""

    def __init__(self, parent=None, cor_selecionado=GAIA_GOLD, cor_texto_selecionado=BG_COLOR,
                 cor_hover=COR_HOVER_ITEM, cor_normal=HIGHLIGHT_COLOR, cor_texto_normal=TEXT_COLOR):
        super().__init__(parent)
        self.cor_selecionado = QColor(cor_selecionado)
        self.cor_texto_selecionado = QColor(cor_texto_selecionado)
        self.cor_hover = QColor(cor_hover)
        self.cor_normal = QColor(cor_normal)
        self.cor_texto_normal = QColor(cor_texto_normal)

    def paint(self, painter, option, index):
        painter.save()
        selecionado = bool(option.state & QStyle.State_Selected)
        em_hover = bool(option.state & QStyle.State_MouseOver)

        if selecionado:
            cor_fundo, cor_texto = self.cor_selecionado, self.cor_texto_selecionado
        elif em_hover:
            cor_fundo, cor_texto = self.cor_hover, self.cor_texto_normal
        else:
            cor_fundo, cor_texto = self.cor_normal, self.cor_texto_normal

        painter.fillRect(option.rect, cor_fundo)
        painter.setPen(cor_texto)
        painter.setFont(option.font)
        area = option.rect.adjusted(10, 0, -10, 0)
        texto = QFontMetrics(option.font).elidedText(index.data(Qt.DisplayRole) or "", Qt.ElideRight, area.width())
        painter.drawText(area, Qt.AlignVCenter | Qt.AlignLeft, texto)
        painter.restore()

    def sizeHint(self, option, index):
        tamanho = super().sizeHint(option, index)
        return QSize(min(tamanho.width(), 500), 26)


class ComboBoxSemScrollAcidental(QComboBox):
    """`QComboBox` que nunca muda de valor com scroll enquanto está FECHADO,
    desenha a própria seta dourada, e sempre abre o popup colado embaixo."""

    def __init__(self, cor_seta=GAIA_GOLD, parent=None):
        super().__init__(parent)
        self.cor_seta = QColor(cor_seta)

    def wheelEvent(self, event):
        event.ignore()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.cor_seta)
        cx = self.width() - 16
        cy = self.height() / 2
        seta = QPainterPath()
        seta.moveTo(cx - 4, cy - 2)
        seta.lineTo(cx + 4, cy - 2)
        seta.lineTo(cx, cy + 3)
        seta.closeSubpath()
        painter.drawPath(seta)
        painter.end()

    def showPopup(self):
        super().showPopup()
        container = self.view().window()
        container.move(self.mapToGlobal(QPoint(0, self.height())))


class _CampoValorSpinbox(QLineEdit):
    """Campo de número da SpinboxCapsula - seleciona o texto inteiro ao
    focar, pra digitar um valor novo sem apagar o antigo primeiro."""

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)


class SpinboxCapsula(QWidget):
    """Campo numérico "cápsula" (botões +/- redondos) substituindo o
    `QSpinBox` nativo. Número central é editável (clique e digite direto)."""

    valueChanged = Signal(int)

    _TAMANHO_BOTAO = 20

    def __init__(self, minimo, maximo, valor_atual, largura=None, passo=1, parent=None):
        super().__init__(parent)
        self._minimo = minimo
        self._maximo = maximo
        self._passo = passo
        self._valor = max(minimo, min(maximo, valor_atual))

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("SpinboxCapsula")
        self.setFixedHeight(self._TAMANHO_BOTAO + 6)
        self.setFixedWidth(self._largura_minima_necessaria(largura))
        self.setStyleSheet(f"""
            QWidget#SpinboxCapsula {{
                background-color: {HIGHLIGHT_COLOR};
                border: 1px solid {BORDA_SUTIL};
                border-radius: {(self._TAMANHO_BOTAO + 6) // 2}px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        self._botao_menos = self._criar_botao("−", self._decrementar)
        self._label_valor = _CampoValorSpinbox(str(self._valor))
        self._label_valor.setAlignment(Qt.AlignCenter)
        self._label_valor.setFrame(False)
        self._label_valor.setValidator(QIntValidator(self._minimo, self._maximo, self._label_valor))
        self._label_valor.setStyleSheet(f"""
            QLineEdit {{
                color: {TEXT_COLOR};
                font-family: Consolas;
                font-size: 12px;
                border: none;
                background: transparent;
                padding: 0px;
            }}
        """)
        self._label_valor.editingFinished.connect(self._ao_editar_texto)
        self._botao_mais = self._criar_botao("+", self._incrementar)

        layout.addWidget(self._botao_menos)
        layout.addWidget(self._label_valor, stretch=1)
        layout.addWidget(self._botao_mais)

    def _largura_minima_necessaria(self, largura_pedida):
        texto_maior = str(max(abs(self._minimo), abs(self._maximo)))
        if self._minimo < 0:
            texto_maior = "-" + texto_maior
        largura_texto = QFontMetrics(QFont("Consolas", 12)).horizontalAdvance(texto_maior)
        minima = self._TAMANHO_BOTAO * 2 + 6 + 4 + largura_texto + 14
        return max(largura_pedida or 0, minima)

    def _criar_botao(self, texto, ao_clicar):
        botao = QPushButton(texto)
        botao.setFixedSize(self._TAMANHO_BOTAO, self._TAMANHO_BOTAO)
        botao.setCursor(Qt.PointingHandCursor)
        botao.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_DIM};
                border: none;
                border-radius: {self._TAMANHO_BOTAO // 2}px;
                font-size: 14px;
                font-weight: 600;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {cor_com_alpha(GAIA_GOLD, 0.18)};
                color: {GAIA_GOLD};
            }}
        """)
        botao.clicked.connect(ao_clicar)
        return botao

    def _decrementar(self, checked=False):
        self.setValue(self._valor - self._passo)

    def _incrementar(self, checked=False):
        self.setValue(self._valor + self._passo)

    def _ao_editar_texto(self):
        try:
            novo_valor = int(self._label_valor.text().strip())
        except ValueError:
            novo_valor = self._valor
        self.setValue(novo_valor)

    def value(self):
        return self._valor

    def setValue(self, novo_valor):
        novo_valor = max(self._minimo, min(self._maximo, novo_valor))
        mudou = novo_valor != self._valor
        self._valor = novo_valor
        self._label_valor.setText(str(novo_valor))
        if mudou:
            self.valueChanged.emit(novo_valor)

    def setRange(self, minimo, maximo):
        self._minimo = minimo
        self._maximo = maximo
        self.setValue(self._valor)


class ScrollAreaArrastavel(QScrollArea):
    """`QScrollArea` que também deixa arrastar o conteúdo segurando o botão
    do meio do mouse, em qualquer direção."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._arrastando = False
        self._pos_inicial = None
        self._scroll_h_inicial = 0
        self._scroll_v_inicial = 0

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._arrastando = True
            self._pos_inicial = event.position()
            self._scroll_h_inicial = self.horizontalScrollBar().value()
            self._scroll_v_inicial = self.verticalScrollBar().value()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._arrastando:
            delta = event.position() - self._pos_inicial
            self.horizontalScrollBar().setValue(self._scroll_h_inicial - int(delta.x()))
            self.verticalScrollBar().setValue(self._scroll_v_inicial - int(delta.y()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self._arrastando:
            self._arrastando = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


def _estilizar_caixa_mensagem(caixa):
    caixa.setStyleSheet(f"""
        QMessageBox {{ background-color: {BG_COLOR}; }}
        QMessageBox QLabel {{ color: {TEXT_COLOR}; font-family: '{FONTE_BASE}'; font-size: 11pt; }}
        QPushButton {{
            background-color: {SURFACE_COLOR};
            color: {TEXT_COLOR};
            border: 1px solid {BORDA_SUTIL};
            border-radius: 8px;
            padding: 6px 16px;
            min-width: 70px;
        }}
        QPushButton:hover {{ background-color: {HIGHLIGHT_COLOR}; }}
    """)


def confirmar_acao(parent, titulo, mensagem):
    """Diálogo Sim/Não - devolve True só se confirmado. Botão focado por
    padrão é "Não", pra um Enter sem querer não confirmar nada destrutivo."""
    caixa = QMessageBox(parent)
    caixa.setIcon(QMessageBox.Warning)
    caixa.setWindowTitle(titulo)
    caixa.setText(mensagem)
    botao_sim = caixa.addButton("Sim", QMessageBox.YesRole)
    botao_nao = caixa.addButton("Não", QMessageBox.NoRole)
    caixa.setDefaultButton(botao_nao)
    _estilizar_caixa_mensagem(caixa)
    caixa.exec()
    return caixa.clickedButton() is botao_sim


def criar_frame_item(fundo=SURFACE_COLOR, raio=8):
    """QFrame simples (sem título, sem largura fixa) pra UM item dentro de
    uma lista rolável - mesmo nível "cards" da hierarquia visual (BG_COLOR
    de fundo da janela -> SURFACE_COLOR dos cards -> HIGHLIGHT_COLOR dos
    botões/campos dentro deles)."""
    frame = QFrame()
    frame.setStyleSheet(f"background-color: {fundo}; border-radius: {raio}px;")
    return frame


def criar_lineedit(texto="", fundo=HIGHLIGHT_COLOR, negrito=False):
    campo = QLineEdit(texto)
    campo.setFixedHeight(32)
    campo.setFont(QFont(FONTE_BASE, 11, QFont.Bold if negrito else QFont.Normal))
    campo.setStyleSheet(f"""
        QLineEdit {{
            background-color: {fundo};
            color: {TEXT_COLOR};
            border: 1px solid {BORDA_SUTIL};
            border-radius: 6px;
            padding: 0 8px;
        }}
    """)
    return campo


def criar_descricao(texto, icone_arquivo=None):
    lbl = QLabel(texto)
    lbl.setWordWrap(True)
    lbl.setFont(QFont(FONTE_BASE, 10))
    lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; border: none;")
    if not (icone_arquivo and os.path.exists(icone_arquivo)):
        return lbl

    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    lbl_icone = QLabel()
    lbl_icone.setStyleSheet("background: transparent; border: none;")
    lbl_icone.setPixmap(QPixmap(icone_arquivo).scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    layout.addWidget(lbl_icone)
    layout.addWidget(lbl, stretch=1)
    return container


def criar_spinbox(minimo, maximo, valor_atual, largura=60, passo=1):
    return SpinboxCapsula(minimo, maximo, valor_atual, largura=largura, passo=passo)


def criar_botao(texto, cor_texto=GAIA_GOLD, preenchido=False, icone_arquivo=None):
    botao = QPushButton(texto)
    botao.setCursor(Qt.PointingHandCursor)
    botao.setFixedHeight(32)
    botao.setFont(QFont(FONTE_BASE, 11, QFont.Bold))
    if icone_arquivo and os.path.exists(icone_arquivo):
        botao.setIcon(QIcon(icone_arquivo))
        botao.setIconSize(QSize(20, 20))
    if preenchido:
        botao.setStyleSheet(f"""
            QPushButton {{
                background-color: {GAIA_GOLD};
                color: {BG_COLOR};
                border: none;
                border-radius: 8px;
                padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: {GAIA_GOLD_HOVER}; }}
        """)
    else:
        botao.setStyleSheet(f"""
            QPushButton {{
                background-color: {SURFACE_COLOR};
                color: {cor_texto};
                border: 1px solid {BORDA_SUTIL};
                border-radius: 8px;
                padding: 0 14px;
            }}
            QPushButton:hover {{ background-color: {HIGHLIGHT_COLOR}; }}
        """)
    return botao


def criar_scroll_area():
    """`lay.setAlignment(Qt.AlignTop)` - sem isso, um QVBoxLayout dentro de
    QScrollArea estica o espaçamento entre widgets pra preencher toda a
    altura disponível quando o conteúdo é mais curto que a área visível."""
    scroll = ScrollAreaArrastavel()
    scroll.setWidgetResizable(True)
    scroll.setStyleSheet(f"background-color: {BG_COLOR}; border: none;")
    conteudo = QWidget()
    conteudo.setStyleSheet(f"background-color: {BG_COLOR};")
    lay = QVBoxLayout(conteudo)
    lay.setAlignment(Qt.AlignTop)
    scroll.setWidget(conteudo)
    return scroll, lay


def criar_tabwidget(compacto=False):
    """Abas no mesmo padrão visual do Avatar Virtual da GAIA. `compacto`
    (sub-abas dentro de uma aba já selecionada, ex.: categorias da Gesture
    Wheel) usa um selecionado mais LEVE (sublinhado, não preenchimento
    sólido) - 2026-09-04, achado ao vivo pelo usuário ("vários elementos
    da msm cor, q n fazem conversar bem"): a aba principal e a sub-aba
    usando o MESMO dourado sólido empilhadas uma embaixo da outra liam
    como um bloco só, sem hierarquia entre "navegação principal" e
    "categoria dentro dela". Também aumentado (2026-09-04, "aumenta
    tamanho das abas dentro de Ações") - ainda menor que o principal, mas
    bem mais legível que antes."""
    abas = QTabWidget()
    abas.setDocumentMode(True)
    abas.setMovable(False)
    abas.tabBar().setExpanding(False)
    # `setDrawBase(False)` (2026-09-04, achado ao vivo com print - linha
    # branca cruzando a largura inteira, na altura do rodapé das abas,
    # visível no espaço vazio à direita da última aba) - `QTabBar` desenha
    # essa "base" por padrão, uma decoração NATIVA do widget (API do Qt,
    # não CSS) - nenhum `border`/`border-top` no QSS acima chega a
    # controlá-la. Afeta TODO `criar_tabwidget`, principal ou compacto -
    # "a interna dentro do ações tbm tem" era a mesma causa.
    abas.tabBar().setDrawBase(False)
    padding_horizontal = 10 if compacto else 12
    tamanho_fonte = 9 if compacto else 10
    margem_direita = 2 if compacto else 3
    abas.setStyleSheet(f"""
        QTabWidget::pane {{
            border: none;
            background-color: {BG_COLOR};
        }}
    """)
    if compacto:
        estilo_selecionado = f"""
            background-color: {HIGHLIGHT_COLOR};
            color: {GAIA_GOLD};
            border-color: {BORDA_SUTIL};
            border-bottom: 2px solid {GAIA_GOLD};
        """
    else:
        estilo_selecionado = f"""
            background-color: {GAIA_GOLD};
            color: {BG_COLOR};
            border-color: {GAIA_GOLD};
        """
    abas.tabBar().setStyleSheet(f"""
        QTabBar::tab {{
            background-color: {SURFACE_COLOR};
            color: {TEXT_DIM};
            padding: 9px {padding_horizontal}px;
            margin-right: {margem_direita}px;
            border: 1px solid {BORDA_SUTIL};
            border-bottom: none;
            border-top-left-radius: 7px;
            border-top-right-radius: 7px;
            font-family: '{FONTE_BASE}';
            font-size: {tamanho_fonte}pt;
            font-weight: 600;
        }}
        QTabBar::tab:selected {{
            {estilo_selecionado}
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {HIGHLIGHT_COLOR};
            color: {TEXT_COLOR};
        }}
        QTabBar QToolButton {{
            background-color: {SURFACE_COLOR};
            color: {TEXT_COLOR};
            border: 1px solid {BORDA_SUTIL};
            border-radius: 4px;
        }}
        QTabBar QToolButton:hover {{ background-color: {HIGHLIGHT_COLOR}; }}
    """)
    return abas


def criar_titulo_secao(texto, cor=GAIA_GOLD, tamanho=15, icone_arquivo=None):
    lbl = QLabel(texto)
    lbl.setFont(QFont(FONTE_BASE, tamanho, QFont.Bold))
    lbl.setStyleSheet(f"color: {cor}; background: transparent; border: none;")
    if not (icone_arquivo and os.path.exists(icone_arquivo)):
        return lbl

    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    lbl_icone = QLabel()
    lbl_icone.setStyleSheet("background: transparent; border: none;")
    lbl_icone.setPixmap(QPixmap(icone_arquivo).scaled(tamanho + 12, tamanho + 12, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    layout.addWidget(lbl_icone)
    layout.addWidget(lbl)
    layout.addStretch(1)
    return container


def criar_slider(minimo, maximo, valor_atual, cor=GAIA_GOLD):
    slider = QSlider(Qt.Horizontal)
    slider.setRange(minimo, maximo)
    slider.setValue(valor_atual)
    slider.setStyleSheet(f"""
        QSlider::groove:horizontal {{
            background-color: {HIGHLIGHT_COLOR};
            height: 6px;
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background-color: {TEXT_COLOR};
            width: 16px;
            margin: -6px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background-color: {GAIA_GOLD_HOVER};
        }}
        QSlider::sub-page:horizontal {{
            background-color: {cor};
            border-radius: 3px;
        }}
    """)
    return slider


def criar_dropdown(valores, valor_atual=None, largura=None, cor_selecionado=GAIA_GOLD):
    combo = ComboBoxSemScrollAcidental(cor_seta=cor_selecionado)
    combo.setItemDelegate(DelegadoItemDropdown(combo, cor_selecionado=cor_selecionado))
    combo.addItems(valores)
    if valor_atual is not None and valor_atual in valores:
        combo.setCurrentText(valor_atual)
    if largura:
        combo.setFixedWidth(largura)
    combo.setMaxVisibleItems(8)
    combo.setStyleSheet(f"""
        QComboBox {{
            background-color: {HIGHLIGHT_COLOR};
            color: {TEXT_COLOR};
            border: 1px solid {BORDA_SUTIL};
            border-radius: 6px;
            padding: 6px 10px;
        }}
        QComboBox::drop-down {{
            border: none;
            background: transparent;
            width: 22px;
        }}
        QComboBox::down-arrow {{
            image: none;
            width: 0px;
            height: 0px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {HIGHLIGHT_COLOR};
            color: {TEXT_COLOR};
            outline: none;
        }}
    """)
    return combo


def aplicar_estilo_global(app):
    """Chamado UMA VEZ na criação da `QApplication` (`process_main.py`) -
    força "Fusion" (senão o Windows usa o tema nativo, que ignora boa parte
    do QSS de cor/seleção) e estiliza `QScrollBar`/`QMenu` globalmente -
    inclui o `QMenu` do "Ações" (`animacao_menu.py`) e da bandeja."""
    app.setStyle("Fusion")
    app.setStyleSheet(f"""
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {GAIA_GOLD};
            border-radius: 5px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {GAIA_GOLD_HOVER};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
            border: none;
            background: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {GAIA_GOLD};
            border-radius: 5px;
            min-width: 24px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {GAIA_GOLD_HOVER};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
            border: none;
            background: none;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}
        QMenu {{
            background-color: {SURFACE_COLOR};
            border: 1px solid {BORDA_SUTIL};
            border-radius: 8px;
            padding: 4px;
            color: {TEXT_COLOR};
        }}
        QMenu::item {{
            padding: 6px 24px 6px 12px;
            border-radius: 6px;
            color: {TEXT_COLOR};
        }}
        QMenu::item:selected {{
            background-color: {HIGHLIGHT_COLOR};
            color: {GAIA_GOLD};
        }}
        QMenu::item:disabled {{
            color: {TEXT_DIM};
        }}
        QMenu::separator {{
            height: 1px;
            background: {BORDA_SUTIL};
            margin: 4px 8px;
        }}
    """)
