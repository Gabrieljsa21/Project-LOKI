# -*- coding: utf-8 -*-
"""Menu SAO (Project LOKI, 2026-09-02) - menu de interação inspirado em
Sword Art Online, especificado em `C:\\Workspace\\GAIA_MENU_SAO.md`. Scroll
para baixo sobre a GAIA abre uma coluna vertical de 4 círculos (Conversar/
Voz/Ações/GAIA) ancorada no lado com mais espaço livre; scroll para cima
(sobre ela ou sobre o próprio menu) ou iniciar um arraste fecha. Mora no
MESMO subprocesso do Mascot (como `companion_panel.py`), nunca importa nada
do processo da GAIA - fala com ela só pelos mecanismos que já existem
(`conversation_overlay.ConversationController`/`companion_panel.
ciclar_modo_voz`).

Decisões de escopo desta 1ª versão (doc, "Primeira versão recomendada" +
conversa 2026-09-02 sobre as duas decisões que mudam comportamento global):

- clique simples na GAIA CONTINUA abrindo/fechando a conversa direto
  (`window.py::clicada`, não mexido aqui) - o menu é uma CAMADA adicional,
  não substitui o acesso rápido ao chat. "Conversar" aqui é redundante de
  propósito (chama o MESMO `ConversationController.alternar` - 2026-09-06:
  deixou de abrir o `CompanionPanel` grande direto, ver `conversation_
  overlay/conversation_controller.py` - o painel tradicional virou o
  destino do "Ver completo"/"Expandir" de um bubble que estourou o limite);
- "Voz" (corrigido 2026-09-06, pedido do usuário: ciclar direto no clique
  "gera ambiguidade sobre se o texto exibido representa o estado atual ou
  a ação que será executada") deixou de chamar `companion_panel.
  ciclar_modo_voz()` no clique - o Nível 1 agora é só um INDICADOR
  permanente do modo ativo (ícone/rótulo lidos de `companion_panel.
  modo_voz_atual`/`MODOS_VOZ_GLIFO`/`MODOS_VOZ_TEXTO`, atualizado via
  `modo_voz_alterado`) e o clique abre um Nível 2 (`_entrar_nivel2_voz`)
  com as 3 opções + "‹ Voltar" substituindo temporariamente a coluna
  principal; selecionar uma opção chama `companion_panel.
  definir_modo_voz(modo)` (aplica na hora) e volta ao Nível 1 sozinho -
  nunca duplica estado de modo de voz próprio, o painel continua sendo a
  única fonte de verdade;
- "Ações" abre a `GestureWheel`: um único nível de medalhões circulares no
  estilo do menu de emotes de Don't Starve Together. Reaproveita a MESMA
  fonte de transições válidas da bandeja e adapta a forma à tela (círculo,
  meia-roda ou quadrante), sem mover a GAIA;
- "Configurações" (renomeado em 2026-09-04) abre `modal_configuracoes.py`
  DIRETO neste processo - o modal de configurações do LOKI é nativo daqui
  desde que "o LOKI tem que conseguir se virar sozinho" virou requisito;
  funciona em modo demonstração igual, sem precisar de bridge/GAIA
  rodando. O botão "🧚 Mascot (LOKI)" do Painel da GAIA pede a MESMA
  janela por um caminho diferente (evento `settings_requested`, já que ele
  vive num processo separado e não pode instanciar um QWidget daqui
  direto) - ver `_processar_evento_gaia` em `process_main.py`;
- hover é um "hover-expand button" (pedido do usuário, 2026-09-02: "Oq eu
  queria era a ideia de hover-expand button") - o PRÓPRIO círculo anima a
  largura e vira uma pílula com ícone + texto ao passar o mouse, em vez de
  um rótulo/tooltip separado flutuando ao lado (1ª tentativa, descartada
  pelo usuário). O texto revela do lado de FORA (afastado da GAIA), o
  ícone fica sempre ancorado perto dela;
- árvore de submenu (nível 2+) só existe pra "Voz" por enquanto (ver acima,
  `_entrar_nivel2_voz`/`_sair_nivel2_voz`/`_trocar_nivel`) - reaproveita a
  MESMA coluna/pílulas do Nível 1 (glifos `◉`/`🎙`/`⊘`/`‹`, reutilizados
  de `companion_panel.MODOS_VOZ_GLIFO` pra manter consistência visual com
  outras interfaces do LOKI, como o doc pede), troca INSTANTÂNEA entre os
  dois conjuntos de círculos (sem stagger próprio - só o open/close do
  menu inteiro tem a animação especificada no doc). `self.direcao` fica
  exposta (doc: "a direção escolhida deve ser armazenada enquanto o menu
  estiver aberto") pra um submenu futuro herdar sem recalcular;
- "clique fora fecha" NÃO implementado (doc marca como opcional) - mesmo
  corte que `companion_panel.py` já faz (só Escape/re-toggle).

Bloqueio de autonomia enquanto aberto (decisão 2026-09-02, ver
`safety.py::SafetyController.bloquear_autonomia`) - impede o Wander de
tirá-la do lugar enquanto o menu está de pé, e evita ela sair voando
imediatamente ao fechar (cooldown reinicia do fim da interação,
`behavior_scheduler.py::_ao_autonomia_alterada`)."""
from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from mascot import conversation_service as conversa_servico_modulo
from mascot import companion_style as estilo
from mascot import config, platform_windows
from mascot.animacao_menu import preencher_menu_forcar_animacao
from mascot.gesture_wheel import GestureWheel

PASSO_MS = 16
DURACAO_ITEM_MS = 220.0  # mesma ordem de grandeza do expandir/recolher do CompanionPanel (plano, seção 5.3: 160-220ms)
ATRASO_ENTRE_ITENS_MS = 55.0  # meio da faixa 40-70ms sugerida no doc
DIAMETRO_CIRCULO = 44
GAP_ITENS = 10
GAP_GAIA = 14
LIMIAR_SCROLL_FECHAR_SOBRE_MENU = 60  # menor que o limiar de abrir (window.py) - já aberto, ativação acidental importa menos
DURACAO_HOVER_MS = 160.0  # expandir/recolher a pílula - um pouco mais lento que os 140ms de um rótulo pontual, é um movimento maior (largura inteira)
PADDING_PILULA_H = 14  # respiro do texto revelado dentro da pílula expandida
FONTE_ROTULO_PT = 10.0  # MESMO valor usado pra medir a largura reservada (__init__) e pra desenhar (paintEvent) - nunca divergir, ver achado abaixo

# (id, rótulo revelado ao expandir, glifo curto do círculo, desabilitado)
# ordem = ordem de entrada. Os 4 itens ganharam conteúdo real em 2026-09-03
# (ver docstring do módulo) - "Ações"/"GAIA" ficaram DESABILITADOS entre
# 2026-09-02 e 2026-09-03 (sugestão do GPT endossada pelo usuário: sinalizar
# "ainda não" em vez de aceitar clique e só fechar o menu, enquanto o
# conteúdo de cada um não estava definido) - `IDS_DESABILITADOS` continua
# aqui pronto pra um item futuro precisar do mesmo tratamento.
ITENS = (
    ("conversar", "Conversar", "💬", False),
    ("voz", "Voz", "🎤", False),
    ("acoes", "Ações", "⚡", False),
    ("gaia", "Configurações", "⚙️", False),
)
IDS_DESABILITADOS = frozenset(id_ for id_, _, _, desabilitado in ITENS if desabilitado)

# Nível 2 "Voz" (2026-09-06) - ordem de EXIBIÇÃO pedida pelo usuário
# (contínua -> push-to-talk -> desligada), independente da ordem do ciclo
# interno de `companion_panel.MODOS_VOZ_CICLO` (que começa em "desligada").
# "Voltar" ocupa o 4º slot - mesma contagem dos 4 itens do Nível 1, a
# coluna nunca precisa mudar de altura entre os dois níveis.
ID_VOLTAR = "voltar"
ORDEM_NIVEL2_VOZ = ("voz_continua", "click_to_talk", None)

# Estilos visuais do botão (2026-09-02) - comparados num artifact interativo
# (4 opções lado a lado, HTML/CSS) antes de escolher; "vidro" é o padrão
# escolhido pelo usuário, os outros 3 ficam disponíveis no Painel
# (`ui/qt_modais/mascot.py`, `mascot_config["menu_sao_estilo"]`). Cada
# entrada: `(cor_hex, alpha)` pra fundo/borda em repouso e em hover;
# `fundo_hover=None` sinaliza usar `gradiente_hover` em vez de cor sólida
# (só "aurora" usa isso hoje).
ESTILOS = {
    "classico": {
        "nome": "Dourado clássico",
        "fundo": ("#28282c", 0.92),
        "fundo_hover": ("#3a342a", 0.92),
        "borda": ("#2f2f34", 1.0),
        "borda_hover": ("#d4af6a", 1.0),
        "texto": "#f1efe9",
        "texto_hover": "#f3e8d2",
        "gradiente_hover": None,
    },
    "vidro": {
        "nome": "Vidro translúcido",
        "fundo": ("#ffffff", 0.05),
        "fundo_hover": ("#b4d7eb", 0.14),
        "borda": ("#d2e1eb", 0.20),
        "borda_hover": ("#d6e8f2", 0.55),
        "texto": "#eef3f6",
        "texto_hover": "#eef3f6",
        "gradiente_hover": None,
    },
    "selo": {
        "nome": "Selo (contorno)",
        "fundo": ("#000000", 0.0),  # sem preenchimento em repouso, só o traço
        "fundo_hover": ("#d4af6a", 0.10),
        "borda": ("#4a4238", 1.0),
        "borda_hover": ("#d4af6a", 1.0),
        "texto": "#948d80",
        "texto_hover": "#e7dcc4",
        "gradiente_hover": None,
    },
    "aurora": {
        "nome": "Aurora",
        "fundo": ("#282623", 0.92),
        "fundo_hover": None,  # usa gradiente_hover em vez de cor sólida
        "borda": ("#ffffff", 0.08),
        "borda_hover": ("#ffffff", 0.0),
        "texto": "#f1efe9",
        "texto_hover": "#12100c",  # escuro - contraste contra o gradiente claro
        "gradiente_hover": ("#d4af6a", "#8ecae6"),
    },
}
ESTILO_PADRAO = "vidro"


def _cor_com_alpha(cor_hex: str, alpha: float) -> QColor:
    cor = QColor(cor_hex)
    cor.setAlphaF(alpha)
    return cor


def _ease_out_back(t: float, overshoot: float = 1.7) -> float:
    """"desce, passa alguns pixels da posição final, volta, assenta" (doc,
    "Animação de abertura") - overshoot passa de 1.0 brevemente antes de
    convergir; quem usa isso já espera o valor sair de [0,1] no meio."""
    t = max(0.0, min(1.0, t)) - 1
    return t * t * ((overshoot + 1) * t + overshoot) + 1


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class _CirculoMenu(QWidget):
    """Um item do menu - "hover-expand button": círculo com ícone que, ao
    receber hover, anima a PRÓPRIA largura e vira uma pílula revelando o
    texto (pedido do usuário, 2026-09-02) - nunca um rótulo/tooltip
    separado. Widget de tamanho FIXO igual à largura RESERVADA pra essa
    linha inteira (`largura_widget` = maior pílula entre os 4 itens, pra
    todo círculo alinhar na mesma borda perto da GAIA independente do
    próprio texto ser mais curto) - só a PARTE DESENHADA (`_progresso`
    de entrada/saída da coluna + `_hover_progresso` de expandir/recolher)
    muda de tamanho, a geometria/hitbox real nunca muda depois de criada."""

    clicado = Signal()
    hover_alterado = Signal(bool)

    def __init__(
        self, glifo: str, rotulo: str, largura_widget: int, estilo_id: str = ESTILO_PADRAO,
        desabilitado: bool = False, parent=None,
    ):
        super().__init__(parent)
        self._glifo = glifo
        self._rotulo = rotulo
        # largura da pílula quando expandida = a MESMA largura reservada
        # pro widget (todo item expande igual, achado ao vivo: "os botoes
        # com o hover tem de ter a msm largura")
        self._largura_expandida = largura_widget
        self._estilo = ESTILOS.get(estilo_id, ESTILOS[ESTILO_PADRAO])
        # Desabilitado (2026-09-02, "Ações"/"GAIA" sem conteúdo real ainda)
        # - continua revelando o rótulo no hover (usuário vê o que VAI
        # fazer), mas nunca aceita clique nem destaca cor - `paintEvent`
        # aplica opacidade reduzida pra sinalizar "ainda não" visualmente.
        self._desabilitado = desabilitado
        # "Marcado" (2026-09-06) - indica a opção ATIVA num nível de seleção
        # (hoje só o Nível 2 "Voz", ver `MenuSAO._entrar_nivel2_voz`); doc:
        # "recebe um indicador visual, como ✓, glow ou destaque no
        # contorno" - optamos por destaque no CONTORNO (reaproveita a cor
        # de borda do hover, sem inventar cor/glifo novo), permanente
        # mesmo sem o mouse em cima (`paintEvent` abaixo).
        self._marcado = False
        self._lado = "right"  # atualizado em MenuSAO.abrir() - decide de que borda o círculo fica ancorado/pra onde a pílula cresce
        self._progresso = 0.0
        self._hover_progresso = 0.0
        self._hover = False
        self._pressionado = False
        self.resize(largura_widget, DIAMETRO_CIRCULO)
        self.setCursor(Qt.CursorShape.ArrowCursor if desabilitado else Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def definir_lado(self, lado: str) -> None:
        self._lado = lado
        self.update()

    def definir_progresso(self, valor: float) -> None:
        if valor == self._progresso:
            return
        self._progresso = valor
        self.update()

    def definir_hover_progresso(self, valor: float) -> None:
        if valor == self._hover_progresso:
            return
        self._hover_progresso = valor
        self.update()

    def definir_marcado(self, valor: bool) -> None:
        if valor == self._marcado:
            return
        self._marcado = valor
        self.update()

    def definir_conteudo(self, glifo: str, rotulo: str) -> None:
        """Troca o ícone/texto de um círculo JÁ CRIADO (2026-09-06) - usado
        pelo círculo "Voz" do Nível 1 pra refletir o modo ativo, sem
        recriar o widget nem mexer na largura reservada (`_largura_
        expandida` continua a mesma, calculada em `MenuSAO.__init__` a
        partir do MAIOR rótulo possível entre os dois níveis)."""
        self._glifo = glifo
        self._rotulo = rotulo
        self.update()

    def enterEvent(self, event) -> None:
        # desabilitado ainda revela o rótulo (largura expande via
        # `hover_alterado` abaixo), mas NUNCA destaca cor - `self._hover`
        # fica sempre False pra ele, único jeito que `paintEvent` sabe
        # disso sem precisar checar `_desabilitado` em cada trecho de cor.
        self._hover = not self._desabilitado
        self.update()
        if self._progresso >= 0.999:  # só expande se o círculo já assentou de vez na coluna
            self.hover_alterado.emit(True)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        self.hover_alterado.emit(False)

    def mousePressEvent(self, event) -> None:
        # ignora clique enquanto ainda está animando entrando/saindo -
        # evita ativar uma opção que visualmente ainda não "assentou".
        # Desabilitado nunca aceita clique nenhum (nem inicia o "press").
        if self._desabilitado:
            return
        if event.button() == Qt.MouseButton.LeftButton and self._progresso >= 0.999:
            self._pressionado = True
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pressionado:
            self._pressionado = False
            if self.rect().contains(event.position().toPoint()):
                self.clicado.emit()
            event.accept()

    def paintEvent(self, event) -> None:
        if self._progresso <= 0.0:
            return
        t_forma = _ease_out_back(self._progresso)
        # desabilitado sempre um pouco mais apagado - sinaliza "ainda não"
        # em vez de parecer quebrado (pedido do GPT/usuário, 2026-09-02)
        opacidade_entrada = _smoothstep(self._progresso) * (0.5 if self._desabilitado else 1.0)
        deslocamento = (1.0 - t_forma) * (DIAMETRO_CIRCULO * 0.65)
        escala_entrada = max(0.05, 0.55 + 0.45 * t_forma)

        t_hover = _smoothstep(self._hover_progresso)
        diametro = DIAMETRO_CIRCULO * escala_entrada
        largura_pilula = (DIAMETRO_CIRCULO + (self._largura_expandida - DIAMETRO_CIRCULO) * t_hover) * escala_entrada
        centro_y = self.height() / 2 + deslocamento

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(max(0.0, min(1.0, opacidade_entrada)))

        # a pílula (fundo) cresce sempre a partir da borda ANCORADA (perto
        # da GAIA) em direção à borda livre do widget - nunca o contrário
        if self._lado == "right":
            retangulo_pilula = QRectF(0.0, centro_y - diametro / 2, largura_pilula, diametro)
            retangulo_icone = QRectF(0.0, centro_y - diametro / 2, diametro, diametro)
        else:
            retangulo_pilula = QRectF(self.width() - largura_pilula, centro_y - diametro / 2, largura_pilula, diametro)
            retangulo_icone = QRectF(self.width() - diametro, centro_y - diametro / 2, diametro, diametro)

        est = self._estilo
        # destaque de contorno: hover OU "marcado" (opção ativa de um
        # nível de seleção) - marcado sozinho nunca muda fundo/texto, só o
        # contorno (doc: "destaque no contorno" como indicador permanente,
        # sem se confundir com o estado de hover em cima).
        destaque_contorno = (self._hover or self._marcado) and not self._desabilitado
        fundo_hex_alpha = (est["fundo_hover"] if self._hover else est["fundo"])
        borda_hex, borda_alpha = est["borda_hover"] if destaque_contorno else est["borda"]
        cor_texto = est["texto_hover"] if self._hover else est["texto"]

        painter.setPen(QPen(_cor_com_alpha(borda_hex, borda_alpha), 1.5))
        if self._hover and fundo_hex_alpha is None and est["gradiente_hover"]:
            gradiente = QLinearGradient(retangulo_pilula.topLeft(), retangulo_pilula.topRight())
            cor1, cor2 = est["gradiente_hover"]
            gradiente.setColorAt(0.0, QColor(cor1))
            gradiente.setColorAt(1.0, QColor(cor2))
            painter.setBrush(gradiente)
        else:
            painter.setBrush(_cor_com_alpha(*fundo_hex_alpha))
        painter.drawRoundedRect(retangulo_pilula, diametro / 2, diametro / 2)

        painter.setPen(QColor(cor_texto))
        fonte_glifo = painter.font()
        fonte_glifo.setPointSizeF(max(6.0, diametro * 0.35))
        painter.setFont(fonte_glifo)
        painter.drawText(retangulo_icone, Qt.AlignmentFlag.AlignCenter, self._glifo)

        if t_hover > 0.01:  # texto só desenha depois que a pílula já abriu espaço de verdade pra ele
            painter.setOpacity(max(0.0, min(1.0, opacidade_entrada * t_hover)))
            fonte_texto = painter.font()
            fonte_texto.setPointSizeF(FONTE_ROTULO_PT)
            painter.setFont(fonte_texto)
            # margem dos dois lados do texto (depois do ícone E antes da
            # borda externa da pílula) - achado ao vivo, pedido do
            # usuário: "n precisa deixar colado texto na borda, pode dar
            # uma pequena margem"
            largura_texto = max(0.0, largura_pilula - diametro - PADDING_PILULA_H * 2)
            if self._lado == "right":
                x_texto = diametro + PADDING_PILULA_H
            else:
                x_texto = self.width() - largura_pilula + PADDING_PILULA_H
            retangulo_texto = QRectF(x_texto, centro_y - diametro / 2, largura_texto, diametro)
            alinhamento = Qt.AlignmentFlag.AlignVCenter | (
                Qt.AlignmentFlag.AlignLeft if self._lado == "right" else Qt.AlignmentFlag.AlignRight
            )
            painter.drawText(retangulo_texto, alinhamento, self._rotulo)
        painter.end()


class MenuSAO(QWidget):
    """Estados: `closed` -> `opening` -> `open` -> `closing` -> `closed`
    (doc, "Estados recomendados" - sem `submenu_open`, nenhum submenu
    implementado nesta versão)."""

    def __init__(
        self, mascot_window, safety, conversation_service, controller=None, mascot_app=None,
        estilo_id: str = ESTILO_PADRAO, parent=None, conversation=None,
    ):
        super().__init__(parent)
        self._mascot_window = mascot_window
        self._safety = safety
        self._conversation_service = conversation_service
        # Conversation Overlay/"Bubble Mode" (2026-09-06) - "Conversar"
        # passou a chamar isto em vez de abrir o `CompanionPanel` direto
        # (ver `_ao_clicar`). Opcional (`None` só em teste isolado de
        # outra coisa que construa `MenuSAO` sem montar o `MascotApp`
        # inteiro) - mesmo corte de `controller`/`mascot_app` acima.
        self._conversation = conversation
        # "Ações" (forçar animação, ver `_abrir_menu_forcar_animacao`) usa
        # só `controller`. "Configurações" (`_abrir_configuracoes`) precisa da
        # `MascotApp` inteira - `modal_configuracoes.ModalConfiguracoes`
        # lê `.window`/`.config_mascot`/`.config_behaviors` dela.
        self._controller = controller
        self._mascot_app = mascot_app
        # `scheduler` vem de `mascot_app` (já passado pra "Configurações",
        # ver acima) - reaproveitado aqui pra `GestureWheel` conseguir
        # chamar `BehaviorScheduler.forcar_movimento` de verdade (2026-09-04,
        # achado ao vivo: "ao fazer movimentos como subida, ela n esta se
        # movendo") em vez de só trocar o clipe.
        scheduler = getattr(mascot_app, "scheduler", None)
        self._gesture_wheel = (
            GestureWheel(mascot_window, controller, safety, scheduler) if controller is not None else None
        )
        self._estado = "closed"
        self.direcao = "right"
        self._tempo_inicio_animacao = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # TODOS os 4 itens expandem pra MESMA largura (a da maior pílula
        # necessária, achado ao vivo, pedido do usuário: "os botoes... tem
        # de ter a msm largura") - nunca cada um com a largura do próprio
        # texto, senão "Voz" (curto) fica visivelmente mais estreito que
        # "Conversar" (longo) ao expandir.
        #
        # 🔥 CORRIGIDO (2026-09-02, achado ao vivo: "o texto maior esta
        # sendo cortado quando o botao abre para a esquerda") - media a
        # largura com `self.font()` (fonte PADRÃO do widget, menor), mas
        # `paintEvent` desenha o rótulo a `FONTE_ROTULO_PT` (10pt, maior) -
        # a reserva ficava estreita demais pro texto real, cortando "Conversar"
        # (o mais longo). Mais visível à esquerda porque o texto ali é
        # alinhado à DIREITA (perto do ícone) - o excesso cortava sempre a
        # PRIMEIRA letra ("C"); à direita cortaria a ÚLTIMA letra, só menos
        # óbvio visualmente. Agora mede com a MESMA fonte que desenha, mais
        # uma folga de 4px (hinting/antialiasing podem variar um pouco).
        fonte_medida = QFont(self.font())
        fonte_medida.setPointSizeF(FONTE_ROTULO_PT)
        fm = QFontMetrics(fonte_medida)
        # 2026-09-06: a reserva de largura agora também cobre os rótulos do
        # Nível 2 "Voz" (`conversation_service.MODOS_VOZ_TEXTO`) + "Voltar" - a
        # MESMA coluna/pílulas são reaproveitadas pros dois níveis, nunca
        # dá pra medir só os rótulos do Nível 1.
        rotulos_para_largura = [rotulo for _, rotulo, _, _ in ITENS]
        rotulos_para_largura += list(conversa_servico_modulo.MODOS_VOZ_TEXTO.values())
        rotulos_para_largura.append("Voltar")
        largura_widget = max(
            DIAMETRO_CIRCULO + PADDING_PILULA_H + fm.horizontalAdvance(rotulo) + PADDING_PILULA_H + 4
            for rotulo in rotulos_para_largura
        )
        altura = len(ITENS) * DIAMETRO_CIRCULO + (len(ITENS) - 1) * GAP_ITENS
        self.resize(largura_widget, altura)

        self._hover_estado = "closed"
        self._hover_tempo_inicio = 0.0
        self._circulo_hover_atual: _CirculoMenu | None = None
        self._circulo_animando: _CirculoMenu | None = None
        self._hover_timer = QTimer(self)
        self._hover_timer.timeout.connect(self._passo_hover)

        # `_nivel` 1 = coluna principal (4 itens), 2 = seleção de voz (só
        # existe enquanto `_circulos_voz` está visível - ver
        # `_entrar_nivel2_voz`/`_sair_nivel2_voz` mais abaixo).
        self._nivel = 1
        self._circulo_voz_nivel1: _CirculoMenu | None = None
        self._circulos: list[_CirculoMenu] = []
        for i, (id_, rotulo, glifo, desabilitado) in enumerate(ITENS):
            circulo = _CirculoMenu(glifo, rotulo, largura_widget, estilo_id, desabilitado, self)
            circulo.move(0, i * (DIAMETRO_CIRCULO + GAP_ITENS))
            circulo.clicado.connect(lambda id_=id_: self._ao_clicar(id_))
            circulo.hover_alterado.connect(lambda ativo, c=circulo: self._ao_hover_circulo(ativo, c))
            self._circulos.append(circulo)
            if id_ == "voz":
                self._circulo_voz_nivel1 = circulo

        # Nível 2 "Voz" (2026-09-06) - 3 modos + "Voltar", MESMOS slots
        # verticais que o Nível 1 (`ORDEM_NIVEL2_VOZ` + `ID_VOLTAR` = 4
        # entradas, mesma contagem de `ITENS`); começam escondidos - só
        # `_entrar_nivel2_voz` os mostra.
        self._circulos_voz: list[_CirculoMenu] = []
        for i, modo in enumerate(ORDEM_NIVEL2_VOZ):
            glifo = conversa_servico_modulo.MODOS_VOZ_GLIFO[modo]
            rotulo = conversa_servico_modulo.MODOS_VOZ_TEXTO[modo]
            circulo = _CirculoMenu(glifo, rotulo, largura_widget, estilo_id, False, self)
            circulo.move(0, i * (DIAMETRO_CIRCULO + GAP_ITENS))
            circulo.clicado.connect(lambda modo=modo: self._ao_selecionar_modo_voz(modo))
            circulo.hover_alterado.connect(lambda ativo, c=circulo: self._ao_hover_circulo(ativo, c))
            circulo.hide()
            self._circulos_voz.append(circulo)
        circulo_voltar = _CirculoMenu("‹", "Voltar", largura_widget, estilo_id, False, self)
        circulo_voltar.move(0, len(ORDEM_NIVEL2_VOZ) * (DIAMETRO_CIRCULO + GAP_ITENS))
        circulo_voltar.clicado.connect(self._sair_nivel2_voz)
        circulo_voltar.hover_alterado.connect(lambda ativo, c=circulo_voltar: self._ao_hover_circulo(ativo, c))
        circulo_voltar.hide()
        self._circulos_voz.append(circulo_voltar)

        # o botão "Voz" do Nível 1 é um INDICADOR permanente do modo ativo
        # (nunca um rótulo estático) - sincroniza agora e toda vez que o
        # modo mudar de verdade, de qualquer origem.
        self._conversation_service.modo_voz_alterado.connect(self._ao_modo_voz_alterado)
        self._atualizar_circulo_voz_nivel1()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._passo_animacao)
        self.hide()
        # `winId()` só pode ser forçado depois de o menu estar completamente
        # configurado; a preferência salva precisa valer também para esta
        # janela auxiliar, inclusive antes de o usuário abrir Configurações.
        QTimer.singleShot(0, lambda: platform_windows.aplicar_protecao_captura(
            self, bool(config.carregar_config_mascot().get("proteger_de_captura")),
        ))

    @property
    def esta_aberto(self) -> bool:
        return self._estado in ("opening", "open")

    # ------------------------------------------------------------------
    def abrir(self) -> None:
        if self._gesture_wheel is not None and self._gesture_wheel.esta_aberta:
            return
        if self._estado in ("opening", "open"):
            return
        if self._estado == "closing":
            # 🔥 achado 2026-09-02 (teste intermitente): reabrir NO MEIO de
            # um fechamento em andamento (ex.: usuário rola pra baixo nos
            # dois no menos de 1 tick de diferença) sobrescrevia `_estado`
            # pra "opening" sem nunca chamar `_finalizar_fechamento()` -
            # `_passo_animacao` passava a interpretar os ticks do MESMO
            # timer como abertura, e o bloqueio de autonomia ("menu_sao")
            # nunca era liberado, vazando pra sempre. Sempre completar o
            # fechamento primeiro (síncrono, sem animação) antes de abrir
            # de novo - nunca deixa a transição pela metade.
            self._timer.stop()
            self._finalizar_fechamento()
        x, y, lado = self._calcular_ancoragem()
        self.direcao = lado
        self.move(x, y)
        for circulo in self._circulos:
            circulo.definir_progresso(0.0)
            circulo.definir_hover_progresso(0.0)
            circulo.definir_lado(lado)
        self._estado = "opening"
        self._tempo_inicio_animacao = time.monotonic()
        self.show()
        self.setFocus()
        if self._safety is not None:
            self._safety.bloquear_autonomia("menu_sao")
        self._timer.start(PASSO_MS)

    def fechar(self, imediato: bool = False) -> None:
        """`imediato=True` (arraste real começando, `process_main.py`) pula
        a animação de saída - o usuário já está com a mão nela, não faz
        sentido o menu continuar recolhendo devagar ao lado."""
        if self._estado == "closed":
            return
        if imediato:
            self._timer.stop()
            self._finalizar_fechamento()
            return
        if self._estado != "closing":
            self._estado = "closing"
            self._tempo_inicio_animacao = time.monotonic()
            self._timer.start(PASSO_MS)

    def _finalizar_fechamento(self) -> None:
        self._estado = "closed"
        self.hide()
        self._hover_timer.stop()
        self._hover_estado = "closed"
        self._circulo_hover_atual = None
        self._circulo_animando = None
        for circulo in self._circulos:
            circulo.definir_hover_progresso(0.0)
        if self._nivel == 2:
            # fechar (Escape/scroll/arraste) NO MEIO do Nível 2 sempre volta
            # pro Nível 1 puro - reabrir mais tarde nunca deve nascer preso
            # na tela de seleção de voz (2026-09-06).
            self._trocar_nivel(escondem=self._circulos_voz, mostram=self._circulos)
            self._nivel = 1
        if self._safety is not None:
            self._safety.liberar_autonomia("menu_sao")

    # ------------------------------------------------------------------
    def _calcular_ancoragem(self) -> tuple[int, int, str]:
        """Mesmo critério de `companion_panel.py::_ancorar_junto_a_mascot`
        (lado com mais espaço, dentro da work area) via
        `platform_windows.lado_com_mais_espaco` - a GAIA nunca fica coberta
        porque a coluna inteira nasce FORA do retângulo dela (gap de
        `GAP_GAIA`), nunca sobre ele (doc, "Regra absoluta de
        posicionamento e direção"). `largura_coluna` já é a MAIOR pílula
        expandida (ver `__init__`) - a borda ANCORADA (perto dela) fica
        fixa nesse gap independente da largura reservada; só a borda
        LIVRE (onde o texto revela) que varia pra mais longe.

        A JANELA do Mascot é a célula/canvas inteiro (mesmo tamanho pra
        todo clipe nunca saltar entre eles), não a silhueta visível dela -
        ancorar pela borda da janela deixava um vão grande e vazio entre o
        menu e a personagem de verdade (achado ao vivo, 2026-09-02, pedido
        do usuário: "pode aproximar os botões da GAIA"). Descontamos a
        margem lateral transparente do asset ATUAL (`AnimationAsset.
        margem_esquerda_vazia_px`/`margem_direita_vazia_px`, escalada por
        `janela.escala` - a margem é medida no espaço de pixel ORIGINAL do
        asset) pra ancorar perto da silhueta, não do canvas."""
        janela = self._mascot_window
        tela = janela.screen() or QApplication.primaryScreen()
        area_x, area_y, area_w, area_h = platform_windows.obter_work_area_da_tela(tela)
        lado = platform_windows.lado_com_mais_espaco(janela.x(), janela.width(), area_x, area_w)
        largura_coluna, altura_coluna = self.width(), self.height()

        asset = janela.asset_atual
        if lado == "right":
            margem_vazia = int((asset.margem_direita_vazia_px if asset else 0) * janela.escala)
            x = janela.x() + janela.width() - margem_vazia + GAP_GAIA
        else:
            margem_vazia = int((asset.margem_esquerda_vazia_px if asset else 0) * janela.escala)
            x = janela.x() + margem_vazia - largura_coluna - GAP_GAIA
        x = max(area_x, min(x, area_x + area_w - largura_coluna))
        y = janela.y() + janela.height() // 2 - altura_coluna // 2
        y = max(area_y, min(y, area_y + area_h - altura_coluna))
        return x, y, lado

    def _passo_animacao(self) -> None:
        decorrido_ms = (time.monotonic() - self._tempo_inicio_animacao) * 1000
        n = len(self._circulos)
        todos_prontos = True
        for i, circulo in enumerate(self._circulos):
            if self._estado == "opening":
                atraso = i * ATRASO_ENTRE_ITENS_MS  # ordem normal: Conversar entra primeiro
                t = max(0.0, min(1.0, (decorrido_ms - atraso) / DURACAO_ITEM_MS))
                circulo.definir_progresso(t)
            else:  # closing - ordem INVERSA da abertura (doc: "fechamento na ordem inversa")
                atraso = ((n - 1) - i) * ATRASO_ENTRE_ITENS_MS
                t = max(0.0, min(1.0, (decorrido_ms - atraso) / DURACAO_ITEM_MS))
                circulo.definir_progresso(1.0 - t)
            if t < 1.0:
                todos_prontos = False
        if todos_prontos:
            self._timer.stop()
            if self._estado == "opening":
                self._estado = "open"
            else:
                self._finalizar_fechamento()

    # ------------------------------------------------------------------
    def _ao_hover_circulo(self, ativo: bool, circulo: "_CirculoMenu") -> None:
        if ativo:
            if self._circulo_animando is not None and self._circulo_animando is not circulo:
                # troca de alvo no meio de uma transição (mouse pulou direto
                # de um círculo pro vizinho, sem gap entre o leave e o enter)
                # - o timer compartilhado só acompanha 1 círculo por vez,
                # então o anterior precisa fechar NA HORA, senão fica preso
                # expandido pra sempre (achado escrevendo o teste)
                self._circulo_animando.definir_hover_progresso(0.0)
            self._circulo_hover_atual = circulo
            self._hover_estado = "opening"
        else:
            if self._circulo_hover_atual is not circulo:
                return  # leave tardio de um círculo que já não é mais o hover atual - ignora
            self._circulo_hover_atual = None
            self._hover_estado = "closing"
        self._circulo_animando = circulo  # só 1 círculo por vez pode estar em transição (1 cursor só)
        self._hover_tempo_inicio = time.monotonic()
        self._hover_timer.start(PASSO_MS)

    def _passo_hover(self) -> None:
        if self._circulo_animando is None:
            self._hover_timer.stop()
            return
        decorrido_ms = (time.monotonic() - self._hover_tempo_inicio) * 1000
        t = max(0.0, min(1.0, decorrido_ms / DURACAO_HOVER_MS))
        if self._hover_estado == "closing":
            t = 1.0 - t
        self._circulo_animando.definir_hover_progresso(t)
        if decorrido_ms >= DURACAO_HOVER_MS:
            self._hover_timer.stop()
            self._hover_estado = "open" if self._hover_estado == "opening" else "closed"
            self._circulo_animando = None

    # ------------------------------------------------------------------
    def _ao_clicar(self, id_: str) -> None:
        if id_ in IDS_DESABILITADOS:
            # defesa em profundidade - o próprio widget já recusa o clique
            # (`_CirculoMenu.mousePressEvent`), isso aqui é só pra nunca
            # fechar o menu OU fingir uma ação nem que alguém chame este
            # método direto (ex.: teste).
            return
        # "Voz" (2026-09-06) passou a abrir o Nível 2 em vez de ciclar o
        # modo na hora - NUNCA fecha o menu inteiro aqui, só os outros 3
        # itens continuam fechando o menu como antes.
        if id_ == "voz":
            self._entrar_nivel2_voz()
            return
        if id_ == "conversar":
            # Conversation Overlay/"Bubble Mode" (2026-09-06) - deixou de
            # abrir o `CompanionPanel` direto; `None` só em teste isolado
            # que não montou o `MascotApp` inteiro (ver `__init__`).
            if self._conversation is not None:
                self._conversation.alternar()
        elif id_ == "acoes":
            self._abrir_gesture_wheel()
        elif id_ == "gaia":
            self._abrir_configuracoes()
        self.fechar()

    # ------------------------------------------------------------------
    # Nível 2 "Voz" (2026-09-06, ver docstring do módulo e docs/ARQUITETURA.md)
    def _atualizar_circulo_voz_nivel1(self) -> None:
        """Mantém o círculo "Voz" do Nível 1 como INDICADOR permanente do
        modo ativo - chamado na construção e toda vez que `conversation_service.
        modo_voz_alterado` disparar, de qualquer origem (Nível 2 daqui,
        ciclo do botão do próprio painel, ou uma futura sincronização
        vinda da GAIA)."""
        modo = self._conversation_service.modo_voz_atual
        self._circulo_voz_nivel1.definir_conteudo(
            conversa_servico_modulo.MODOS_VOZ_GLIFO[modo], conversa_servico_modulo.MODOS_VOZ_TEXTO[modo],
        )

    def _ao_modo_voz_alterado(self, _modo) -> None:
        self._atualizar_circulo_voz_nivel1()

    def _entrar_nivel2_voz(self) -> None:
        if self._nivel == 2:
            return
        modo_atual = self._conversation_service.modo_voz_atual
        for circulo, modo in zip(self._circulos_voz, ORDEM_NIVEL2_VOZ + (ID_VOLTAR,)):
            circulo.definir_marcado(modo == modo_atual)
        self._trocar_nivel(escondem=self._circulos, mostram=self._circulos_voz)
        self._nivel = 2

    def _ao_selecionar_modo_voz(self, modo: str | None) -> None:
        """Doc: "seleciona -> aplica imediatamente -> retorna ao Nível 1" -
        `definir_modo_voz` já emite `modo_voz_alterado`, que por sua vez já
        atualiza o círculo "Voz" do Nível 1 (`_ao_modo_voz_alterado`) antes
        de `_sair_nivel2_voz` trocar a coluna de volta pra ele."""
        self._conversation_service.definir_modo_voz(modo)
        self._sair_nivel2_voz()

    def _sair_nivel2_voz(self) -> None:
        if self._nivel == 1:
            return
        self._trocar_nivel(escondem=self._circulos_voz, mostram=self._circulos)
        self._nivel = 1

    def _trocar_nivel(self, escondem: list["_CirculoMenu"], mostram: list["_CirculoMenu"]) -> None:
        """Troca INSTANTÂNEA entre os círculos do Nível 1 e do Nível 2 -
        sem stagger próprio (só o open/close do menu inteiro tem a
        animação especificada no doc). Mesmo corte de `_finalizar_
        fechamento`: nenhum hover/pílula em transição sobrevive à troca."""
        self._hover_timer.stop()
        self._hover_estado = "closed"
        self._circulo_hover_atual = None
        self._circulo_animando = None
        for circulo in escondem:
            circulo.definir_hover_progresso(0.0)
            circulo.definir_progresso(0.0)
            circulo.hide()
        for circulo in mostram:
            circulo.definir_hover_progresso(0.0)
            circulo.definir_lado(self.direcao)
            circulo.definir_progresso(1.0)
            circulo.show()

    def _construir_menu_forcar_animacao(self) -> QMenu | None:
        """Monta o `QMenu` de "Ações" sem exibi-lo - separado de
        `_abrir_menu_forcar_animacao` só pra dar pra inspecionar o
        conteúdo (`.actions()`) num teste sem precisar mostrar/fechar um
        popup de verdade. `None` se não há `controller` (menu construído
        sem essa dependência, ex.: teste isolado de outra coisa).
        `preencher_menu_forcar_animacao` (`mascot/animacao_menu.py`) é a
        MESMA função que a bandeja usa pro submenu "Forçar animação"
        (`process_main.py::_preencher_submenu_playground`) - extraída
        2026-09-03 pra não duplicar o filtro de transições válidas."""
        if self._controller is None:
            return None
        menu = QMenu(self)
        preencher_menu_forcar_animacao(menu, self._controller)
        return menu

    def _abrir_menu_forcar_animacao(self) -> None:
        """"Ações" (pedido do usuário, 2026-09-03: "deveria ser as
        animações dela, a função forçar animação da bandeja") - MESMA
        lógica de `process_main.py::_preencher_submenu_playground`: só
        lista transições VÁLIDAS a partir do estado lógico atual, nunca o
        catálogo inteiro (evita clicar um complemento fora de hora, mesmo
        motivo de lá). Sem árvore de submenu própria do Menu SAO nesta
        versão (doc, "árvore de submenu NÃO implementada") - um `QMenu`
        nativo pop-up no cursor é o jeito mais direto de expor o mesmo
        recurso aqui, sem inventar uma animação de submenu que ninguém
        pediu ainda. `popup()` (não `exec()`) - não bloqueia esperando o
        usuário escolher, mesmo espírito não-modal do resto do Menu SAO."""
        menu = self._construir_menu_forcar_animacao()
        if menu is not None:
            menu.popup(QCursor.pos())

    def _abrir_gesture_wheel(self) -> None:
        """Abre a roda antes de o Menu SAO liberar seu bloqueio de autonomia."""
        if self._gesture_wheel is not None:
            self._gesture_wheel.abrir()

    def fechar_tudo(self, imediato: bool = False) -> None:
        """Fecha menu e roda; usado quando um arraste real começa."""
        self.fechar(imediato=imediato)
        if self._gesture_wheel is not None:
            self._gesture_wheel.fechar()

    def _abrir_configuracoes(self) -> None:
        """"Configurações" (pedido do usuário, 2026-09-03, renomeado em 2026-09-04
        depois do modal de configurações virar nativo do LOKI: "o ideal é
        mantermos sempre o modal do loki atualizado. E a gaia ver meio q
        ele") - delega pra `MascotApp._abrir_configuracoes` (instância
        única e persistente, MESMO caminho da bandeja e do evento vindo da
        GAIA) em vez de construir um modal próprio aqui - nunca duas
        fontes de verdade pro mesmo modal. `None` só se `mascot_app` não
        foi passado (ex.: teste isolado de outra coisa)."""
        if self._mascot_app is None:
            return
        self._mascot_app._abrir_configuracoes()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            # dentro do Nível 2 "Voz", Escape só volta um nível (mesmo
            # destino do próprio botão "‹ Voltar") - um 2º Escape fecha o
            # menu inteiro, mesma progressão de `GestureWheel` com o campo
            # de filtro (2026-09-06).
            if self._nivel == 2:
                self._sair_nivel2_voz()
            else:
                self.fechar()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        """Scroll pra cima enquanto o cursor está SOBRE O PRÓPRIO MENU
        (não só sobre a GAIA, ver `window.py::wheelEvent`) também fecha -
        doc não deixa claro se a regra de fechar exige estar sobre ela, e
        fechar com o cursor já em cima do menu é o caso mais comum na
        prática. Limiar único (sem acumulador) - já está aberto, uma
        rolagem de verdade aqui é intencional quase sempre."""
        if event.angleDelta().y() >= LIMIAR_SCROLL_FECHAR_SOBRE_MENU:
            self.fechar()
        event.accept()
