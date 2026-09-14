# -*- coding: utf-8 -*-
"""`Bubble`/`IndicadorVoz` (Project LOKI, Conversation Overlay, 2026-09-06,
polimento visual 2026-09-06) - renderiza UMA mensagem ou UM indicador de
voz. Pintado à mão (`QPainter`, fundo/borda/glow arredondados) - mesma
TÉCNICA de pintura de `menu_sao.py::_CirculoMenu`/`halo.py`, nunca QSS de
widget nativo. Diferente de `_CirculoMenu` (filho de UMA janela dona,
`MenuSAO`) - cada `Bubble`/`IndicadorVoz` é sua PRÓPRIA janela top-level
(mesmo padrão de `CompanionPanel`/`MenuSAO`: Tool/frameless/sempre no
topo, `move(x, y)` em coordenadas absolutas de tela), porque `BubbleStack`
precisa reposicionar cada bubble de forma independente conforme a pilha
cresce/encolhe - um widget FILHO só se moveria relativo ao container.

**Retrato/avatar FORA do balão (2026-09-07, pedido do usuário com
referência visual: "queria que ficasse assim")** - revisão da 1ª versão
do retrato (que ficava INLINE, num cabeçalho dentro do próprio balão).
`_desenhar_avatar` desenha um círculo de `TAMANHO_AVATAR` ao LADO do
balão (esquerda pra GAIA/erro, direita pro usuário, nunca dentro dele) -
`_area_bubble`/`_x_bubble` guardam o retângulo do balão em si, deslocado
pra abrir espaço pro avatar; `LARGURA_AVATAR_AREA` é a reserva (avatar +
respiro) que some da largura disponível pro TEXTO. A GAIA usa o retrato
real (`assets/avatar_galateia_chat.png`, já vem com o anel dourado/azul
pintado no próprio arquivo); cai pro glifo `✦` dourado se o arquivo não
existir (nunca quebra por causa de um asset ausente). **Novo nesta
revisão**: o usuário TAMBÉM ganhou avatar (a referência mostra os dois
lados com retrato) - um ícone genérico desenhado à mão (círculo cristal +
silhueta simples), já que não existe nenhuma foto própria configurada
pra ele. `erro` continua só com o glifo (aviso do sistema, não "ela"
respondendo de verdade). Um brilho `✦` decorativo pequeno acompanha
qualquer avatar (mesmo toque visual da referência).

**Largura por CONTEÚDO** (polimento 2026-09-06, pedido do usuário:
"atualmente 'Olá' ocupa praticamente a mesma largura de uma resposta
grande") - `LARGURA_PADRAO` é o TETO/envelope (nunca a largura FIXA de
todo bubble); cada bubble mede o próprio texto e usa `clamp(natural,
LARGURA_MINIMA, LARGURA_PADRAO - reserva_do_avatar)`. `alinhamento`
("esquerda"/"direita"/"centro", por `remetente`) deixa `BubbleStack`
posicionar cada um dentro do MESMO envelope de largura, sem recalcular
region/monitor/DPI - só desloca dentro da coluna já decidida por
`positioning.escolher_layout_conversa`; a LARGURA TOTAL do widget
(balão + avatar) nunca ultrapassa `LARGURA_PADRAO`, preservando o
invariante que `bubble_stack.py`/`positioning.py` dependem (nenhum item
sai do envelope) - `positioning.py` continua INTOCADO. **Teto 380->450
(2026-09-07)** - os 380px de antes (aumentados no MESMO dia por causa de
uma frase que quebrava sem necessidade) viraram só o orçamento de TEXTO;
os +70px novos são exatamente `LARGURA_AVATAR_AREA`, pra o avatar não
"roubar" de volta o espaço que tinha acabado de ser conquistado."""
from __future__ import annotations

import math
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from mascot.conversation_overlay import estilo

LARGURA_MINIMA = 90  # doc: "width = clamp(content_width + padding, MIN_BUBBLE_WIDTH, MAX_BUBBLE_WIDTH)" - só o balão, nunca inclui o avatar
TAMANHO_AVATAR = 60  # diâmetro do retrato/ícone FORA do balão (era 26, inline - 2026-09-07 moveu pra fora e aumentou, referência visual do usuário)
GAP_AVATAR_BUBBLE = 10  # respiro entre o avatar e a borda do balão
LARGURA_AVATAR_AREA = TAMANHO_AVATAR + GAP_AVATAR_BUBBLE  # reserva total (avatar + respiro) descontada do orçamento de texto
LARGURA_PADRAO = 380 + LARGURA_AVATAR_AREA  # TETO (doc: MAX_BUBBLE_WIDTH) do widget INTEIRO (balão + avatar) - 380 é o orçamento de texto (era o teto antigo, 2026-09-06), + LARGURA_AVATAR_AREA pra o avatar não tomar espaço que já tinha sido aumentado por causa do wrap desnecessário
ALTURA_MAXIMA_TEXTO = 200  # doc: "não deixar o bubble ocupar metade da tela" - além disso, trunca + "Ver completo"
ALTURA_MINIMA_BUBBLE = 40  # nunca menor que isto, mesmo pra "Olá" - dá espaço pro rodapé respirar
PADDING_H = 16  # doc, polimento: "padding horizontal: 14 a 18px"
PADDING_V = 11  # doc, polimento: "padding vertical: 9 a 12px"
ALTURA_RODAPE = 20  # linha única pro timestamp (sempre) + "Ver completo ›" (só quando truncado) - MESMA reserva, nunca condicional
ALTURA_MAXIMA_MINIATURA = 160  # teto da miniatura de uma imagem anexada (2026-09-07, Ctrl+V/anexo) - nunca deixa o bubble virar uma imagem em tela cheia
LARGURA_MINIMA_MINIATURA = 200  # largura mínima de uma miniatura SEM legenda (texto vazio) - senão ela ficaria do tamanho de um ícone perdido
GAP_MINIATURA_TEXTO = 8  # respiro entre a miniatura e o texto (só quando os dois existem no mesmo bubble)
_CAMINHO_AVATAR = Path(__file__).resolve().parents[2] / "assets" / "avatar_galateia_chat.png"
DURACAO_ANIM_MS = 220  # doc, seção 12: "algo na faixa de 150 a 300ms já deve bastar"
PASSO_MS = 16
DESLOCAMENTO_ENTRADA_PX = 10  # doc: "bubble entrando: fade + leve deslocamento"


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


_avatar_cache: QPixmap | None = None  # carregado/escalado UMA vez (o arquivo original tem 1254x1254px, ~2MB - recarregar por bubble seria desperdício)


def _avatar_pixmap() -> QPixmap | None:
    """`None` se o arquivo não existir/falhar ao carregar (usuário pode
    mover/apagar o PNG) - quem chama cai pro glifo `✦` nesse caso, nunca
    quebra por causa de um asset ausente."""
    global _avatar_cache
    if _avatar_cache is None:
        pix = QPixmap()
        if _CAMINHO_AVATAR.is_file():
            pix.load(str(_CAMINHO_AVATAR))
        _avatar_cache = (
            pix.scaled(
                TAMANHO_AVATAR, TAMANHO_AVATAR,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            )
            if not pix.isNull() else QPixmap()  # QPixmap() nula marca "já tentei, não existe" - não tenta de novo a cada bubble
        )
    return _avatar_cache if not _avatar_cache.isNull() else None


def _truncar_para_altura(fm: QFontMetrics, texto: str, largura_disponivel: int, altura_maxima: int) -> "tuple[str, bool]":
    """Corta o texto (busca binária pelo maior prefixo que cabe) até a
    altura RENDERIZADA (word wrap real, não contagem de linhas estimada)
    ficar dentro de `altura_maxima` - devolve `(texto_exibido, foi_cortado)`.
    Nunca corta no meio de sobrar espaço (doc: "mostrar uma versão
    resumida ou um trecho")."""
    caixa = QRect(0, 0, max(1, largura_disponivel), 100_000)
    if fm.boundingRect(caixa, Qt.TextFlag.TextWordWrap, texto).height() <= altura_maxima:
        return texto, False
    baixo, alto = 1, len(texto)
    melhor = texto[:1] + "…"
    while baixo <= alto:
        meio = (baixo + alto) // 2
        candidato = texto[:meio].rstrip() + "…"
        altura = fm.boundingRect(caixa, Qt.TextFlag.TextWordWrap, candidato).height()
        if altura <= altura_maxima:
            melhor = candidato
            baixo = meio + 1
        else:
            alto = meio - 1
    return melhor, True


class _BolhaBase(QWidget):
    """Pintura comum (fundo arredondado + borda + glow) - `Bubble`
    (mensagem) e `IndicadorVoz` (escutando/processando) só diferem no
    CONTEÚDO desenhado por cima, ver `_desenhar_conteudo`."""

    concluiu_saida = Signal(object)  # emite a si mesma - BubbleStack remove/deleta ao receber
    # Rodinha do mouse sobre o bubble (2026-09-07, modo histórico do
    # `BubbleStack` - "permitindo voltar com scroll") - delta bruto do Qt
    # (`QWheelEvent.angleDelta().y()`, tipicamente ±120 por "clique" da
    # rodinha); ignorado fora do modo histórico (`BubbleStack._ao_scroll_
    # historico` descarta se `_historico_ativo` for `False`).
    scroll_solicitado = Signal(int)

    def __init__(
        self, cor_fundo_hex: str, alpha_fundo: float, cor_borda_hex: str, alpha_borda: float,
        parent=None, raio: int = estilo.RAIO_BUBBLE, janela_topo: bool = True,
    ):
        super().__init__(parent)
        self._cor_fundo = QColor(cor_fundo_hex)
        self._cor_fundo.setAlphaF(alpha_fundo)
        self._cor_borda = QColor(cor_borda_hex)
        self._cor_borda.setAlphaF(alpha_borda)
        self._largura_borda = 1.0  # doc, polimento: "1px normal; 1 a 2px em focus/hover" - só `InputBar` varia isto (`redefinir_borda`)
        self._raio = raio
        self._area_bubble: QRect | None = None  # None = balão ocupa o widget INTEIRO (InputBar/IndicadorVoz); `Bubble` com avatar desloca isto pra abrir espaço fora do balão (ver `_rect_bubble`)
        # `janela_topo=False` (2026-09-07, `Bubble` embutido no histórico
        # completo do `CompanionPanel`, ver docstring do módulo) - widget
        # FILHO normal (layout do Qt decide a posição), nunca top-level
        # próprio. Por padrão (`True`, bubbles/composer FLUTUANTES do
        # Conversation Overlay) continua sendo uma janela TOP-LEVEL
        # própria (mesmo padrão de `CompanionPanel`/`MenuSAO` - Tool/
        # frameless/sempre no topo, SEM parent de verdade mesmo quando um
        # `parent` é passado) - necessário pra `move(x, y)` valer em
        # coordenadas ABSOLUTAS de tela (`positioning.py` já devolve
        # absolutas); um widget FILHO comum posicionaria relativo ao
        # container, não à tela.
        self._janela_topo = janela_topo
        if janela_topo:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
            )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if janela_topo:
            # 🔥 CORRIGIDO (2026-09-07, achado ao vivo: uma janela "Galateia"
            # apareceu em branco depois de reiniciar) - `aplicar_protecao_captura`
            # chama `widget.winId()`, forçando a criação IMEDIATA do HWND nativo.
            # Chamado aqui, bem no INÍCIO de `_BolhaBase.__init__` (antes de
            # `resize`/layout/conteúdo do subtipo real - `Bubble`/`InputBar`/
            # `IndicadorVoz`, que só rodam DEPOIS deste `super().__init__()`),
            # força esse HWND a existir sem geometria/conteúdo nenhum ainda -
            # mesma classe de bug de timing Qt/Windows do `raise_()` em
            # `entrar()` logo abaixo, que já precisou do mesmo adiamento.
            # `QTimer.singleShot(0, ...)` adia a chamada pro próximo tick do
            # event loop, depois que o construtor do subtipo real já terminou.
            # Nunca chamado quando embutido - não é uma janela de verdade
            # (sem HWND próprio), a proteção de captura do widget PAI já cobre.
            from mascot import config, platform_windows
            QTimer.singleShot(0, lambda: platform_windows.aplicar_protecao_captura(
                self, bool(config.carregar_config_mascot().get("proteger_de_captura")),
            ))

        self._opacidade = 1.0  # aplicada em `paintEvent` via `painter.setOpacity` - `setWindowOpacity` não tem efeito em janela SEM decoração/compositing próprio nesta versão do Qt (confirmado ao vivo), pintar é mais confiável
        # Opacidade de REPOUSO (doc, seção 7: "[resposta anterior] ← mais
        # transparente... antigas perdem destaque, fazem fade") - separada
        # da opacidade de ENTRADA/SAÍDA: um bubble que deixa de ser o mais
        # novo (empurrado pra cima por uma mensagem nova, `mover_para`
        # abaixo) esmaece pro seu novo valor de repouso, sem precisar
        # sair/reentrar.
        self._opacidade_repouso = 1.0
        self._opacidade_origem_realocacao = 1.0
        self._interpolar_opacidade_na_realocacao = False
        self._direcao = "entrando"
        self._tempo_inicio = 0.0
        self._y_alvo = 0
        self._y_origem_realocacao = 0
        self._deslocamento_atual = DESLOCAMENTO_ENTRADA_PX  # 0 quando `entrar(..., deslizar=False)` - ver docstring de `entrar`
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._passo)

        # 🔥 CORRIGIDO 2x (2026-09-06). 1ª tentativa: `outline`/frame do
        # Fusion (não era a causa). 2ª tentativa: alpha da cor do glow
        # (causa real do "retângulo" ao digitar, mas não da invisibilidade
        # dos bubbles). Causa real da INVISIBILIDADE (achado ao vivo, log
        # real confirmando bubble criado/posicionado certinho mas nunca
        # aparecendo, em QUALQUER monitor): `QGraphicsDropShadowEffect`
        # (`QGraphicsEffect`) combinado com janela TOP-LEVEL frameless
        # `WA_TranslucentBackground` é uma combinação conhecida por falhar
        # silenciosamente no compositor do Windows. Glow agora é pintado
        # À MÃO em `paintEvent` (`_desenhar_glow`) - MESMA técnica já
        # comprovada de `halo.py`, sem `QGraphicsEffect` nenhum.
        self._cor_glow = QColor(estilo.CRISTAL_GLOW)
        self._cor_glow.setAlphaF(0.5)
        self._intensidade_glow = 0.0  # 0 = sem glow; escala livre (era "blurRadius" do efeito antigo, mesmo significado de intensidade)

    def redefinir_borda(self, cor_hex: str, alpha: float, blur: float, largura_px: float = 1.0) -> None:
        """Permite um subtipo (`InputBar`) reagir a hover/foco - mesma
        pintura de `_desenhar_conteudo`, só muda cor/intensidade da borda,
        a intensidade do glow (`_desenhar_glow`) e a espessura do traço
        (doc, polimento: "1px normal; 1 a 2px em focus/hover"). `Bubble`/
        `IndicadorVoz` nunca chamam isto (borda fixa, definida uma vez no
        construtor)."""
        self._cor_borda = QColor(cor_hex)
        self._cor_borda.setAlphaF(alpha)
        self._intensidade_glow = blur
        self._largura_borda = largura_px
        self.update()

    def _rect_bubble(self) -> QRectF:
        """Retângulo do BALÃO em si (fundo/borda/glow) - todo o widget,
        a menos que `_area_bubble` tenha sido deslocado pra abrir espaço
        pro avatar (`Bubble`, ver docstring do módulo)."""
        return QRectF(self._area_bubble) if self._area_bubble is not None else QRectF(self.rect())

    def _desenhar_glow(self, painter: QPainter, caminho: QPainterPath) -> None:
        """Glow pintado à mão (nunca `QGraphicsEffect`, ver `__init__`) -
        um traço largo e translúcido por baixo do traço nítido da borda,
        concentrado perto dela (não "vaza" pra fora do widget - o widget
        não reserva margem extra pra isso, então um halo que se espalhasse
        pra fora seria cortado pelos próprios limites do widget)."""
        if self._intensidade_glow <= 0:
            return
        cor_halo = QColor(self._cor_glow)
        cor_halo.setAlphaF(self._cor_glow.alphaF() * min(1.0, self._intensidade_glow / 20.0))
        caneta = QPen(cor_halo, 3.0 + self._intensidade_glow * 0.35)
        painter.setPen(caneta)
        painter.drawPath(caminho)

    def entrar(self, x: int, y: int, opacidade_repouso: float = 1.0, deslizar: bool = True) -> None:
        """`deslizar=False` (polimento 2026-09-06) - pula o deslocamento
        de entrada, só faz fade "no lugar". Usado quando um `Bubble` novo
        está SUBSTITUINDO o indicador de voz ("✦ •••" -> resposta de
        verdade, doc: "sem destruir um widget e fazer outro aparecer
        abruptamente") - aproximação deliberada de "morph" (são objetos
        Qt DIFERENTES, não dá pra transformar um no outro de verdade sem
        unificar as classes) - a ausência do slide já entrega a sensação
        de "o conteúdo mudou no lugar", não "um elemento novo chegou"."""
        self._y_alvo = y
        self._deslocamento_atual = DESLOCAMENTO_ENTRADA_PX if deslizar else 0
        self.move(x, y + self._deslocamento_atual)
        self._opacidade = 0.0
        self._opacidade_repouso = opacidade_repouso
        self._direcao = "entrando"
        self._tempo_inicio = time.monotonic()
        self.show()
        # `raise_()` explícito (2026-09-06) - cada `Bubble`/`IndicadorVoz`/
        # `InputBar` é uma janela top-level PRÓPRIA sem parent (ver
        # docstring do módulo); `WindowStaysOnTopHint` sozinho não garante
        # posição RELATIVA entre várias janelas "sempre no topo"
        # concorrentes. Dobrado (imediato + adiado via `QTimer.singleShot`)
        # por um achado conhecido do Qt/Windows: `raise_()` no MESMO tick
        # de `show()` pode ser um no-op se o HWND nativo ainda não foi
        # mapeado de verdade.
        self.raise_()
        QTimer.singleShot(0, self.raise_)
        self._timer.start(PASSO_MS)

    def sair(self) -> None:
        self._y_alvo = self.y()
        self._direcao = "saindo"
        self._tempo_inicio = time.monotonic()
        self._timer.start(PASSO_MS)

    def mover_para(self, y_novo: int, opacidade_repouso: float | None = None) -> None:
        """Reposiciona um bubble JÁ visível (ex.: um mais antigo empurrado
        pra cima por uma mensagem nova) - desliza suave. `opacidade_
        repouso` (doc, seção 7: mensagens antigas "perdem destaque, fazem
        fade") esmaece JUNTO com o deslocamento, na MESMA duração - `None`
        (padrão) não mexe na opacidade atual."""
        if self.y() == y_novo and opacidade_repouso is None:
            return
        self._y_origem_realocacao = self.y()
        self._y_alvo = y_novo
        self._opacidade_origem_realocacao = self._opacidade
        self._interpolar_opacidade_na_realocacao = opacidade_repouso is not None
        if opacidade_repouso is not None:
            self._opacidade_repouso = opacidade_repouso
        self._direcao = "realocando"
        self._tempo_inicio = time.monotonic()
        self._timer.start(PASSO_MS)

    def _passo(self) -> None:
        # 🔥 CORRIGIDO (2026-09-07, achado ao vivo pelo usuário - print real
        # mostrando bubbles "duplicados", uma cópia fantasma logo atrás da
        # de verdade) - confirmado por script que NÃO existe bubble/dado
        # duplicado nenhum (`BubbleStack._bubbles`/`_historico_dados` só
        # têm 1 entrada por mensagem, sempre) - é um artefato de
        # COMPOSITING do Windows, mesma família dos outros 3 achados desta
        # sessão sobre janela top-level frameless translúcida sempre-no-
        # topo (`QGraphicsDropShadowEffect` invisível, `winId()` prematuro
        # travando em branco, `raise_()` de z-order) - aqui, mover E
        # esmaecer o widget no MESMO frame via `update()` (agendado, pode
        # atrasar/empilhar) deixava o DWM compor um frame ANTIGO por cima
        # do novo por um instante. `repaint()` (síncrono, nunca adiado) +
        # `raise_()` a cada frame (mesma razão do `entrar()` abaixo -
        # várias janelas "sempre no topo" concorrentes podem perder a
        # ordem entre si, não só ao aparecer) resolvem isso.
        decorrido_ms = (time.monotonic() - self._tempo_inicio) * 1000
        t = _ease_out(decorrido_ms / DURACAO_ANIM_MS)
        if self._direcao == "entrando":
            self.move(self.x(), int(self._y_alvo + self._deslocamento_atual * (1.0 - t)))
            self._opacidade = t * self._opacidade_repouso
            self.raise_()
            self.repaint()
            if t >= 1.0:
                self._timer.stop()
        elif self._direcao == "saindo":
            self.move(self.x(), int(self._y_alvo - DESLOCAMENTO_ENTRADA_PX * t))
            self._opacidade = self._opacidade_repouso * (1.0 - t)
            self.repaint()
            if t >= 1.0:
                self._timer.stop()
                self.hide()
                self.concluiu_saida.emit(self)
        else:  # realocando
            y_atual = int(self._y_origem_realocacao + (self._y_alvo - self._y_origem_realocacao) * t)
            self.move(self.x(), y_atual)
            if self._interpolar_opacidade_na_realocacao:
                self._opacidade = self._opacidade_origem_realocacao + (self._opacidade_repouso - self._opacidade_origem_realocacao) * t
            self.raise_()
            self.repaint()
            if t >= 1.0:
                self._timer.stop()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(self._opacidade)
        caminho = QPainterPath()
        caminho.addRoundedRect(self._rect_bubble().adjusted(1, 1, -1, -1), self._raio, self._raio)
        painter.fillPath(caminho, self._cor_fundo)
        self._desenhar_glow(painter, caminho)
        painter.setPen(QPen(self._cor_borda, self._largura_borda))
        painter.drawPath(caminho)
        self._desenhar_conteudo(painter)

    def _desenhar_conteudo(self, painter: QPainter) -> None:
        raise NotImplementedError

    def wheelEvent(self, event) -> None:  # noqa: N802 - nome exigido pelo Qt
        self.scroll_solicitado.emit(event.angleDelta().y())
        event.accept()


class Bubble(_BolhaBase):
    """Uma mensagem (GAIA, usuário, erro local ou sistema). `remetente`:
    `"gaia"` / `"usuario"` / `"erro"` / `"sistema"` - decide cor/avatar/
    alinhamento:

    - `"usuario"`: fundo azul-marinho mais claro, borda CRISTAL, alinhado
      à DIREITA da coluna, avatar (ícone genérico) do lado de FORA à
      direita do balão.
    - `"gaia"`/`"erro"`: fundo navy quase preto, borda CRISTAL (2026-09-07,
      ver docstring do módulo - reversão da borda NEUTRA de antes),
      alinhado à ESQUERDA, avatar (retrato real pra `"gaia"`, glifo `✦`
      pra `"erro"`) do lado de FORA à esquerda do balão.
    - `"sistema"`: neutro, centralizado, sem avatar.

    Largura por CONTEÚDO (`clamp(natural, LARGURA_MINIMA, LARGURA_PADRAO -
    reserva_do_avatar)`, ver docstring do módulo) - altura cresce até
    `ALTURA_MAXIMA_TEXTO`, além disso trunca e mostra "Ver completo ›"
    (`expandir_solicitado`). Timestamp discreto sempre no rodapé
    (`ALTURA_RODAPE`)."""

    expandir_solicitado = Signal()

    _CORES = {
        "gaia": (estilo.FUNDO_1, 0.90, estilo.CRISTAL, 0.55),
        "usuario": ("#12283D", 0.92, estilo.CRISTAL, 0.55),
        "erro": (estilo.FUNDO_1, 0.90, estilo.ERRO, 0.55),
        "sistema": (estilo.FUNDO_2, 0.85, estilo.TEXTO_SECUNDARIO, 0.30),
    }
    _REMETENTES_COM_AVATAR = ("gaia", "usuario", "erro")
    _ALINHAMENTO = {"usuario": "direita", "gaia": "esquerda", "erro": "esquerda", "sistema": "centro"}
    _INTENSIDADE_GLOW_MENSAGEM = 12.0  # doc: referência visual mostra as duas bordas com brilho ciano vívido - `IndicadorVoz`/`InputBar` continuam com seu próprio valor (0 por padrão, variável por hover/foco)

    def __init__(
        self, remetente: str, texto: str, parent=None, imagem: QPixmap | None = None,
        embutido: bool = False, largura_maxima: int | None = None, sem_truncamento: bool = False,
    ):
        """`embutido`/`largura_maxima`/`sem_truncamento` (2026-09-07) -
        parâmetros INDEPENDENTES, cada um com seu próprio motivo:

        - `embutido=True`: bubble nasce como widget FILHO normal
          (`janela_topo=False`, ver `_BolhaBase`) em vez de janela
          top-level própria - usado quando um widget PAI de verdade
          (`QScrollArea`/layout) já vai posicionar este bubble; não
          combina com `entrar`/`sair`/`mover_para` (animação de janela
          flutuante), quem usa isto só chama `.show()` normal.
        - `largura_maxima`: teto de largura PRÓPRIO no lugar de
          `LARGURA_PADRAO` (pensado pro envelope do Conversation Overlay,
          não serve pra toda superfície que queira embutir um bubble).
        - `sem_truncamento=True`: nunca corta o texto nem mostra "Ver
          completo ›", mesmo sendo uma janela top-level normal (modo
          histórico do `BubbleStack` - "permitindo voltar com scroll" - os
          bubbles ali continuam FLUTUANTES, só que sem o limite de altura
          de texto que a pilha normal tem). `embutido=True` TAMBÉM
          desativa o truncamento (o destino de "Ver completo" nunca
          precisaria truncar de novo), então o truncamento real é
          `not (embutido or sem_truncamento)`."""
        cor_fundo, alpha_fundo, cor_borda, alpha_borda = self._CORES.get(remetente, self._CORES["sistema"])
        super().__init__(cor_fundo, alpha_fundo, cor_borda, alpha_borda, parent, janela_topo=not embutido)
        self.remetente = remetente
        self.texto_completo = texto
        self.alinhamento = self._ALINHAMENTO.get(remetente, "centro")
        self._tem_avatar = remetente in self._REMETENTES_COM_AVATAR
        if self._tem_avatar:
            # Glow derivado da PRÓPRIA cor da borda (nunca mais um azul
            # fixo hardcoded) - `"erro"` ganha um halo vermelho coerente
            # com a borda dele de graça, sem precisar de um caso especial.
            self._cor_glow = QColor(cor_borda)
            self._cor_glow.setAlphaF(0.5)
            self._intensidade_glow = self._INTENSIDADE_GLOW_MENSAGEM
        self._hora_criacao = time.strftime("%H:%M")

        self._fonte = QFont(self.font())
        self._fonte.setPointSizeF(10.0)
        self._fonte_avatar_fallback = QFont(self.font())
        self._fonte_avatar_fallback.setPointSizeF(20.0)  # glifo `✦` centralizado dentro do círculo do avatar (fallback sem retrato/foto)
        self._fonte_sparkle = QFont(self.font())
        self._fonte_sparkle.setPointSizeF(11.0)
        self._fonte_hora = QFont(self.font())
        self._fonte_hora.setPointSizeF(7.5)
        fm = QFontMetrics(self._fonte)

        # Largura por CONTEÚDO (doc: "width = clamp(content_width +
        # padding, MIN, MAX)") - mede o texto NATURAL (1 linha) primeiro;
        # só usa o teto quando o texto realmente precisa de mais espaço
        # que isso, e nesse caso o word-wrap cuida do resto. O orçamento
        # de texto já desconta a reserva do avatar (se houver) - o widget
        # INTEIRO (balão + avatar) nunca ultrapassa `LARGURA_PADRAO`.
        largura_avatar_reservada = LARGURA_AVATAR_AREA if self._tem_avatar else 0
        largura_teto = largura_maxima if largura_maxima is not None else LARGURA_PADRAO
        largura_texto_maxima = largura_teto - largura_avatar_reservada - 2 * PADDING_H
        largura_desejada = fm.horizontalAdvance(texto) if texto else 0
        if imagem is not None and not imagem.isNull():
            # Uma miniatura sem legenda nenhuma ainda precisa de uma
            # largura razoável (não o quase-zero de um texto vazio) pra
            # parecer uma miniatura de verdade, não um ícone perdido.
            largura_desejada = max(largura_desejada, min(LARGURA_MINIMA_MINIATURA, largura_texto_maxima))
        largura_texto_final = max(1, min(largura_desejada, largura_texto_maxima))
        largura_bubble = max(LARGURA_MINIMA, largura_texto_final + 2 * PADDING_H)
        largura_texto_final = largura_bubble - 2 * PADDING_H  # reajusta caso o clamp por LARGURA_MINIMA tenha sobrado espaço

        # Sem truncamento quando embutido OU explicitamente pedido
        # (2026-09-07) - ver docstring do construtor.
        altura_maxima_texto_efetiva = float("inf") if (embutido or sem_truncamento) else ALTURA_MAXIMA_TEXTO
        self.texto_exibido, self._truncado = _truncar_para_altura(
            fm, texto, largura_texto_final, altura_maxima_texto_efetiva,
        )
        altura_texto = fm.boundingRect(
            QRect(0, 0, largura_texto_final, 100_000), Qt.TextFlag.TextWordWrap, self.texto_exibido,
        ).height() if texto else 0

        # Miniatura de imagem anexada (2026-09-07, Ctrl+V/anexo no
        # composer) - escalada pra caber na largura do TEXTO (mesmo
        # envelope, nunca estoura o balão pros lados) com um teto de
        # altura (`ALTURA_MAXIMA_MINIATURA`, nunca vira tela cheia).
        self._miniatura = None
        altura_miniatura = 0
        if imagem is not None and not imagem.isNull():
            self._miniatura = imagem.scaled(
                largura_texto_final, ALTURA_MAXIMA_MINIATURA,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            )
            altura_miniatura = self._miniatura.height()

        altura_conteudo = altura_miniatura + (GAP_MINIATURA_TEXTO + altura_texto if self._miniatura is not None and texto else altura_texto)
        altura_bubble = max(
            ALTURA_MINIMA_BUBBLE,
            altura_conteudo + 2 * PADDING_V + ALTURA_RODAPE,
            TAMANHO_AVATAR if self._tem_avatar else 0,  # o balão nunca fica mais baixo que o próprio avatar
        )
        # avatar à ESQUERDA do balão (gaia/erro) empurra o balão pra
        # direita dentro do widget; à DIREITA (usuário) o balão fica em
        # x=0 e o avatar ocupa a sobra à direita - ver `_desenhar_avatar`.
        x_bubble = largura_avatar_reservada if self.alinhamento == "esquerda" else 0
        self.resize(largura_bubble + largura_avatar_reservada, altura_bubble)
        self._area_bubble = QRect(x_bubble, 0, largura_bubble, altura_bubble)
        self._x_bubble = x_bubble
        self._largura_bubble = largura_bubble
        self._largura_texto = largura_texto_final
        self._altura_miniatura = altura_miniatura

    def sizeHint(self):  # noqa: N802 - nome exigido pelo Qt
        return self.size()

    def mousePressEvent(self, event) -> None:
        if self._truncado and event.button() == Qt.MouseButton.LeftButton:
            retangulo_acao = QRectF(self._x_bubble, self.height() - ALTURA_RODAPE, self._largura_bubble, ALTURA_RODAPE)
            if retangulo_acao.contains(event.position()):
                self.expandir_solicitado.emit()
                event.accept()
                return
        super().mousePressEvent(event)

    def _desenhar_conteudo(self, painter: QPainter) -> None:
        if self._tem_avatar:
            self._desenhar_avatar(painter)

        y_conteudo = PADDING_V
        if self._miniatura is not None:
            painter.drawPixmap(QRectF(self._x_bubble + PADDING_H, y_conteudo, self._miniatura.width(), self._miniatura.height()), self._miniatura, QRectF(self._miniatura.rect()))
            y_conteudo += self._altura_miniatura + (GAP_MINIATURA_TEXTO if self.texto_exibido else 0)

        if self.texto_exibido:
            painter.setFont(self._fonte)
            if self.remetente == "sistema":
                cor_texto = estilo.TEXTO_SECUNDARIO
            elif self.remetente == "erro":
                cor_texto = estilo.ERRO
            else:
                cor_texto = estilo.TEXTO_PRINCIPAL
            painter.setPen(QColor(cor_texto))
            retangulo_texto = QRectF(
                self._x_bubble + PADDING_H, y_conteudo,
                self._largura_texto, self.height() - y_conteudo - ALTURA_RODAPE,
            )
            painter.drawText(retangulo_texto, Qt.TextFlag.TextWordWrap, self.texto_exibido)

        y_rodape = self.height() - ALTURA_RODAPE
        if self._truncado:
            painter.setPen(QColor(estilo.CRISTAL))
            painter.drawText(
                QRectF(self._x_bubble + PADDING_H, y_rodape, self._largura_bubble - 2 * PADDING_H - 50, ALTURA_RODAPE),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Ver completo ›",
            )
        cor_hora = QColor(estilo.TEXTO_SECUNDARIO)
        cor_hora.setAlphaF(0.55)
        painter.setPen(cor_hora)
        painter.setFont(self._fonte_hora)
        painter.drawText(
            QRectF(self._x_bubble + PADDING_H, y_rodape, self._largura_bubble - 2 * PADDING_H, ALTURA_RODAPE),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, self._hora_criacao,
        )

    def _desenhar_avatar(self, painter: QPainter) -> None:
        """Retrato/ícone FORA do balão (2026-09-07, referência visual do
        usuário: "queria que ficasse assim"). GAIA usa o retrato real
        (já vem com o anel dourado/azul pintado no próprio arquivo);
        usuário ganha um ícone genérico desenhado à mão (nenhuma foto
        própria configurada pra ele); `"erro"` cai pro mesmo glifo `✦` de
        sempre, agora dentro de um círculo em vez de inline. Cai pro
        glifo também se o retrato da GAIA não existir/falhar ao carregar
        (`_avatar_pixmap` devolve `None` nesse caso) - nunca quebra por
        causa de um asset ausente."""
        x_avatar = 0.0 if self.alinhamento == "esquerda" else self._x_bubble + self._largura_bubble + GAP_AVATAR_BUBBLE
        y_avatar = (self.height() - TAMANHO_AVATAR) / 2
        rect_avatar = QRectF(x_avatar, y_avatar, TAMANHO_AVATAR, TAMANHO_AVATAR)

        retrato = _avatar_pixmap() if self.remetente == "gaia" else None
        if retrato is not None:
            painter.drawPixmap(rect_avatar, retrato, QRectF(retrato.rect()))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(estilo.CRISTAL if self.remetente == "usuario" else estilo.FUNDO_3))
            painter.drawEllipse(rect_avatar)
            if self.remetente == "usuario":
                self._desenhar_silhueta_pessoa(painter, rect_avatar)
            else:
                painter.setFont(self._fonte_avatar_fallback)
                painter.setPen(QColor(estilo.DOURADO))
                painter.drawText(rect_avatar, Qt.AlignmentFlag.AlignCenter, "✦")

        self._desenhar_sparkle_avatar(painter, rect_avatar)

    def _desenhar_silhueta_pessoa(self, painter: QPainter, rect_avatar: QRectF) -> None:
        """Ícone genérico do usuário (nenhum asset/foto própria configurada
        - cabeça + ombros simples, recortados pelo círculo do próprio
        avatar via `setClipPath`, mesma silhueta comum de app de chat)."""
        painter.save()
        caminho_clip = QPainterPath()
        caminho_clip.addEllipse(rect_avatar)
        painter.setClipPath(caminho_clip)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(estilo.FUNDO_1))
        raio = rect_avatar.width() / 2
        cx = rect_avatar.center().x()
        raio_cabeca = raio * 0.34
        y_cabeca = rect_avatar.top() + raio * 0.62
        painter.drawEllipse(QPointF(cx, y_cabeca), raio_cabeca, raio_cabeca)
        corpo = QRectF(cx - raio * 0.62, y_cabeca + raio_cabeca * 0.5, raio * 1.24, raio * 1.3)
        painter.drawEllipse(corpo)
        painter.restore()

    def _desenhar_sparkle_avatar(self, painter: QPainter, rect_avatar: QRectF) -> None:
        """Brilho `✦` decorativo perto do avatar (mesmo toque visual da
        referência) - dourado pra GAIA/erro (identidade antiga da
        assinatura), cristal pro usuário."""
        cor = QColor(estilo.DOURADO if self.remetente in ("gaia", "erro") else estilo.CRISTAL)
        painter.setFont(self._fonte_sparkle)
        painter.setPen(cor)
        tamanho = TAMANHO_AVATAR * 0.4
        painter.drawText(
            QRectF(rect_avatar.right() - TAMANHO_AVATAR * 0.18, rect_avatar.top() - TAMANHO_AVATAR * 0.05, tamanho, tamanho),
            Qt.AlignmentFlag.AlignCenter, "✦",
        )


ALTURA_INDICADOR = 40
_LARGURA_ANIMACAO_INDICADOR = 40  # reserva à direita pra waveform/reticências
_LARGURA_MINIMA_INDICADOR = 70
DURACAO_ONDA_MS = 900  # 1 ciclo completo da waveform discreta (doc, seção 8: "pode ter uma waveform discreta")


class IndicadorVoz(_BolhaBase):
    """Pequeno bubble/indicador de voz (doc, seção 8) - `tipo`: `"ouvindo"`
    (`🎙 Te ouvindo...` + waveform discreta) ou `"processando"` (`✦` +
    reticências pulsando, polimento 2026-09-06: "prefiro três pontos
    animados a manter um texto grande como 'Pensando...'"). NUNCA vira
    janela - mesmo widget pintado à mão dos bubbles normais, só mais
    compacto e sem truncamento/"Ver completo" (texto sempre curto e
    fixo). Largura por CONTEÚDO como `Bubble` (mede o texto de cada tipo,
    já que "🎙 Te ouvindo..." precisa de bem mais espaço que só "✦")."""

    TEXTOS = {"ouvindo": "🎙 Te ouvindo...", "processando": "✦"}

    def __init__(self, tipo: str, parent=None):
        super().__init__(estilo.FUNDO_1, 0.90, estilo.CRISTAL, 0.6, parent)
        self.tipo = tipo
        self.alinhamento = "centro"
        self._fonte = QFont(self.font())
        self._fonte.setPointSizeF(10.0)
        fm = QFontMetrics(self._fonte)
        texto = self.TEXTOS.get(tipo, "")
        largura = PADDING_H + fm.horizontalAdvance(texto) + 6 + _LARGURA_ANIMACAO_INDICADOR + PADDING_H // 2
        self.resize(max(_LARGURA_MINIMA_INDICADOR, largura), ALTURA_INDICADOR)
        self._fase_onda = 0.0
        self._timer_onda = QTimer(self)
        self._timer_onda.timeout.connect(self._avancar_onda)
        self._timer_onda.start(PASSO_MS)

    def _avancar_onda(self) -> None:
        self._fase_onda = (self._fase_onda + PASSO_MS / DURACAO_ONDA_MS) % 1.0
        self.update()

    def _desenhar_conteudo(self, painter: QPainter) -> None:
        painter.setFont(self._fonte)
        painter.setPen(QColor(estilo.TEXTO_PRINCIPAL))
        texto = self.TEXTOS.get(self.tipo, "")
        painter.drawText(
            QRectF(PADDING_H, 0, self.width() - PADDING_H - _LARGURA_ANIMACAO_INDICADOR, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, texto,
        )
        if self.tipo == "ouvindo":
            self._desenhar_waveform(painter)
        else:
            self._desenhar_reticencias_pulsando(painter)

    def _desenhar_waveform(self, painter: QPainter) -> None:
        """3 barrinhas simples oscilando fora de fase - "discreta" de
        propósito (doc), sem depender de nível de áudio real (não há
        canal pra isso vindo da GAIA hoje, ver `docs/TODO.md`)."""
        base_x = self.width() - _LARGURA_ANIMACAO_INDICADOR + 6
        centro_y = self.height() / 2
        caneta = QPen(QColor(estilo.CRISTAL), 3)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(caneta)
        for i in range(3):
            fase = (self._fase_onda + i * 0.33) % 1.0
            altura_barra = 4 + 10 * abs(math.sin(fase * math.pi))
            x = base_x + i * 8
            painter.drawLine(int(x), int(centro_y - altura_barra / 2), int(x), int(centro_y + altura_barra / 2))

    def _desenhar_reticencias_pulsando(self, painter: QPainter) -> None:
        pontos_visiveis = 1 + int(self._fase_onda * 3) % 3
        painter.setPen(QColor(estilo.DOURADO))
        painter.drawText(
            QRectF(self.width() - _LARGURA_ANIMACAO_INDICADOR + 4, 0, _LARGURA_ANIMACAO_INDICADOR - 8, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "•" * pontos_visiveis,
        )
