# -*- coding: utf-8 -*-
"""Gesture Wheel adaptativa para as animações contextuais da GAIA.

A âncora nunca é deslocada: no centro da tela a roda é completa; perto de
uma borda ela abre como semicírculo para dentro; num canto, como quadrante.
Isso mantém a GAIA no lugar e todos os alvos dentro da área útil do monitor.
"""
from __future__ import annotations

import itertools
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from mascot import state_catalog
from mascot.animacao_menu import ids_animacoes_validas
from mascot.qt_widgets import criar_lineedit

PASSO_MS = 16
DURACAO_ABERTURA_MS = 150.0
RAIO_INTERNO_MIN = 104.0
ESPESSURA = 76.0
MARGEM_TELA = 22.0
RAIO_BOTAO = 31.0
LARGURA_PLACA = 100.0
ALTURA_PLACA = 22.0
CAMINHO_CONFIG = Path(__file__).resolve().parents[1] / "data" / "gesture_wheel.json"


@dataclass(frozen=True)
class LayoutRoda:
    modo: str
    angulo_inicial: float
    amplitude: float
    capacidade: int


@dataclass(frozen=True)
class ItemRoda:
    id: str
    rotulo: str
    glifo: str
    imagem: QPixmap | None = None


def carregar_configuracao(caminho: Path = CAMINHO_CONFIG) -> dict:
    """Lê a personalização a cada abertura; editar o JSON não exige reinício."""
    padrao = {"quantidade_maxima": 8, "acoes": [], "rotulos": {}, "simbolos": {}, "imagens": {}}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return padrao
    if not isinstance(dados, dict):
        return padrao
    resultado = dict(padrao)
    resultado.update({chave: dados[chave] for chave in padrao if chave in dados})
    return resultado


def salvar_configuracao(alteracoes: dict, caminho: Path = CAMINHO_CONFIG) -> None:
    """Mescla alterações sem apagar a ordem/rótulos personalizados."""
    dados = carregar_configuracao(caminho)
    dados.update(alteracoes)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporario.replace(caminho)


def acoes_configuradas(config: dict) -> list[tuple[str, int]]:
    """Normaliza o formato antigo (lista de ids) e o novo (id + página)."""
    resultado: list[tuple[str, int]] = []
    for item in config.get("acoes", []):
        if isinstance(item, str):
            resultado.append((item, 1))
        elif isinstance(item, dict) and isinstance(item.get("id"), str):
            try:
                pagina = max(1, int(item.get("pagina", 1)))
            except (TypeError, ValueError):
                pagina = 1
            resultado.append((item["id"], pagina))
    return resultado


def calcular_distribuicao(layout: LayoutRoda, quantidade: int, raio_interno: float) -> list[tuple[float, float]]:
    """Retorna (ângulo, raio) garantindo espaço real para medalhão e placa."""
    if quantidade <= 0:
        return []

    # A placa tem 100 px, mas a caixa visual também inclui aro/hover e o
    # texto pode tocar diagonalmente. 22 px de respiro eliminam esse caso.
    passo_minimo = LARGURA_PLACA + 22.0

    def raio_para(pontos: int, amplitude: float, ciclico: bool = False) -> float:
        if pontos <= 1:
            return raio_interno + 48.0
        passo_angular = amplitude / (pontos if ciclico else pontos - 1)
        seno = math.sin(math.radians(passo_angular) / 2.0)
        return passo_minimo / (2.0 * max(0.08, seno))

    inicio, amplitude = layout.angulo_inicial, layout.amplitude
    if layout.modo == "circulo":
        raio = max(raio_interno + 48.0, raio_para(quantidade, 360.0, True))
        return [(inicio + i * 360.0 / quantidade, raio) for i in range(quantidade)]

    if layout.modo == "semicirculo":
        raio = max(raio_interno + 52.0, raio_para(quantidade, amplitude))
        return [(inicio + amplitude * i / max(1, quantidade - 1), raio) for i in range(quantidade)]

    if quantidade <= 4:
        raio = max(raio_interno + 58.0, raio_para(quantidade, amplitude))
        return [(inicio + amplitude * i / max(1, quantidade - 1), raio) for i in range(quantidade)]

    externos = math.ceil(quantidade * 0.6)
    internos = quantidade - externos
    raio_interno_fila = max(raio_interno + 58.0, raio_para(internos, amplitude - 30.0))
    raio_externo_fila = max(raio_interno_fila + 122.0, raio_para(externos, amplitude))
    distribuicao = [
        (inicio + amplitude * i / max(1, externos - 1), raio_externo_fila)
        for i in range(externos)
    ]
    margem = 15.0
    distribuicao.extend(
        (
            inicio + amplitude / 2.0 if internos == 1
            else inicio + margem + (amplitude - 2 * margem) * i / (internos - 1),
            raio_interno_fila,
        )
        for i in range(internos)
    )
    return distribuicao


def calcular_layout_roda(ancora: QPointF, area: QRectF, raio_externo: float) -> LayoutRoda:
    """Escolhe círculo/meia-roda/quadrante sem mover ``ancora``.

    Ângulos usam a convenção visual: 0° aponta à direita e 90° para cima.
    """
    r = raio_externo + MARGEM_TELA
    falta_esquerda = ancora.x() - area.left() < r
    falta_direita = area.right() - ancora.x() < r
    falta_cima = ancora.y() - area.top() < r
    falta_baixo = area.bottom() - ancora.y() < r

    horizontal = falta_esquerda or falta_direita
    vertical = falta_cima or falta_baixo
    if horizontal and vertical:
        abre_direita = falta_esquerda if falta_esquerda != falta_direita else ancora.x() <= area.center().x()
        abre_baixo = falta_cima if falta_cima != falta_baixo else ancora.y() <= area.center().y()
        if abre_direita and abre_baixo:
            inicio = 270.0
        elif abre_direita:
            inicio = 0.0
        elif abre_baixo:
            inicio = 180.0
        else:
            inicio = 90.0
        return LayoutRoda("quadrante", inicio, 90.0, 8)

    if horizontal:
        abre_direita = falta_esquerda if falta_esquerda != falta_direita else ancora.x() <= area.center().x()
        return LayoutRoda("semicirculo", 270.0 if abre_direita else 90.0, 180.0, 8)
    if vertical:
        abre_baixo = falta_cima if falta_cima != falta_baixo else ancora.y() <= area.center().y()
        return LayoutRoda("semicirculo", 180.0 if abre_baixo else 0.0, 180.0, 8)
    return LayoutRoda("circulo", 0.0, 360.0, 8)


# Rótulos que a geração mecânica (abaixo) não acerta - acento (ids são ASCII
# de propósito, nomes de pasta) ou clareza (2026-09-04, usuário: "o q estou
# achando feio é... nome de algumas animacoes"). Só entra aqui quem PRECISA
# de ajuste manual; o resto sai bom o bastante da geração automática.
_ROTULOS_ESPECIAIS = {
    "flutuando_idle": "Flutuando",  # evita o "Idle" em inglês, e não colide com "Flutuar" (verbo, abaixo)
    "flutuando_para_sentada": "Sentar",
    "sentada_para_flutuando": "Flutuar",
    "sentada_balancando-pernas": "Balançando as Pernas",
    "sentada_caindo-no-sono": "Caindo no Sono",
    "sentada_espreguicando": "Espreguiçando",
    "sentada_olhando-ao-redor": "Olhando ao Redor",
    "sentada_rindo_sem-graca": "Rindo Sem Graça",
    "sentada_brincando-cabelo": "Brincando com o Cabelo",
    "sentada_arrumando-cabelo": "Arrumando o Cabelo",
    "sentada_enrolando-cabelo": "Enrolando o Cabelo",
    "sentada_enrolando-cabelo_corando": "Enrolando o Cabelo (Corada)",
    "sentada_jogando-cabelo": "Jogando o Cabelo",
    "sentada_segurando-riso": "Segurando o Riso",
    "sentada_gargalhada_quase-caindo": "Gargalhada (Quase Caindo)",
    "sentada_gargalhada_caindo": "Gargalhada (Caindo)",
    # Direções de voo - "_iniciar" é alcançável direto do idle
    # (`eh_transicao_de_retorno` exclui só isso do EDITOR); mas "_loop" É
    # alcançável de verdade na RODA em runtime, quando ela já está voando
    # naquela direção (`ids_animacoes_validas` filtra pelo estado ATUAL,
    # não só pelo idle) - achado ao vivo 2026-09-04: duas ações no mesmo
    # menu mostrando "Superior Direita" idênticas ("_loop" e "_parar" caindo
    # na geração mecânica, que descarta o sufixo sem reintroduzir a
    # diferença). "_loop" reaproveita o MESMO texto do "_iniciar" da mesma
    # direção (de propósito - pro usuário são a mesma intenção, "voar pra
    # lá", nunca aparecem juntos no mesmo estado); "_parar" de QUALQUER
    # direção vira o mesmo rótulo genérico (parar de voar é sempre a mesma
    # ação, não importa a direção atual).
    "flutuando_direita_iniciar": "Voar Direita",
    "flutuando_direita_loop": "Voar Direita",
    "flutuando_direita_parar": "Parar de Voar",
    "flutuando_esquerda_iniciar": "Voar Esquerda",
    "flutuando_esquerda_loop": "Voar Esquerda",
    "flutuando_esquerda_parar": "Parar de Voar",
    "flutuando_subida_iniciar": "Voar Subida",
    "flutuando_subida_loop": "Voar Subida",
    "flutuando_subida_parar": "Parar de Voar",
    "flutuando_descida_iniciar": "Voar Descida",
    "flutuando_descida_loop": "Voar Descida",
    "flutuando_descida_parar": "Parar de Voar",
    "flutuando_superior-direita_iniciar": "Voar Sup. Direita",
    "flutuando_superior-direita_loop": "Voar Sup. Direita",
    "flutuando_superior-direita_parar": "Parar de Voar",
    "flutuando_superior-esquerda_iniciar": "Voar Sup. Esquerda",
    "flutuando_superior-esquerda_loop": "Voar Sup. Esquerda",
    "flutuando_superior-esquerda_parar": "Parar de Voar",
    "flutuando_inferior-direita_iniciar": "Voar Inf. Direita",
    "flutuando_inferior-direita_loop": "Voar Inf. Direita",
    "flutuando_inferior-direita_parar": "Parar de Voar",
    "flutuando_inferior-esquerda_iniciar": "Voar Inf. Esquerda",
    "flutuando_inferior-esquerda_loop": "Voar Inf. Esquerda",
    "flutuando_inferior-esquerda_parar": "Parar de Voar",
    "flutuando_cortina-abrindo": "Abrindo a Cortina",
    "transformacao_inicio": "Transformação",
    "flutuando_para_substituicao-ninja": "Substituição Ninja",
    "leque-esnobe_para_neutra": "Ficar Neutra",
    "leque_neutra_para_esnobe": "Ficar Esnobe",
}


def rotulo_animacao(animation_id: str) -> str:
    """Rótulo humano curto; o id completo segue disponível no tooltip."""
    if animation_id in _ROTULOS_ESPECIAIS:
        return _ROTULOS_ESPECIAIS[animation_id]
    texto = animation_id
    for prefixo in ("flutuando_para_", "sentada_para_", "leque_", "flutuando_", "sentada_"):
        if texto.startswith(prefixo):
            texto = texto[len(prefixo):]
            break
    texto = texto.removesuffix("_loop").removesuffix("_iniciar").removesuffix("_parar")
    texto = texto.replace("-", " ").replace("_", " ")
    palavras = texto.split()
    resultado = " ".join(palavras).strip().title()
    return resultado[:24] + ("…" if len(resultado) > 24 else "")


# Estados "de repouso" - os únicos de onde a Gesture Wheel realista/normalmente
# é aberta (loop com tag "idle", ver `state_catalog.py`: flutuando/sentada/leque).
ESTADOS_ESTAVEIS = frozenset(
    e.estado_destino for e in state_catalog.CATALOGO.values() if "idle" in e.tags
)


def eh_transicao_de_retorno(animation_id: str) -> bool:
    """True pra metade de VOLTA de uma sequência de 2+ clipes (ex.:
    `trazendo-caos_para_flutuando`, `queda-bunda_para_flutuando`,
    `flutuando_direita_parar`) - só alcançável depois de já estar NO MEIO de
    alguma cena/ação, nunca escolhível como 1º passo a partir de um estado
    de repouso. Usado só pra FILTRAR o editor (`gesture_wheel_editor.py`,
    que lista o catálogo estático inteiro sem contexto de estado atual) -
    a roda em si (`abrir()`, via `ids_animacoes_validas`) já não mostra
    essas transições fora de hora, por já filtrar pelo estado ATUAL de
    verdade (`transicoes_validas_a_partir_de`); esta função generaliza o
    mesmo raciocínio pra quando não existe um estado atual concreto."""
    entrada = state_catalog.CATALOGO.get(animation_id)
    if entrada is None or entrada.estado_origem is None:
        return False
    return entrada.estado_origem not in ESTADOS_ESTAVEIS


def direcao_de_movimento(animation_id: str) -> str | None:
    """Direção ("direita", "subida", etc.) se `animation_id` for uma das 8
    transições de INÍCIO de voo (`flutuando_<direcao>_iniciar`, origem
    "flutuando") - `None` pra qualquer outra animação. Usado por
    `GestureWheel.mousePressEvent` pra rotear o clique pro
    `BehaviorScheduler.forcar_movimento` (desloca de verdade) em vez de só
    `AnimationController.solicitar_transicao` (só troca o clipe - achado
    ao vivo 2026-09-04: "ao fazer movimentos como subida, ela n esta se
    movendo")."""
    entrada = state_catalog.CATALOGO.get(animation_id)
    if entrada is None or entrada.estado_origem != "flutuando" or "movement" not in entrada.tags:
        return None
    return entrada.tags[-1]


def glifo_animacao(animation_id: str) -> str:
    entrada = state_catalog.CATALOGO.get(animation_id)
    tags = set(entrada.tags if entrada else ())
    if "ninja" in tags or "ninja" in animation_id:
        return "NJ"
    if "sitting" in tags or "sentad" in animation_id:
        return "SI"
    if "laugh" in tags or "ris" in animation_id:
        return "HA"
    if "hair" in tags or "cabelo" in animation_id:
        return "FX"
    if "movement" in tags:
        setas = {
            "direita": "→",
            "esquerda": "←",
            "subida": "↑",
            "descida": "↓",
            "superior-direita": "↗",
            "superior-esquerda": "↖",
            "inferior-direita": "↘",
            "inferior-esquerda": "↙",
        }
        for direcao, seta in setas.items():
            if direcao in tags:
                return seta
        return "→"
    partes = rotulo_animacao(animation_id).split()
    return "".join(parte[0] for parte in partes[:2]).upper() or "A"


class GestureWheel(QWidget):
    """Popup radial contextual, desenhado numa janela transparente do monitor."""

    def __init__(self, mascot_window, controller, safety=None, scheduler=None, parent=None):
        super().__init__(parent)
        self._mascot_window = mascot_window
        # Fallback explícito para o raro caso em que o Windows encaminha
        # um evento à janela da personagem mesmo com o overlay por cima.
        mascot_window._gesture_wheel_overlay = self
        self._controller = controller
        self._safety = safety
        # `scheduler` (2026-09-04, achado ao vivo: "ao fazer movimentos
        # como subida, ela n esta se movendo") - só quem faz a Gala
        # REALMENTE andar pela tela é `BehaviorScheduler._iniciar_hop`
        # (Wander/"ir até aqui"); `controller.solicitar_transicao` sozinho
        # só troca o CLIPE. `None` é aceito (ex.: teste isolado de layout)
        # - nesse caso o clique numa direção de voo só troca o clipe, sem
        # crashar, ver `mousePressEvent`.
        self._scheduler = scheduler
        self._aberta = False
        self._hover = -1
        self._itens_todos: list[ItemRoda] = []
        self._itens_visiveis: list[ItemRoda] = []
        self._paginas: list[list[ItemRoda]] = []
        self._indice_pagina = 0
        self._distribuicao: list[tuple[float, float]] = []
        self._layout = LayoutRoda("circulo", 0.0, 360.0, 8)
        self._centro = QPointF()
        self._raio_interno = RAIO_INTERNO_MIN
        self._raio_externo = RAIO_INTERNO_MIN + ESPESSURA
        self._progresso = 0.0
        self._inicio = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animar)
        # Filtro por texto (2026-09-06, pedido do usuário: "qnd mouse tiver
        # na gaia ou em alguma animacao, apertar ctrl+f filtraria essas
        # animações") - `_limite` guardado aqui (antes só variável local de
        # `abrir`) porque o filtro precisa repaginar depois de reduzir a
        # lista, com o MESMO máximo por página.
        self._limite = 8
        self._campo_filtro = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

    @property
    def esta_aberta(self) -> bool:
        return self._aberta

    @property
    def layout_atual(self) -> LayoutRoda:
        return self._layout

    def abrir(self) -> bool:
        # 2026-09-05 - a roda deixou de se limitar às transições
        # alcançáveis do estado ATUAL (pedido do usuário: "o proposito
        # dessa tela é listar todas as animacoes q posso ativar, porem n
        # se limitar as opcoes do estado atual, eu posso querer q ela
        # faça a transformação msm estando sentada") - mostra TODAS as
        # configuradas que ainda existem no catálogo; a preparação pra
        # chegar no estado exigido por cada uma acontece só na hora do
        # clique (`mousePressEvent`, `AnimationController.
        # solicitar_transicao_com_preparo`). Continua excluindo
        # `IDS_OCULTOS_DE_SELECAO` por tabela (defesa extra - o editor já
        # nem deixa selecionar as duas).
        config = carregar_configuracao()
        try:
            limite = max(1, min(8, int(config.get("quantidade_maxima", 8))))
        except (TypeError, ValueError):
            limite = 8
        self._limite = limite
        configuradas = acoes_configuradas(config)
        if configuradas:
            por_pagina: dict[int, list[str]] = {}
            for animation_id, pagina in configuradas:
                if animation_id in state_catalog.CATALOGO and animation_id not in state_catalog.IDS_OCULTOS_DE_SELECAO:
                    por_pagina.setdefault(pagina, []).append(animation_id)
            grupos_ids = []
            for pagina in sorted(por_pagina):
                grupo = por_pagina[pagina]
                grupos_ids.extend(grupo[i:i + limite] for i in range(0, len(grupo), limite))
        else:
            # bootstrap raro (antes de qualquer "Aplicar" no editor) - aqui
            # sim vale restringir ao estado atual, só pra não abrir uma
            # roda gigante com o catálogo inteiro na 1ª vez.
            ids = ids_animacoes_validas(self._controller)
            grupos_ids = [ids[i:i + limite] for i in range(0, len(ids), limite)]
        grupos_ids = [grupo for grupo in grupos_ids if grupo]
        if not grupos_ids:
            return False
        rotulos = config.get("rotulos") if isinstance(config.get("rotulos"), dict) else {}
        simbolos = config.get("simbolos") if isinstance(config.get("simbolos"), dict) else {}
        imagens = config.get("imagens") if isinstance(config.get("imagens"), dict) else {}

        def criar_item(i: str, posicao: int) -> ItemRoda:
            pixmap = QPixmap()
            caminho = imagens.get(i)
            if isinstance(caminho, str) and caminho:
                caminho_imagem = Path(caminho)
                if not caminho_imagem.is_absolute():
                    caminho_imagem = CAMINHO_CONFIG.parents[1] / caminho_imagem
                pixmap.load(str(caminho_imagem))
            # Número da posição concatenado no início (2026-09-06, pedido do
            # usuário, print da roda de verdade) - "X - Animação". Contagem
            # ÚNICA de 1 até o total de animações ativas, NUNCA reiniciando
            # a cada página ("n quero q seja varios de 1~max por pagina,
            # tem q ser uma unica contagem de 1~todas animacoes ativas") -
            # 1ª tentativa reiniciava por página, corrigida no mesmo dia.
            rotulo_base = str(rotulos.get(i) or rotulo_animacao(i))
            return ItemRoda(
                i,
                f"{posicao} - {rotulo_base}",
                str(simbolos.get(i) or glifo_animacao(i)),
                pixmap if not pixmap.isNull() else None,
            )

        contador_posicao = itertools.count(1)
        self._paginas = [
            [criar_item(i, next(contador_posicao)) for i in grupo]
            for grupo in grupos_ids
        ]
        self._indice_pagina = 0
        self._itens_todos = [item for pagina in self._paginas for item in pagina]
        self._configurar_geometria()
        self._montar_itens()
        self._hover = -1
        self._progresso = 0.0
        self._inicio = time.monotonic()
        self._aberta = True
        if self._safety is not None:
            self._safety.bloquear_autonomia("gesture_wheel")
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.PopupFocusReason)
        self._timer.start(PASSO_MS)
        return True

    def fechar(self) -> None:
        if not self._aberta:
            return
        self._aberta = False
        self._timer.stop()
        self.hide()
        self._hover = -1
        if self._campo_filtro is not None:
            self._campo_filtro.hide()
            self._campo_filtro.clear()
        if self._safety is not None:
            self._safety.liberar_autonomia("gesture_wheel")

    def _configurar_geometria(self) -> None:
        janela = self._mascot_window
        tela = janela.screen() or QApplication.primaryScreen()
        area = tela.availableGeometry()
        asset = getattr(janela, "asset_atual", None)
        escala = getattr(janela, "escala", 1.0)
        if asset is not None:
            esquerda = janela.x() + asset.margem_esquerda_vazia_px * escala
            direita = janela.x() + janela.width() - asset.margem_direita_vazia_px * escala
            topo = janela.y() + asset.margem_superior_vazia_px * escala
            base = janela.y() + janela.height() - asset.margem_inferior_vazia_px * escala
            ancora_global = QPointF((esquerda + direita) / 2.0, (topo + base) / 2.0)
            meia_silhueta = max((direita - esquerda) / 2.0, (base - topo) / 2.0)
            self._raio_interno = max(RAIO_INTERNO_MIN, min(154.0, meia_silhueta + 12.0))
        else:
            ancora_global = QPointF(janela.x() + janela.width() / 2.0, janela.y() + janela.height() / 2.0)
            self._raio_interno = RAIO_INTERNO_MIN
        self._raio_externo = self._raio_interno + ESPESSURA
        self._layout = calcular_layout_roda(ancora_global, QRectF(area), self._raio_externo)
        self.setGeometry(area)
        self._centro = ancora_global - QPointF(area.x(), area.y())

    def _montar_itens(self) -> None:
        self._itens_visiveis = list(self._paginas[self._indice_pagina])
        self._distribuicao = calcular_distribuicao(
            self._layout, len(self._itens_visiveis), self._raio_interno
        )

    def _animar(self) -> None:
        self._progresso = min(1.0, (time.monotonic() - self._inicio) * 1000.0 / DURACAO_ABERTURA_MS)
        self.update()
        if self._progresso >= 1.0:
            self._timer.stop()

    def _angulo_item(self, indice: int) -> float:
        return self._distribuicao[indice][0]

    def _centro_item(self, indice: int, expandir: float = 0.0) -> QPointF:
        escala = 0.62 + 0.38 * (1.0 - (1.0 - self._progresso) ** 3)
        raio_base = self._distribuicao[indice][1]
        raio = (raio_base + expandir) * escala
        rad = math.radians(self._angulo_item(indice))
        return self._centro + QPointF(raio * math.cos(rad), -raio * math.sin(rad))

    def _indice_em(self, pos: QPointF) -> int:
        for indice in range(len(self._itens_visiveis)):
            centro = self._centro_item(indice, 5.0 if indice == self._hover else 0.0)
            if math.hypot(pos.x() - centro.x(), pos.y() - centro.y()) <= RAIO_BOTAO + 5.0:
                return indice
        return -1

    def _sobre_gaia_ou_animacao(self, pos: QPointF) -> bool:
        """`pos` em coordenadas LOCAIS deste widget (mesma referência de
        `_indice_em`/`_centro`) - usado só pra decidir se Ctrl+F deveria
        abrir o filtro (2026-09-06: "qnd mouse tiver na gaia ou em alguma
        animacao, apertar ctrl+f filtraria essas animações"), não pra
        clique/hover normal."""
        if self._indice_em(pos) >= 0:
            return True
        return math.hypot(pos.x() - self._centro.x(), pos.y() - self._centro.y()) <= self._raio_interno

    def mouseMoveEvent(self, event) -> None:
        novo = self._indice_em(event.position())
        if novo != self._hover:
            self._hover = novo
            self.setCursor(Qt.CursorShape.PointingHandCursor if novo >= 0 else Qt.CursorShape.ArrowCursor)
            self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.fechar()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        indice = self._indice_em(event.position())
        if indice < 0:
            self.fechar()
            return
        item = self._itens_visiveis[indice]
        self._executar_item(item.id)
        self.fechar()

    def _executar_item(self, animation_id: str) -> None:
        """"flutuando_para_sentada" -> vai até a barra primeiro
        (`BehaviorScheduler.forcar_sentar`, achado ao vivo 2026-09-05: "qnd
        eu mando ela sentar, ela tem q ir ate a barra antes de realizar a
        animação direto onde esta" - antes ia direto pro
        `solicitar_transicao`, sentando no ar onde ela estivesse). Direção
        de voo -> desloca de verdade (`forcar_movimento`, mesmo par
        animação+física do Wander). As duas passam por
        `AnimationController.preparar_para` primeiro se ela não estiver em
        "flutuando" - a roda lista TODAS as ações configuradas, não só as
        do estado atual (2026-09-05: "n se limitar as opcoes do estado
        atual"), então clicar "sentar"/mover estando sentada, por exemplo,
        precisa levantar sozinha primeiro. Qualquer outra ação ->
        `solicitar_transicao_com_preparo` (mesma preparação, genérica).

        Sem `scheduler` (`None`, ex.: teste isolado) ou sem caminho até
        "flutuando", cai pro `solicitar_transicao_com_preparo` puro - troca
        o clipe mesmo sem a jornada especial, melhor que não fazer nada."""
        if animation_id == "flutuando_para_sentada" and self._scheduler is not None:
            if self._controller.preparar_para("flutuando", self._scheduler.forcar_sentar):
                return
            self._controller.solicitar_transicao_com_preparo(animation_id)
            return

        direcao = direcao_de_movimento(animation_id)
        if direcao is not None and self._scheduler is not None:
            def _mover() -> None:
                # `forcar_movimento` devolve `False` só se o scheduler já
                # estiver ocupado/sem espaço real pra avançar nessa direção -
                # cai pro `solicitar_transicao` puro (troca o clipe mesmo
                # sem deslocar, melhor que não fazer nada).
                if not self._scheduler.forcar_movimento(direcao):
                    self._controller.solicitar_transicao(animation_id)

            if self._controller.preparar_para("flutuando", _mover):
                return

        self._controller.solicitar_transicao_com_preparo(animation_id)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self._campo_filtro is not None and self._campo_filtro.isVisible():
                self._esconder_campo_filtro()
                return
            self.fechar()
            return
        if (
            event.key() == Qt.Key.Key_F
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and self._sobre_gaia_ou_animacao(self.mapFromGlobal(QCursor.pos()))
        ):
            self._mostrar_campo_filtro()
            return
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_PageDown):
            self._trocar_pagina(1)
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
            self._trocar_pagina(-1)
            return
        super().keyPressEvent(event)

    def _mostrar_campo_filtro(self) -> None:
        """Ctrl+F com o mouse sobre a Gaia ou uma animação (2026-09-06,
        pedido do usuário) - filtra `_itens_todos` por texto, repaginando
        com o MESMO `_limite`. Campo único, reaproveitado (mesmo padrão do
        indicador de arraste do editor - nunca recriado à toa)."""
        if self._campo_filtro is None:
            campo = criar_lineedit()
            campo.setParent(self)
            campo.setPlaceholderText("Filtrar…")
            campo.textChanged.connect(self._ao_filtro_mudar)
            self._campo_filtro = campo
        largura = 180
        self._campo_filtro.setFixedWidth(largura)
        self._campo_filtro.move(
            int(self._centro.x() - largura / 2),
            max(4, int(self._centro.y() - self._raio_externo - 44)),
        )
        self._campo_filtro.show()
        self._campo_filtro.raise_()
        self._campo_filtro.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._campo_filtro.selectAll()

    def _esconder_campo_filtro(self) -> None:
        if self._campo_filtro is not None:
            self._campo_filtro.hide()
            self._campo_filtro.clear()  # dispara _ao_filtro_mudar("") - some o filtro sozinho
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _ao_filtro_mudar(self, texto: str) -> None:
        termos = texto.casefold().strip().split()
        if termos:
            filtrados = [
                item for item in self._itens_todos
                if all(termo in f"{item.id} {item.rotulo}".casefold() for termo in termos)
            ]
        else:
            filtrados = list(self._itens_todos)
        limite = max(1, self._limite)
        self._paginas = [filtrados[i:i + limite] for i in range(0, len(filtrados), limite)] or [[]]
        self._indice_pagina = 0
        self._hover = -1
        self._montar_itens()
        self.update()

    def wheelEvent(self, event) -> None:
        if len(self._paginas) > 1 and event.angleDelta().y():
            self._trocar_pagina(-1 if event.angleDelta().y() > 0 else 1)
        event.accept()

    def trocar_pagina(self, delta: int) -> None:
        if len(self._paginas) <= 1:
            return
        self._indice_pagina = (self._indice_pagina + delta) % len(self._paginas)
        self._hover = -1
        self._montar_itens()
        self.update()

    _trocar_pagina = trocar_pagina

    def focusOutEvent(self, event) -> None:
        # Também cobre clique em outro monitor, fora da janela transparente
        # que ocupa somente o monitor atual. EXCETO (2026-09-06) quando o
        # foco só se moveu pro campo de filtro (widget FILHO, `setFocus`
        # em `_mostrar_campo_filtro`) - isso fecharia a roda bem na hora de
        # abrir o campo, sem o usuário ter feito nada pra fechar de verdade.
        novo_foco = QApplication.focusWidget()
        if novo_foco is not None and self.isAncestorOf(novo_foco):
            super().focusOutEvent(event)
            return
        self.fechar()
        super().focusOutEvent(event)

    def paintEvent(self, _event) -> None:
        if not self._itens_visiveis:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(self._progresso)
        for indice, item in enumerate(self._itens_visiveis):
            hover = indice == self._hover
            centro = self._centro_item(indice, 6.0 if hover else 0.0)
            raio = RAIO_BOTAO + (3.0 if hover else 0.0)

            # Medalhão circular independente + aro duplo, seguido de uma
            # placa curta de comando, em vez de setores de uma pizza.
            painter.setPen(QPen(QColor(3, 7, 10, 235), 5.0))
            painter.setBrush(QColor(20, 31, 39, 238))
            painter.drawEllipse(centro, raio, raio)
            painter.setPen(QPen(QColor("#E8C878") if hover else QColor("#78DDF4"), 2.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(centro, raio - 3.5, raio - 3.5)

            conteudo = QRectF(centro.x() - raio + 6, centro.y() - raio + 6, (raio - 6) * 2, (raio - 6) * 2)
            if item.imagem is not None:
                painter.save()
                recorte = QPainterPath()
                recorte.addEllipse(conteudo)
                painter.setClipPath(recorte)
                origem = item.imagem.rect()
                lado = min(origem.width(), origem.height())
                origem = QRectF(
                    origem.center().x() - lado / 2, origem.center().y() - lado / 2, lado, lado
                )
                painter.drawPixmap(conteudo, item.imagem, origem)
                painter.restore()
            else:
                fonte_glifo = QFont(painter.font())
                fonte_glifo.setPointSize(14)
                fonte_glifo.setWeight(QFont.Weight.Bold)
                painter.setFont(fonte_glifo)
                painter.setPen(QColor("#FFF1BD") if hover else QColor("#EAF8FF"))
                painter.drawText(conteudo, Qt.AlignmentFlag.AlignCenter, item.glifo)

            placa = QRectF(
                centro.x() - LARGURA_PLACA / 2.0,
                centro.y() + raio - 2.0,
                LARGURA_PLACA,
                ALTURA_PLACA,
            )
            painter.setPen(QPen(QColor("#E8C878") if hover else QColor(5, 9, 13), 1.5))
            painter.setBrush(QColor(10, 17, 23, 242))
            painter.drawRoundedRect(placa, 3.0, 3.0)
            painter.setPen(QColor("#FFF1BD") if hover else QColor("#F0F5F7"))
            fonte_rotulo = QFont(painter.font())
            fonte_rotulo.setPointSize(7)
            fonte_rotulo.setWeight(QFont.Weight.DemiBold)
            painter.setFont(fonte_rotulo)
            painter.drawText(placa.adjusted(4, 1, -4, -1), Qt.AlignmentFlag.AlignCenter, item.rotulo)
        if len(self._paginas) > 1:
            texto_pagina = f"Página {self._indice_pagina + 1}/{len(self._paginas)}  ·  role para trocar"
            fonte = QFont(painter.font())
            fonte.setPointSize(8)
            painter.setFont(fonte)
            fm = painter.fontMetrics()
            largura = fm.horizontalAdvance(texto_pagina) + 24
            placa = QRectF(self.width() / 2 - largura / 2, 12, largura, 26)
            painter.setPen(QPen(QColor("#78DDF4"), 1.2))
            painter.setBrush(QColor(10, 17, 23, 228))
            painter.drawRoundedRect(placa, 13, 13)
            painter.setPen(QColor("#F0F5F7"))
            painter.drawText(placa, Qt.AlignmentFlag.AlignCenter, texto_pagina)
        painter.end()
