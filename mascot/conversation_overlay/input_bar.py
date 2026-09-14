# -*- coding: utf-8 -*-
"""`InputBar`/"Composer" (Project LOKI, Conversation Overlay, 2026-09-06) -
campo de texto compacto e flutuante próximo da GAIA (doc, seção 2). Herda
o fundo/borda/glow/fade de `bubble._BolhaBase` (MESMA pintura dos
bubbles, identidade visual única) - só acrescenta widgets FILHOS por cima
do fundo pintado (herança normal do Qt já desenha os filhos depois do
`paintEvent` do pai, sem truque nenhum). Reage a hover/foco
(`_atualizar_borda`, correção 2026-09-06: "ainda parece um campo Qt
jogado na tela" - borda/glow eram ESTÁTICOS antes, sem nenhum estado) -
repouso quase sem destaque, glow leve só quando o campo tem foco de
verdade (doc: "glow leve quando estiver focado", nunca um brilho
permanente).

**Revisão 2026-09-07** (pedido do usuário com referência visual do
composer de um app de chat comum): três mudanças:

1. `LARGURA_PADRAO` passou a ser a MESMA largura de `bubble.LARGURA_PADRAO`
   ("aumenta o tamanho do campo de digitar mensagem p ficar do tamanho
   da fala da gaia") - fonte única, nunca mais um número solto igual mas
   duplicado.
2. O campo virou multi-linha (`QPlainTextEdit` em vez de `QLineEdit`) e
   CRESCE em altura conforme o texto quebra linha, até um teto de
   `ALTURA_MAXIMA_LINHAS` linhas (depois disso rola por dentro) - Enter
   envia, Shift+Enter quebra linha. O widget INTEIRO (janela top-level
   própria, ver docstring de `bubble.py`) cresce/encolhe junto
   (`_atualizar_geometria`), sempre mantendo o canto superior esquerdo
   FIXO (`QWidget.resize` cresce pra baixo/direita por padrão) - crescer
   pra BAIXO nunca invade o espaço já reservado pros bubbles (que ficam
   ACIMA do composer nos dois layouts possíveis, ver `positioning.py`),
   então nenhuma linha de `positioning.py`/`conversation_controller.py`
   precisou mudar pra isso funcionar - só o valor reservado
   (`ALTURA_MAXIMA`, pior caso) passou a ir pra `escolher_layout_conversa`
   no lugar da altura de repouso.
3. Ctrl+V com uma imagem na área de transferência (ou o botão 📎, arquivo
   local) anexa uma imagem - aparece como uma miniatura removível numa
   linha própria acima do campo (`_linha_anexo`). Ao enviar, a imagem é
   redimensionada/comprimida (JPEG, thumbnail 1024x1024, qualidade 70 -
   MESMO padrão de `capturar_tela_b64` no lado da GAIA) e viaja em
   `imagem_base64` (`core/mascot_events.py::evento_chat_submitted`) - o
   pipe Mascot<->GAIA tem um teto de tamanho de mensagem
   (`TAMANHO_MAXIMO_MENSAGEM_BYTES`, aumentado no mesmo dia pra caber
   isso), então a compressão acontece AQUI, antes de cruzar o pipe. O
   botão 😊 abre um seletor simples de emoji (grade fixa, sem biblioteca
   nova) que insere o glifo na posição do cursor.

`enviar_solicitado` mudou de `Signal(str)` pra `Signal(object)` (um dict
`{"texto", "imagem_preview", "imagem_base64", "imagem_mime"}`) pra
carregar a imagem sem multiplicar parâmetros posicionais por toda a
cadeia (`ConversationController`/`BubbleStack`/`CompanionPanel`).

`QPlainTextEdit` é o ÚNICO widget nativo do Qt aqui (era `QLineEdit`) -
inevitável pra teclado/IME de verdade; estilizado por QSS pra não ter
nenhum resquício de chrome padrão (sem borda quadrada, sem fundo cinza),
então não conta como "menu nativo do Qt" no sentido que o pedido original
quis evitar (QMenu/QDialog com moldura do sistema)."""
from __future__ import annotations

import base64

from PySide6.QtCore import QBuffer, QEvent, QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QImage, QKeySequence, QPalette, QPixmap
from PySide6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from mascot.conversation_overlay import bubble as bubble_module
from mascot.conversation_overlay import estilo
from mascot.conversation_overlay.bubble import _BolhaBase

LARGURA_PADRAO = bubble_module.LARGURA_PADRAO  # MESMA largura do bubble da GAIA (2026-09-07, pedido do usuário) - fonte única, nunca duplicado
ALTURA_PADRAO = 44  # altura de REPOUSO (1 linha vazia) - `ALTURA_MAXIMA` abaixo é o teto de crescimento
ALTURA_MAXIMA_LINHAS = 4  # depois disso o campo rola por dentro em vez de continuar crescendo pra sempre
ALTURA_LINHA_ANEXO = 52  # altura reservada pra linha de miniatura quando uma imagem está anexada
ALTURA_MAXIMA = 190  # pior caso (texto de 4 linhas + linha de anexo) - reservado de propósito em `escolher_layout_conversa` (ver docstring do módulo, item 2); número generoso, não precisa ser exato
PADDING_H = 16  # MESMO respiro horizontal de `Bubble` (`bubble.PADDING_H`) - identidade visual consistente
TAMANHO_MINIATURA_ANEXO = 36
LARGURA_MAXIMA_IMAGEM_ENVIO = 1024  # mesmo teto de `capturar_tela_b64` (lado GAIA) - imagem só precisa dar pra descrever, não pra ler pixel a pixel
QUALIDADE_JPEG_ENVIO = 70

# (alpha da borda, blur do glow, espessura do traço) por estado -
# progressão discreta (doc: "hover/focus discretos... glow leve quando
# estiver focado"), nunca um brilho permanente igual antes. Espessura
# (polimento 2026-09-06, doc: "1px normal; 1 a 2px em focus/hover").
_BORDA_REPOUSO = (0.35, 0.0, 1.0)
_BORDA_HOVER = (0.50, 6.0, 1.2)
_BORDA_FOCADO = (0.80, 16.0, 1.6)

# Estado LIGADO/DESLIGADO do botão de histórico (2026-09-07, pedido do
# usuário: "eu tenho q saber quando o botao de historico ta habilitado ou
# n") - antes o botão era sempre o mesmo `✦` dourado, sem nenhuma pista
# visual de que o modo histórico do `BubbleStack` estava ativo ou não.
_ESTILO_BOTAO_HISTORICO_INATIVO = f"""
    QPushButton {{ background: transparent; border: none; border-radius: 12px; color: {estilo.DOURADO}; font-size: 11pt; }}
    QPushButton:hover {{ background: {estilo.cor_fundo_translucido(estilo.DOURADO, 0.12)}; }}
"""
_ESTILO_BOTAO_HISTORICO_ATIVO = f"""
    QPushButton {{
        background: {estilo.cor_fundo_translucido(estilo.CRISTAL, 0.25)};
        border: 1px solid {estilo.CRISTAL}; border-radius: 12px; color: {estilo.CRISTAL}; font-size: 11pt;
    }}
    QPushButton:hover {{ background: {estilo.cor_fundo_translucido(estilo.CRISTAL, 0.35)}; }}
"""

_EMOJIS = [
    "😊", "😂", "🥲", "😍", "😘", "😉",
    "🤔", "😅", "😭", "😮", "😢", "😴",
    "🥺", "😴", "💀", "🔥", "✨", "🎉",
    "👍", "👀", "🙏", "🙌", "❤️", "💙",
    "🐾", "🎮", "🍕", "🌙", "⭐", "☕",
]


class InputBar(_BolhaBase):
    # `object` (nunca `str`) - carrega um dict com texto/imagem, ver
    # docstring do módulo. `_ao_enviar` monta o payload inteiro.
    enviar_solicitado = Signal(object)
    sair_solicitado = Signal()
    # Pedido do usuário (2026-09-06): "ainda falta uma forma de habilitar
    # p mostrar historico das mensagens q mandei e q ela respondeu" - o
    # "Ver completo" de um bubble só aparecia quando UMA mensagem estourava
    # o limite de altura (`bubble.py`), sem nenhum jeito de abrir o
    # histórico completo em qualquer outro momento. Botão próprio aqui,
    # sempre visível/alcançável (não depende de nenhum bubble específico).
    historico_solicitado = Signal()

    def __init__(self, parent=None):
        super().__init__(estilo.FUNDO_2, 0.92, estilo.CRISTAL, 0.6, parent, raio=estilo.RAIO_INPUT)
        self.resize(LARGURA_PADRAO, ALTURA_PADRAO)
        self._hover = False
        self._focado = False
        self._imagem_anexada: QImage | None = None
        self._atualizar_borda()  # começa em repouso - o construtor de `_BolhaBase` deixaria em estado "focado" por padrão

        # ---- linha de anexo (miniatura + remover) - escondida por padrão ----
        self._linha_anexo = QWidget(self)
        layout_anexo = QHBoxLayout(self._linha_anexo)
        layout_anexo.setContentsMargins(4, 4, 4, 0)
        layout_anexo.setSpacing(8)
        self._label_miniatura_anexo = QLabel(self._linha_anexo)
        self._label_miniatura_anexo.setFixedSize(TAMANHO_MINIATURA_ANEXO, TAMANHO_MINIATURA_ANEXO)
        self._label_miniatura_anexo.setScaledContents(True)
        self._label_rotulo_anexo = QLabel("Imagem anexada", self._linha_anexo)
        self._label_rotulo_anexo.setStyleSheet(f"color: {estilo.TEXTO_SECUNDARIO}; font-size: 9pt; background: transparent;")
        self._botao_remover_anexo = QPushButton("✕", self._linha_anexo)
        self._botao_remover_anexo.setFixedSize(20, 20)
        self._botao_remover_anexo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._botao_remover_anexo.setAutoDefault(False)
        self._botao_remover_anexo.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; border-radius: 10px; color: {estilo.TEXTO_SECUNDARIO}; font-size: 9pt; }}
            QPushButton:hover {{ background: {estilo.cor_fundo_translucido(estilo.ERRO, 0.18)}; color: {estilo.ERRO}; }}
        """)
        self._botao_remover_anexo.clicked.connect(self._remover_anexo)
        layout_anexo.addWidget(self._label_miniatura_anexo)
        layout_anexo.addWidget(self._label_rotulo_anexo)
        layout_anexo.addStretch(1)
        layout_anexo.addWidget(self._botao_remover_anexo)
        self._linha_anexo.setVisible(False)

        # ---- campo de texto (multi-linha, cresce com o conteúdo) ----
        self._campo = QPlainTextEdit(self)
        self._campo.setPlaceholderText("Digite uma mensagem...")
        self._campo.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        self._campo.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._campo.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._campo.setTabChangesFocus(True)
        self._campo.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        # 🔥 mesma causa/correção de 2026-09-06 (`outline: none`, ver
        # `_BolhaBase`/histórico do módulo) - o Fusion desenha um retângulo
        # de foco próprio via `outline`, não `border`.
        self._campo.setStyleSheet(
            f"QPlainTextEdit {{ background: transparent; border: none; outline: none; color: {estilo.TEXTO_PRINCIPAL}; "
            f"font-family: 'Segoe UI'; font-size: 10.5pt; }}"
            f"QPlainTextEdit:focus {{ background: transparent; border: none; outline: none; }}"
        )
        paleta = self._campo.palette()
        paleta.setColor(QPalette.ColorRole.PlaceholderText, QColor(estilo.TEXTO_SECUNDARIO))
        self._campo.setPalette(paleta)
        self._campo.textChanged.connect(self._atualizar_geometria)
        # Escape/Enter/Ctrl+V precisam de tratamento especial que o
        # `QPlainTextEdit` sozinho não dá (Enter insere quebra de linha por
        # padrão, sem sinal `returnPressed` como o `QLineEdit` tinha) -
        # filtro garante que tudo passa por `eventFilter` abaixo antes do
        # comportamento padrão do widget.
        self._campo.installEventFilter(self)

        self._botao_enviar = QPushButton("➤", self)
        self._botao_enviar.setFixedSize(28, 28)
        self._botao_enviar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._botao_enviar.setAutoDefault(False)
        self._botao_enviar.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: 14px;
                color: {estilo.CRISTAL}; font-size: 13pt;
            }}
            QPushButton:hover {{ background: {estilo.cor_fundo_translucido(estilo.CRISTAL, 0.16)}; }}
        """)
        self._botao_enviar.clicked.connect(self._ao_enviar)

        # "Histórico" - polimento 2026-09-06: dobra como assinatura visual
        # da GAIA (`✦`, MESMO glifo dourado dos bubbles dela) - resolve os
        # dois pedidos com um ÚNICO ícone (nunca uma barra de ferramentas
        # permanente), em vez de um ícone de relógio genérico separado.
        self._botao_historico = QPushButton("✦", self)
        self._botao_historico.setFixedSize(24, 24)
        self._botao_historico.setCursor(Qt.CursorShape.PointingHandCursor)
        self._botao_historico.setAutoDefault(False)
        self._botao_historico.clicked.connect(self.historico_solicitado.emit)
        self.definir_historico_ativo(False)  # estado inicial - também aplica o estilo/tooltip "inativo"

        # 📎 anexar imagem (2026-09-07) - MESMO resultado visual/fluxo de
        # colar com Ctrl+V, só que via seletor de arquivo (`_definir_anexo`
        # é o caminho ÚNICO pros dois, nunca duplicado).
        self._botao_anexo = QPushButton("📎", self)
        self._botao_anexo.setFixedSize(26, 26)
        self._botao_anexo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._botao_anexo.setAutoDefault(False)
        self._botao_anexo.setToolTip("Anexar imagem")
        self._botao_anexo.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; border-radius: 13px; color: {estilo.TEXTO_SECUNDARIO}; font-size: 11pt; }}
            QPushButton:hover {{ background: {estilo.cor_fundo_translucido(estilo.CRISTAL, 0.12)}; color: {estilo.CRISTAL}; }}
        """)
        self._botao_anexo.clicked.connect(self._anexar_imagem_de_arquivo)

        # 😊 emoji (2026-09-07) - grade fixa própria (sem biblioteca nova,
        # sem QMenu nativo - mesmo raciocínio de "nunca moldura do
        # sistema" do resto do composer).
        self._botao_emoji = QPushButton("😊", self)
        self._botao_emoji.setFixedSize(26, 26)
        self._botao_emoji.setCursor(Qt.CursorShape.PointingHandCursor)
        self._botao_emoji.setAutoDefault(False)
        self._botao_emoji.setToolTip("Inserir emoji")
        self._botao_emoji.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; border-radius: 13px; font-size: 11pt; }}
            QPushButton:hover {{ background: {estilo.cor_fundo_translucido(estilo.CRISTAL, 0.12)}; }}
        """)
        self._botao_emoji.clicked.connect(self._abrir_seletor_emoji)

        layout_externo = QVBoxLayout(self)
        layout_externo.setContentsMargins(PADDING_H // 2, 4, PADDING_H // 2, 4)
        layout_externo.setSpacing(4)
        layout_externo.addWidget(self._linha_anexo)

        linha_campo = QHBoxLayout()
        linha_campo.setSpacing(4)
        linha_campo.addWidget(self._botao_historico)
        linha_campo.addSpacing(4)
        linha_campo.addWidget(self._campo, stretch=1)
        linha_campo.addWidget(self._botao_anexo)
        linha_campo.addWidget(self._botao_emoji)
        linha_campo.addWidget(self._botao_enviar)
        layout_externo.addLayout(linha_campo)

        self._atualizar_geometria()

    def _desenhar_conteudo(self, painter) -> None:
        pass  # só o fundo/borda/glow de `_BolhaBase` - todo o resto é widget filho

    def _atualizar_borda(self) -> None:
        if self._focado:
            alpha, blur, largura = _BORDA_FOCADO
        elif self._hover:
            alpha, blur, largura = _BORDA_HOVER
        else:
            alpha, blur, largura = _BORDA_REPOUSO
        self.redefinir_borda(estilo.CRISTAL, alpha, blur, largura)

    def enterEvent(self, event) -> None:
        self._hover = True
        self._atualizar_borda()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self._atualizar_borda()

    def eventFilter(self, watched: QObject, event) -> bool:
        if watched is self._campo:
            tipo = event.type()
            if tipo == QEvent.Type.KeyPress:
                tecla = event.key()
                if tecla == Qt.Key.Key_Escape:
                    self.sair_solicitado.emit()
                    return True
                if tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self._ao_enviar()
                    return True
                if event.matches(QKeySequence.StandardKey.Paste) and self._colar_imagem_do_clipboard():
                    return True  # imagem colada com sucesso - nunca deixa o QPlainTextEdit tentar colar isso também
            elif tipo == QEvent.Type.FocusIn:
                self._focado = True
                self._atualizar_borda()
            elif tipo == QEvent.Type.FocusOut:
                self._focado = False
                self._atualizar_borda()
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------
    # Anexo de imagem (Ctrl+V ou botão 📎) - `_definir_anexo` é o caminho
    # ÚNICO que os dois usam, nunca duplicado.
    def _colar_imagem_do_clipboard(self) -> bool:
        dados = QGuiApplication.clipboard().mimeData()
        if dados is None or not dados.hasImage():
            return False
        imagem = QGuiApplication.clipboard().image()
        if imagem.isNull():
            return False
        self._definir_anexo(imagem)
        return True

    def _anexar_imagem_de_arquivo(self) -> None:
        caminho, _filtro = QFileDialog.getOpenFileName(
            self, "Anexar imagem", "", "Imagens (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not caminho:
            return
        imagem = QImage(caminho)
        if imagem.isNull():
            return
        self._definir_anexo(imagem)

    def _definir_anexo(self, imagem: QImage) -> None:
        self._imagem_anexada = imagem
        self._label_miniatura_anexo.setPixmap(QPixmap.fromImage(imagem))
        self._linha_anexo.setVisible(True)
        self._atualizar_geometria()

    def _remover_anexo(self) -> None:
        self._imagem_anexada = None
        self._label_miniatura_anexo.clear()
        self._linha_anexo.setVisible(False)
        self._atualizar_geometria()

    def _preparar_imagem_para_envio(self) -> "tuple[str, str] | None":
        """JPEG comprimido/redimensionado (mesmo padrão de
        `capturar_tela_b64` no lado da GAIA: thumbnail 1024x1024,
        qualidade 70) - o pipe Mascot<->GAIA tem um teto de tamanho de
        mensagem (`mascot_events.TAMANHO_MAXIMO_MENSAGEM_BYTES`), então a
        compressão acontece AQUI, antes de cruzar o pipe, nunca depois.
        `None` se não há imagem anexada."""
        if self._imagem_anexada is None:
            return None
        imagem = self._imagem_anexada
        if imagem.width() > LARGURA_MAXIMA_IMAGEM_ENVIO or imagem.height() > LARGURA_MAXIMA_IMAGEM_ENVIO:
            imagem = imagem.scaled(
                LARGURA_MAXIMA_IMAGEM_ENVIO, LARGURA_MAXIMA_IMAGEM_ENVIO,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            )
        buffer_saida = QBuffer()
        buffer_saida.open(QBuffer.OpenModeFlag.WriteOnly)
        imagem.save(buffer_saida, "JPEG", QUALIDADE_JPEG_ENVIO)
        dados_base64 = base64.b64encode(bytes(buffer_saida.data())).decode("ascii")
        return dados_base64, "image/jpeg"

    # ------------------------------------------------------------------
    # Emoji (grade fixa, popup que fecha sozinho ao perder o foco - MESMO
    # princípio de "nunca moldura nativa do sistema" do resto do composer)
    def _abrir_seletor_emoji(self) -> None:
        popup = QWidget(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        fundo = QColor(estilo.FUNDO_2)
        fundo.setAlphaF(0.98)
        popup.setStyleSheet(
            f"QWidget {{ background-color: {fundo.name(QColor.NameFormat.HexArgb)}; "
            f"border: 1px solid {estilo.CRISTAL}; border-radius: 10px; }}"
        )
        grade = QGridLayout(popup)
        grade.setContentsMargins(6, 6, 6, 6)
        grade.setSpacing(2)
        colunas = 6
        for indice, emoji in enumerate(_EMOJIS):
            botao = QPushButton(emoji, popup)
            botao.setFixedSize(30, 30)
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            botao.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none; border-radius: 6px; font-size: 12pt; }}
                QPushButton:hover {{ background: {estilo.cor_fundo_translucido(estilo.CRISTAL, 0.16)}; }}
            """)
            botao.clicked.connect(lambda _checked=False, e=emoji, p=popup: self._inserir_emoji(e, p))
            grade.addWidget(botao, indice // colunas, indice % colunas)
        popup.adjustSize()
        ponto = self._botao_emoji.mapToGlobal(QPoint(self._botao_emoji.width() - popup.width(), -popup.height() - 6))
        popup.move(ponto)
        popup.show()

    def _inserir_emoji(self, emoji: str, popup: QWidget) -> None:
        self._campo.insertPlainText(emoji)
        popup.close()
        self._campo.setFocus()

    # ------------------------------------------------------------------
    def _atualizar_geometria(self) -> None:
        """Cresce em altura conforme o texto quebra linha (até
        `ALTURA_MAXIMA_LINHAS`) - mede o texto NA LARGURA real do campo
        (mesma técnica de `bubble._truncar_para_altura`: `QFontMetrics.
        boundingRect` com `TextWordWrap`, em vez de mexer com o layout
        interno do `QTextDocument`), e deixa o `layout()` do próprio
        `InputBar` calcular a altura TOTAL certa (inclui a linha de anexo
        só quando visível, sem duplicar a lógica de margens/espaçamento
        aqui). O canto superior esquerdo nunca se move (`resize` cresce
        pra baixo/direita por padrão) - ver docstring do módulo, item 2."""
        fm = QFontMetrics(self._campo.font())
        linha_unica = fm.lineSpacing()
        largura_disponivel = max(1, self._campo.width() - 8)
        caixa = QRect(0, 0, largura_disponivel, 100_000)
        altura_texto = fm.boundingRect(caixa, Qt.TextFlag.TextWordWrap, self._campo.toPlainText() or " ").height()
        altura_campo = max(linha_unica, min(altura_texto, linha_unica * ALTURA_MAXIMA_LINHAS)) + 12
        self._campo.setFixedHeight(int(altura_campo))
        self.layout().activate()
        nova_altura = self.layout().sizeHint().height()
        if nova_altura != self.height():
            self.resize(self.width(), nova_altura)

    def _ao_enviar(self) -> None:
        texto = self._campo.toPlainText().strip()
        anexo = self._preparar_imagem_para_envio()
        if not texto and anexo is None:
            return
        imagem_preview = QPixmap.fromImage(self._imagem_anexada) if self._imagem_anexada is not None else None
        self._campo.clear()
        self._remover_anexo()
        self.enviar_solicitado.emit({
            "texto": texto,
            "imagem_preview": imagem_preview,
            "imagem_base64": anexo[0] if anexo else None,
            "imagem_mime": anexo[1] if anexo else None,
        })

    def focar(self) -> None:
        self._campo.setFocus()

    def definir_historico_ativo(self, ativo: bool) -> None:
        """`ConversationController` chama sempre que o modo histórico do
        `BubbleStack` muda (2026-09-07, pedido do usuário: "eu tenho q
        saber quando o botao de historico ta habilitado ou n") - troca o
        `✦` dourado discreto por um destaque cristal (fundo + borda) só
        enquanto o histórico estiver aberto, MESMA identidade cristal de
        "ativo/em foco" usada no resto do composer (`_atualizar_borda`)."""
        self._botao_historico.setStyleSheet(_ESTILO_BOTAO_HISTORICO_ATIVO if ativo else _ESTILO_BOTAO_HISTORICO_INATIVO)
        self._botao_historico.setToolTip("Fechar histórico completo" if ativo else "Ver histórico completo da conversa")
