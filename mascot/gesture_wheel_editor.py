# -*- coding: utf-8 -*-
"""Editor visual das ações, páginas e retratos da Gesture Wheel.

**Redesenho 2026-09-04** (usuário mandou print de referência, "melhora
essa paleta, consegue deixar mais proximo disso" -> "redesign completo
como a imagem") - banner com título/descrição, pills de categoria com
ícone (em vez das sub-abas `criar_tabwidget` de antes), emblema de
categoria colorido ao lado do nome, menu "⋮" (substituindo o botão "×"),
barra de seleção em massa (remover selecionadas / ordenar
automaticamente) e um rodapé Cancelar/Aplicar/Restaurar padrão - MUDANÇA
DE COMPORTAMENTO deliberada e aceita pelo usuário: as escolhas da roda
agora ficam em RASCUNHO em memória (`self._selecionadas`/`self._imagens`/
`self._limite`) e só gravam em `data/gesture_wheel.json` quando
"✓ Aplicar" é clicado - `gesture_wheel.json` só é a fonte de verdade de
novo depois disso. Esse fluxo é EXCLUSIVO desta aba - as outras 4 abas de
`modal_configuracoes.py` continuam aplicando cada campo na hora, como
antes (não existe pedido do usuário pra mudar isso lá).

**A paginação em si (rolar o mouse sobre a roda ou ←/→ pra ver o resto)
foi cogitada removida em 2026-09-04 e revertida no mesmo dia** - o pedido
original ("n quero ter q ficar rodando pagina para os lados") era na
verdade sobre a JANELA de Configurações abrir cortada por padrão, não
sobre a roda em si; a roda continua paginando normalmente, respeitando
"Máx./página" (`self._limite`).

Duas coisas da imagem de referência NÃO foram reproduzidas de propósito
(evitar inventar conteúdo sem base real): a arte de personagem no banner
(não existe um retrato/portrait pronto nos assets, só sprites de corpo
inteiro dentro de atlas) e a linha de descrição por animação (exigiria
escrever texto novo pras 44 ações, sem fonte confiável do que cada uma
faz de verdade).

**2026-09-05** - 3ª rodada de pedidos: a alça de arrastar (⠿) passou a
reordenar de VERDADE (`QDrag` do Qt sobre os `QFrame` existentes, card
visivelmente arrastado + linha dourada indicando onde vai entrar) - o
campo "Ordem" por linha SUMIU, a página virou sempre derivada da posição
entre as marcadas; nova pill "Tudo" (todas as categorias juntas, onde o
arraste entre categorias diferentes faz mais sentido); o menu "⋮" (só
tinha 1 opção) virou um botão "🗑" direto, mesma linguagem de "🗑 Remover
selecionadas". Ver docstrings de `_filtrar_evento_alca`/`_filtrar_evento_
linha`/`_mostrar_indicador_em` pro mecanismo de arrastar-e-soltar."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, Qt
from PySide6.QtGui import QDrag, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMenu, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from mascot import state_catalog
from mascot.gesture_wheel import (
    CAMINHO_CONFIG, acoes_configuradas, carregar_configuracao,
    eh_transicao_de_retorno, rotulo_animacao, salvar_configuracao,
)
from mascot.qt_widgets import (
    BG_COLOR, BORDA_SUTIL, GAIA_GOLD, HIGHLIGHT_COLOR, SURFACE_COLOR, TEXT_COLOR, TEXT_DIM,
    CheckboxQuadrado, FONTE_BASE, cor_com_alpha, confirmar_acao, criar_botao,
    criar_descricao, criar_frame_item, criar_lineedit, criar_spinbox, criar_titulo_secao,
)

# Só animações alcançáveis DIRETO de um estado de repouso entram aqui -
# metade de retorno de uma sequência (`eh_transicao_de_retorno`) nunca faz
# sentido como ação escolhida isoladamente (ver docstring da função) e,
# sem esse filtro, inflava a lista com nomes truncados feios (ids longos
# tipo `substituicao-ninja_para_flutuando`) que na prática nunca são a
# ação que alguém queria atribuir a um botão da roda.
IDS_ESCOLHIVEIS = tuple(
    aid for aid in state_catalog.CATALOGO
    if not eh_transicao_de_retorno(aid) and aid not in state_catalog.IDS_OCULTOS_DE_SELECAO
)

PASTA_ICONES = CAMINHO_CONFIG.parents[1] / "assets" / "gesture_wheel" / "icons"
# "Tudo" (2026-09-05, pedido do usuário) - pill extra que mostra as 7
# categorias reais juntas, sem filtrar - é aqui que a ORDEM/arraste faz
# mais sentido de verdade, já que a roda respeita a posição entre
# categorias diferentes (ver `self._ordem`). Não é uma categoria real
# (`categoria_animacao` nunca devolve "Tudo") - tratada à parte em
# `_reconstruir_linhas`.
CATEGORIA_TUDO = "Tudo"
# "Outras" (2026-09-06, pedido do usuário: "'Outras' n vai ser tag de
# animação, vai ser tipo uma pasta contendo categorias") - deixou de ser
# uma pill que FILTRA animações direto; virou uma PASTA que, ao passar o
# mouse, abre um menu vertical com as categorias reais listadas em
# `SUBCATEGORIAS_OUTRAS` (cada uma continua sendo o valor de verdade
# devolvido por `categoria_animacao`, só não ganha mais pill própria na
# linha horizontal - é assim que a lista de categorias para de crescer
# pros lados). "Leque" foi a primeira a entrar aqui (2026-09-06, "leque
# vai ser uma nova categoria q entrara dentro da pasta outros") - existia
# como pill própria por um dia só.
SUBCATEGORIAS_OUTRAS = ("Leque",)
CATEGORIAS = (
    CATEGORIA_TUDO, "Movimento", "Especiais", "Sentada", "Flutuando",
    "Transições", "Expressões", "Outras",
)
# Ícone (a cor vem de graça - emoji tem cor própria, não é afetado pelo
# `color:` do CSS do botão) e cor de destaque só pro EMBLEMA ao lado do
# nome (2026-09-04, achado ao vivo: "vários elementos da msm cor, q n
# fazem conversar bem" - cada categoria com sua própria cor de emblema
# evita que tudo vire só dourado/neutro). Inclui as sub-categorias de
# "Outras" (`SUBCATEGORIAS_OUTRAS`) - usadas no menu da pasta e no
# emblema de cada linha, mesmo sem pill própria.
CATEGORIA_ICONE = {
    CATEGORIA_TUDO: "🗂", "Movimento": "🏃", "Especiais": "⭐", "Sentada": "🪑", "Flutuando": "🪶",
    "Leque": "🪭", "Transições": "➕", "Expressões": "😊", "Outras": "🔳",
}
CATEGORIA_COR = {
    "Movimento": "#7dd3fc", "Especiais": GAIA_GOLD, "Sentada": "#f5a3b0",
    "Flutuando": "#93c5fd", "Leque": "#c4b5fd", "Transições": "#fdba74", "Expressões": "#86efac",
    "Outras": "#a3a3a3",
}


def categoria_animacao(animation_id: str) -> str:
    # "Leque" (2026-09-06, pedido do usuário: "Cria uma tag Leque, no msm
    # nivel do sentada ou flutuando") - antes entrava em "Especiais" junto
    # com ninja/chaos/transformação, misturado com coisas bem diferentes;
    # ganhou categoria PRÓPRIA, checada antes de "Especiais" pra não cair
    # lá (`flutuando_para_leque`/`leque_*`/`leque-esnobe_para_neutra`
    # todos têm a tag "fan" OU "leque" no id).
    entrada = state_catalog.CATALOGO.get(animation_id)
    tags = set(entrada.tags if entrada else ())
    if "movement" in tags or any(parte in animation_id for parte in ("direita", "esquerda", "subida", "descida")):
        return "Movimento"
    if "fan" in tags or "leque" in animation_id:
        return "Leque"
    # 2026-09-06, achado ao vivo: "transformações era p entrar em
    # Especiais, nao outras" - a checagem só cobria parte da cena
    # (`ssj3_invocacao-dragao`/`ssj3_para_chamuscada` batiam por "ssj"/
    # "dragao" no id, mas `transformacao_inicio` não tinha NENHUM tag/
    # substring aqui - caía em "Outras"; `transformacao_fim` caía em
    # "Transições"; `chamuscada_para_flutuando` caía em "Flutuando" -
    # os 5 clipes da MESMA cena cinematográfica espalhados em 3
    # categorias diferentes. Cobrindo todas as tags reais da sequência
    # (`transformation`/`ssj3`/`dragon`/`soot`, ver `state_catalog.py`)
    # os 5 caem juntos em "Especiais", checado ANTES de "Transições"/
    # "Flutuando" pra ganhar prioridade sobre elas.
    if any(tag in tags for tag in ("ninja", "chaos", "special", "transformation", "ssj3", "dragon", "soot")) or any(
        parte in animation_id for parte in ("ninja", "chaos", "ssj", "dragao", "brinde", "transformacao", "chamuscada")
    ):
        return "Especiais"
    if animation_id.startswith("sentada") or "sitting" in tags:
        return "Sentada"
    if animation_id.startswith("flutuando") or "floating" in tags:
        return "Flutuando"
    if "transition" in tags:
        return "Transições"
    if any(tag in tags for tag in ("laugh", "greeting", "thinking", "tired", "shy", "playful")):
        return "Expressões"
    return "Outras"


class EditorGestureWheel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._categoria_atual = CATEGORIAS[0]
        self._linhas: dict[str, QFrame] = {}
        self._miniaturas: dict[str, QLabel] = {}
        self._botoes_remover_imagem: dict[str, QPushButton] = {}
        self._arraste_origem_id: str | None = None
        self._arraste_pos_inicio = None
        # Linha dourada fina que marca ONDE o card vai entrar durante o
        # arraste (2026-09-05, pedido do usuário: "ficando aquela linha
        # entre os cards onde ele vai ser inserido") - criada uma única
        # vez (não recriada a cada `_reconstruir_linhas`) e só entra/sai
        # do `_lista_layout` durante um arraste em andamento.
        self._indicador_insercao = QFrame()
        self._indicador_insercao.setFixedHeight(3)
        self._indicador_insercao.setStyleSheet(f"background-color:{GAIA_GOLD};border-radius:1px;")
        self._indicador_insercao.hide()
        self._carregar_do_disco()

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(10)

        raiz.addWidget(self._montar_banner())

        topo = QHBoxLayout()
        busca = criar_lineedit()
        busca.setPlaceholderText("Buscar animação…")
        busca.setClearButtonEnabled(True)
        busca.textChanged.connect(self._filtrar)
        self._busca = busca
        topo.addWidget(busca, 1)
        topo.addWidget(criar_descricao("Máx./página"))
        self._spin_limite = criar_spinbox(1, 8, self._limite, largura=58)
        self._spin_limite.valueChanged.connect(self._alterar_limite)
        topo.addWidget(self._spin_limite)
        raiz.addLayout(topo)

        cabecalho = QHBoxLayout()
        cabecalho.addWidget(criar_descricao("Usar"), 0)
        cabecalho.addSpacing(56)
        cabecalho.addWidget(criar_descricao("Animação"), 1)
        cabecalho.addSpacing(126)
        raiz.addLayout(cabecalho)

        raiz.addLayout(self._montar_pills())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(320)
        conteudo = QWidget()
        self._lista_layout = QVBoxLayout(conteudo)
        self._lista_layout.setContentsMargins(0, 0, 4, 0)
        self._lista_layout.setSpacing(4)
        scroll.setWidget(conteudo)
        raiz.addWidget(scroll)
        self._reconstruir_linhas()

        raiz.addLayout(self._montar_barra_selecao())

        raiz.addWidget(criar_descricao(
            "Arraste pela alça (⠿) pra reordenar - a ordem/página da roda segue a posição "
            "aqui na aba \"Tudo\". Ela se prepara sozinha (levanta, etc.) se a ação exigir "
            "outro estado. Role sobre a roda ou use ←/→ para trocar de página. As mudanças "
            "valem depois de \"Aplicar\"."
        ))

        raiz.addLayout(self._montar_rodape())

    # ------------------------------------------------------------------
    # Carregamento / rascunho (2026-09-04) - `self._config` é só a FOTO do
    # que está gravado em disco agora; `_selecionadas`/`_ordem`/`_imagens`/
    # `_limite` são o RASCUNHO em memória que a UI edita - só viram arquivo
    # de verdade em `_aplicar`.
    def _carregar_do_disco(self) -> None:
        self._config = carregar_configuracao()
        self._limite = max(1, min(8, int(self._config.get("quantidade_maxima", 8))))
        configuradas = acoes_configuradas(self._config)
        # `_ordem` (2026-09-05) - posição de TODAS (marcadas ou não) na aba
        # "Tudo"; a página deixou de ser um campo salvo por item (spinbox
        # "Ordem") e virou só a posição entre as MARCADAS, recalculada em
        # `_aplicar` (pedido do usuário: "a ordem que aparece lá nos
        # círculos... pela posição na aba todos"). Ids configurados entram
        # na ordem salva; o resto (nunca escolhido ainda) completa atrás,
        # na ordem do catálogo.
        ids_configurados_em_ordem = [
            animation_id for animation_id, _pagina in configuradas
            if animation_id in IDS_ESCOLHIVEIS
        ]
        self._selecionadas: set[str] = set(ids_configurados_em_ordem)
        if not configuradas:
            self._selecionadas = set(IDS_ESCOLHIVEIS)
        restantes = [aid for aid in IDS_ESCOLHIVEIS if aid not in ids_configurados_em_ordem]
        self._ordem: list[str] = ids_configurados_em_ordem + restantes
        imagens = self._config.get("imagens", {})
        self._imagens = dict(imagens) if isinstance(imagens, dict) else {}

    def _montar_banner(self) -> QFrame:
        banner = QFrame()
        banner.setStyleSheet(f"""
            QFrame {{
                background-color: {HIGHLIGHT_COLOR};
                border: 1px solid {BORDA_SUTIL};
                border-radius: 10px;
            }}
        """)
        lay = QVBoxLayout(banner)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        titulo = criar_titulo_secao("🎬 Roda de ações", GAIA_GOLD, 16)
        lay.addWidget(titulo)
        lay.addWidget(criar_descricao(
            "Escolha quais animações aparecem, em qual página e a imagem de cada botão."
        ))
        return banner

    def _montar_pills(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(6)
        # Sem QButtonGroup exclusivo (2026-09-06, removido) - o estado
        # "marcado" de cada pill é 100% gerido à mão por
        # `_atualizar_pills_checked` (precisa disso desde que "Outras"
        # virou pasta: selecionar uma sub-categoria como "Leque" marca
        # "Outras", não uma pill própria). Um QButtonGroup exclusivo
        # RECUSA desmarcar programaticamente o único botão marcado (é a
        # garantia dele de sempre ter um marcado) - isso travava "Tudo"
        # marcado pra sempre depois do primeiro clique, mesmo trocando
        # de categoria depois.
        self._botoes_pill: dict[str, QPushButton] = {}
        for categoria in CATEGORIAS:
            pill = QPushButton(f"{CATEGORIA_ICONE[categoria]}  {categoria}")
            pill.setCheckable(True)
            pill.setCursor(Qt.PointingHandCursor)
            pill.setStyleSheet(f"""
                QPushButton {{
                    background-color: {SURFACE_COLOR};
                    color: {TEXT_DIM};
                    border: 1px solid {BORDA_SUTIL};
                    border-radius: 14px;
                    padding: 6px 14px;
                    font-family: '{FONTE_BASE}';
                    font-weight: 600;
                }}
                QPushButton:checked {{
                    background-color: {GAIA_GOLD};
                    color: {BG_COLOR};
                    border-color: {GAIA_GOLD};
                }}
                QPushButton:hover:!checked {{
                    background-color: {BORDA_SUTIL};
                    color: {TEXT_COLOR};
                }}
            """)
            if categoria == "Outras":
                # Pasta, não filtro direto (ver comentário de
                # `SUBCATEGORIAS_OUTRAS`) - passar o mouse abre o menu
                # vertical com as categorias reais; o clique também abre
                # (mesmo menu, pro caso de não rolar o mouse até ela) em
                # vez de filtrar por "Outras" - não existe mais nenhuma
                # animação classificada direto nela.
                pill.installEventFilter(self)
                pill.clicked.connect(lambda: self._abrir_menu_outras())
            else:
                pill.clicked.connect(lambda _=False, c=categoria: self._selecionar_categoria(c))
            self._botoes_pill[categoria] = pill
            linha.addWidget(pill)
        linha.addStretch(1)
        self._atualizar_pills_checked()
        return linha

    def _atualizar_pills_checked(self) -> None:
        ativa = "Outras" if self._categoria_atual in SUBCATEGORIAS_OUTRAS else self._categoria_atual
        for nome, pill in self._botoes_pill.items():
            pill.setChecked(nome == ativa)

    def _abrir_menu_outras(self) -> None:
        # Clicar em "Outras" sem escolher nada no menu não deve mudar a
        # categoria ativa de verdade - restaura o estado real (desfaz o
        # toggle automático do próprio Qt no botão checável) antes de
        # abrir o menu.
        self._atualizar_pills_checked()
        pill = self._botoes_pill["Outras"]
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {SURFACE_COLOR};
                color: {TEXT_COLOR};
                border: 1px solid {BORDA_SUTIL};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 14px;
                border-radius: 6px;
            }}
            QMenu::item:selected {{
                background-color: {GAIA_GOLD};
                color: {BG_COLOR};
            }}
        """)
        for subcategoria in SUBCATEGORIAS_OUTRAS:
            acao = menu.addAction(f"{CATEGORIA_ICONE[subcategoria]}  {subcategoria}")
            acao.triggered.connect(lambda _=False, c=subcategoria: self._selecionar_categoria(c))
        menu.exec(pill.mapToGlobal(pill.rect().bottomLeft()))

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (nome do Qt)
        if obj is self._botoes_pill.get("Outras") and event.type() == QEvent.Type.Enter:
            self._abrir_menu_outras()
        return super().eventFilter(obj, event)

    def _montar_barra_selecao(self) -> QHBoxLayout:
        # "🔀 Ordenar automaticamente" (2026-09-04) removido (2026-09-05) -
        # existia pra redistribuir as marcadas em páginas consecutivas sem
        # buraco; a página virou sempre DERIVADA da posição em `_ordem`
        # (recalculada em `_aplicar`), então nunca mais sobra buraco pra
        # "consertar" - a própria razão de existir do botão sumiu.
        linha = QHBoxLayout()
        self._label_contagem = criar_descricao(self._texto_contagem())
        linha.addWidget(self._label_contagem)
        linha.addStretch(1)
        botao_remover = criar_botao("🗑 Remover selecionadas", cor_texto=TEXT_DIM)
        botao_remover.clicked.connect(self._remover_selecionadas)
        linha.addWidget(botao_remover)
        return linha

    def _montar_rodape(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        botao_restaurar = criar_botao("🔄 Restaurar padrão", cor_texto=TEXT_DIM)
        botao_restaurar.clicked.connect(self._restaurar_padrao)
        linha.addWidget(botao_restaurar)
        linha.addStretch(1)
        botao_cancelar = criar_botao("Cancelar", cor_texto=TEXT_DIM)
        botao_cancelar.clicked.connect(self._cancelar)
        linha.addWidget(botao_cancelar)
        botao_aplicar = criar_botao("✓ Aplicar", preenchido=True)
        botao_aplicar.clicked.connect(self._aplicar)
        linha.addWidget(botao_aplicar)
        return linha

    # ------------------------------------------------------------------
    def _texto_contagem(self) -> str:
        n = len(self._selecionadas)
        return f"{n} ação selecionada" if n == 1 else f"{n} ações selecionadas"

    def _selecionar_categoria(self, categoria: str) -> None:
        self._categoria_atual = categoria
        self._atualizar_pills_checked()
        self._reconstruir_linhas()
        self._filtrar(self._busca.text())

    def _reconstruir_linhas(self) -> None:
        while self._lista_layout.count():
            item = self._lista_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._linhas.clear()
        self._miniaturas.clear()
        self._botoes_remover_imagem.clear()
        # Itera por `_ordem` (posição de arrasto), não pela ordem crua do
        # catálogo (`IDS_ESCOLHIVEIS`) - "Tudo" mostra todo mundo; as
        # outras pills continuam filtrando por categoria real.
        for animation_id in self._ordem:
            if self._categoria_atual == CATEGORIA_TUDO or categoria_animacao(animation_id) == self._categoria_atual:
                self._criar_linha(animation_id, self._lista_layout)
        self._lista_layout.addStretch(1)

    def _criar_linha(self, animation_id: str, lista: QVBoxLayout) -> None:
        # `criar_frame_item` - MESMA fábrica que `_linha_skin` do Avatar
        # Virtual usa (`ui/qt_modais/avatar_virtual.py`), nunca cor solta.
        linha = criar_frame_item(fundo=HIGHLIGHT_COLOR)
        linha.setAcceptDrops(True)
        linha.setProperty("papel_arraste", "linha")
        linha.setProperty("animation_id", animation_id)
        linha.installEventFilter(self)
        lay = QHBoxLayout(linha)
        lay.setContentsMargins(7, 6, 7, 6)
        lay.setSpacing(8)

        # Alça de arrastar - reordena de verdade (2026-09-05, antes só
        # visual): pressionar e arrastar daqui solta ANTES do item onde o
        # cursor passar por cima (metade de baixo da linha-alvo = depois
        # dele) - ver `eventFilter`.
        alca = criar_descricao("⠿")
        alca.setFixedWidth(14)
        alca.setCursor(Qt.CursorShape.SizeAllCursor)
        alca.setToolTip("Arrastar para reordenar")
        alca.setProperty("papel_arraste", "alca")
        alca.setProperty("animation_id", animation_id)
        alca.installEventFilter(self)
        lay.addWidget(alca)

        marcar = CheckboxQuadrado()
        marcar.setChecked(animation_id in self._selecionadas)
        marcar.setToolTip("Exibir esta animação na roda")
        marcar.stateChanged.connect(
            lambda estado, aid=animation_id: self._alternar(aid, bool(estado))
        )
        lay.addWidget(marcar)

        miniatura = QLabel()
        miniatura.setFixedSize(44, 44)
        miniatura.setAlignment(Qt.AlignmentFlag.AlignCenter)
        miniatura.setStyleSheet(
            f"background:{HIGHLIGHT_COLOR};border:1px dashed {TEXT_DIM};"
            f"border-radius:8px;color:{TEXT_DIM};"
        )
        self._miniaturas[animation_id] = miniatura
        self._atualizar_miniatura(animation_id)
        lay.addWidget(miniatura)

        coluna_nome = QVBoxLayout()
        coluna_nome.setSpacing(2)
        linha_nome = QHBoxLayout()
        linha_nome.setSpacing(6)
        nome = criar_descricao(f"<b>{rotulo_animacao(animation_id)}</b>")
        nome.setToolTip(animation_id)
        linha_nome.addWidget(nome)
        linha_nome.addWidget(self._criar_emblema_categoria(categoria_animacao(animation_id)))
        linha_nome.addStretch(1)
        coluna_nome.addLayout(linha_nome)
        lay.addLayout(coluna_nome, 1)

        imagem = criar_botao("Imagem…")
        imagem.setFixedHeight(28)
        imagem.clicked.connect(lambda _=False, aid=animation_id: self._escolher_imagem(aid))
        lay.addWidget(imagem)

        # "🗑" (2026-09-05, substitui o menu "⋮" de 2026-09-04) - só tinha
        # UMA opção lá dentro ("usar iniciais automáticas"), então o menu
        # era indireção sem propósito - botão direto representa a própria
        # função (remover a imagem vinculada), MESMO ícone de "🗑 Remover
        # selecionadas" (achado ao vivo: "coloca um icone no botao de
        # remover imagem" - só "×" não deixava a função óbvia de cara).
        remover_imagem = criar_botao("🗑", cor_texto=TEXT_DIM)
        remover_imagem.setFixedSize(30, 28)
        remover_imagem.setToolTip("Remover imagem (volta pras iniciais automáticas)")
        remover_imagem.setEnabled(animation_id in self._imagens)
        remover_imagem.clicked.connect(lambda _=False, aid=animation_id: self._limpar_imagem(aid))
        lay.addWidget(remover_imagem)
        self._botoes_remover_imagem[animation_id] = remover_imagem

        self._linhas[animation_id] = linha
        lista.addWidget(linha)

    def _criar_emblema_categoria(self, categoria: str) -> QLabel:
        cor = CATEGORIA_COR.get(categoria, TEXT_DIM)
        emblema = QLabel(categoria.lower())
        emblema.setStyleSheet(f"""
            color: {cor};
            background-color: {cor_com_alpha(cor, 0.16)};
            border-radius: 8px;
            padding: 1px 8px;
            font-size: 9pt;
            font-weight: 600;
        """)
        return emblema

    # ------------------------------------------------------------------
    # Arrastar-e-soltar pra reordenar (2026-09-05) - `QDrag` padrão do Qt
    # (não `QListWidget`/`InternalMove` - manter as linhas como `QFrame`
    # com `criar_frame_item`, mesma fábrica visual do resto do app, em vez
    # de reescrever a lista inteira só pra ganhar reorder nativo). A alça
    # (`papel_arraste="alca"`) inicia o arraste; a LINHA inteira
    # (`papel_arraste="linha"`) aceita o drop - soltar na metade de cima
    # insere ANTES do alvo, na metade de baixo insere DEPOIS.
    def eventFilter(self, obj, event) -> bool:
        papel = obj.property("papel_arraste")
        if papel == "alca":
            return self._filtrar_evento_alca(obj, event)
        if papel == "linha":
            return self._filtrar_evento_linha(obj, event)
        return super().eventFilter(obj, event)

    def _filtrar_evento_alca(self, alca: QLabel, event) -> bool:
        tipo = event.type()
        if tipo == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._arraste_origem_id = alca.property("animation_id")
            self._arraste_pos_inicio = event.position()
            return True
        if tipo == QEvent.Type.MouseMove and self._arraste_origem_id == alca.property("animation_id"):
            delta = event.position() - self._arraste_pos_inicio
            if delta.manhattanLength() >= QApplication.startDragDistance():
                origem_id = self._arraste_origem_id
                self._arraste_origem_id = None
                self._iniciar_drag(alca, origem_id, event.position())
            return True
        if tipo == QEvent.Type.MouseButtonRelease:
            self._arraste_origem_id = None
            return True
        return False

    def _iniciar_drag(self, alca: QLabel, origem_id: str, pos_na_alca) -> None:
        """Card visivelmente arrastado (2026-09-05, pedido do usuário:
        "Podia ser visivel o card sendo de fato arrastado") - `QDrag.
        setPixmap` com um retrato semi-transparente da própria linha
        (`QWidget.grab()`), não o cursor genérico padrão do Qt."""
        drag = QDrag(alca)
        mime = QMimeData()
        mime.setText(origem_id)
        drag.setMimeData(mime)
        linha_origem = self._linhas.get(origem_id)
        if linha_origem is not None:
            retrato = linha_origem.grab()
            semi_transparente = QPixmap(retrato.size())
            semi_transparente.fill(Qt.GlobalColor.transparent)
            pintor = QPainter(semi_transparente)
            pintor.setOpacity(0.75)
            pintor.drawPixmap(0, 0, retrato)
            pintor.end()
            drag.setPixmap(semi_transparente)
            drag.setHotSpot(alca.mapTo(linha_origem, pos_na_alca.toPoint()))
        drag.exec(Qt.DropAction.MoveAction)
        self._esconder_indicador()

    def _filtrar_evento_linha(self, linha: QFrame, event) -> bool:
        tipo = event.type()
        if tipo in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            if event.mimeData().hasText():
                event.acceptProposedAction()
                self._mostrar_indicador_em(linha, event.position().y() > linha.height() / 2)
                return True
            return False
        if tipo == QEvent.Type.DragLeave:
            self._esconder_indicador()
            return True
        if tipo == QEvent.Type.Drop:
            origem_id = event.mimeData().text()
            destino_id = linha.property("animation_id")
            depois = event.position().y() > linha.height() / 2
            self._esconder_indicador()
            self._mover_na_ordem(origem_id, destino_id, depois=depois)
            event.acceptProposedAction()
            return True
        return False

    def _mostrar_indicador_em(self, linha: QFrame, depois: bool) -> None:
        """Linha dourada fina entre os cards, na posição EXATA onde o
        card solto entraria (2026-09-05, pedido do usuário: "ficando
        aquela linha entre os cards onde ele vai ser inserido") - remove
        e reinsere a cada evento (`removeWidget` é no-op seguro se o
        indicador não estiver em nenhuma posição ainda) pra nunca deixar
        DUAS entradas do mesmo widget no layout."""
        self._lista_layout.removeWidget(self._indicador_insercao)
        indice_linha = self._lista_layout.indexOf(linha)
        if indice_linha < 0:
            return
        self._lista_layout.insertWidget(indice_linha + 1 if depois else indice_linha, self._indicador_insercao)
        self._indicador_insercao.show()

    def _esconder_indicador(self) -> None:
        self._lista_layout.removeWidget(self._indicador_insercao)
        self._indicador_insercao.hide()

    def _mover_na_ordem(self, origem_id: str, destino_id: str, *, depois: bool) -> None:
        if origem_id == destino_id or origem_id not in self._ordem or destino_id not in self._ordem:
            return
        self._ordem.remove(origem_id)
        indice_destino = self._ordem.index(destino_id)
        self._ordem.insert(indice_destino + 1 if depois else indice_destino, origem_id)
        self._reconstruir_linhas()
        self._filtrar(self._busca.text())

    # ------------------------------------------------------------------
    # Edição do RASCUNHO (2026-09-04) - nada aqui grava em disco; só
    # `_aplicar` faz isso, de uma vez.
    def _alternar(self, animation_id: str, ativo: bool) -> None:
        if ativo:
            self._selecionadas.add(animation_id)
        else:
            self._selecionadas.discard(animation_id)
        self._label_contagem.setText(self._texto_contagem())

    def _alterar_limite(self, valor: int) -> None:
        self._limite = valor

    def _remover_selecionadas(self) -> None:
        if not self._selecionadas:
            return
        if not confirmar_acao(
            self, "Remover selecionadas",
            f"Remove as {len(self._selecionadas)} ações marcadas da roda (rascunho - só vale de "
            "verdade depois de \"Aplicar\"). Confirma?",
        ):
            return
        self._selecionadas.clear()
        self._reconstruir_linhas()
        self._filtrar(self._busca.text())
        self._label_contagem.setText(self._texto_contagem())

    def _aplicar(self) -> None:
        # Página é sempre DERIVADA da posição em `_ordem` entre as
        # MARCADAS (2026-09-05) - nunca mais um campo editado à parte, o
        # que eliminava a chance de página e ordem de arrasto discordarem.
        selecionadas_em_ordem = [aid for aid in self._ordem if aid in self._selecionadas]
        ordem = [
            {"id": animation_id, "pagina": indice // self._limite + 1}
            for indice, animation_id in enumerate(selecionadas_em_ordem)
        ]
        salvar_configuracao({
            "acoes": ordem,
            "quantidade_maxima": self._limite,
            "imagens": self._imagens,
        })
        self._config = carregar_configuracao()

    def _cancelar(self) -> None:
        self._carregar_do_disco()
        self._spin_limite.blockSignals(True)
        self._spin_limite.setValue(self._limite)
        self._spin_limite.blockSignals(False)
        self._reconstruir_linhas()
        self._filtrar(self._busca.text())
        self._label_contagem.setText(self._texto_contagem())

    def _restaurar_padrao(self) -> None:
        if not confirmar_acao(
            self, "Restaurar padrão",
            "Volta a roda pro padrão de fábrica (todas as ações alcançáveis, "
            "8 por página, sem imagens customizadas) - rascunho, só vale de "
            "verdade depois de \"Aplicar\". Confirma?",
        ):
            return
        self._limite = 8
        self._selecionadas = set(IDS_ESCOLHIVEIS)
        self._ordem = list(IDS_ESCOLHIVEIS)
        self._imagens = {}
        self._spin_limite.blockSignals(True)
        self._spin_limite.setValue(self._limite)
        self._spin_limite.blockSignals(False)
        self._reconstruir_linhas()
        self._filtrar(self._busca.text())
        self._label_contagem.setText(self._texto_contagem())

    def _filtrar(self, texto: str) -> None:
        termos = texto.casefold().strip().split()
        for animation_id, linha in self._linhas.items():
            alvo = f"{animation_id} {rotulo_animacao(animation_id)}".casefold()
            visivel = all(termo in alvo for termo in termos)
            linha.setVisible(visivel)

    def _caminho_imagem(self, animation_id: str) -> Path | None:
        valor = self._imagens.get(animation_id)
        if not isinstance(valor, str) or not valor:
            return None
        caminho = Path(valor)
        return caminho if caminho.is_absolute() else CAMINHO_CONFIG.parents[1] / caminho

    def _atualizar_miniatura(self, animation_id: str) -> None:
        label = self._miniaturas.get(animation_id)
        if label is None:
            return
        caminho = self._caminho_imagem(animation_id)
        pixmap = QPixmap(str(caminho)) if caminho else QPixmap()
        if pixmap.isNull():
            label.setPixmap(QPixmap())
            label.setText("+")
        else:
            label.setText("")
            label.setPixmap(pixmap.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                          Qt.TransformationMode.SmoothTransformation))
        botao_remover = self._botoes_remover_imagem.get(animation_id)
        if botao_remover is not None:
            botao_remover.setEnabled(animation_id in self._imagens)

    def _escolher_imagem(self, animation_id: str) -> None:
        origem, _ = QFileDialog.getOpenFileName(
            self, "Escolher imagem da animação", "", "Imagens (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not origem:
            return
        pixmap = QPixmap(origem)
        if pixmap.isNull():
            return
        PASTA_ICONES.mkdir(parents=True, exist_ok=True)
        nome = re.sub(r"[^a-zA-Z0-9_-]+", "_", animation_id) + ".png"
        destino = PASTA_ICONES / nome
        pixmap.save(str(destino), "PNG")
        self._imagens[animation_id] = destino.relative_to(CAMINHO_CONFIG.parents[1]).as_posix()
        self._atualizar_miniatura(animation_id)

    def _limpar_imagem(self, animation_id: str) -> None:
        if animation_id in self._imagens:
            self._imagens.pop(animation_id)
            self._atualizar_miniatura(animation_id)
