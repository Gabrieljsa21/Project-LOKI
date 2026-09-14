# -*- coding: utf-8 -*-
"""MascotWindow (plano, seção 6.2/9.1) - janela transparente, sempre no
topo, sem borda, fora da barra de tarefas, que mostra o quadro atual do
`AnimationController`. Só desenha e reage a mouse/posição - estado e
ciclo de vida da animação ficam inteiramente no controller (seção 7.2:
"behavior pede uma intenção ao controller, não troca textura diretamente").

Posição persistida por quantidade de monitores, mesmo padrão já validado
em `features/avatar_overlay/vtuber_overlay.py` (`_carregar_posicao_salva`/
`_salvar_posicao_atual`) - arquivo próprio (`data/mascot_posicao.json`)
pra não colidir com o overlay antigo enquanto os dois convivem (plano,
seção 1.7: Live2D continua como rollback até o cutover da Fase 8).
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QWidget

from mascot import chaos_flight, config, platform_windows, state_catalog
from mascot.animation_controller import AnimationController
from mascot.halo import Halo
from mascot.physics import MovimentoAmortecido, MovimentoComDuracaoFixa, MovimentoQuedaGravidade

CAMINHO_POSICAO = Path(__file__).resolve().parents[1] / "data" / "mascot_posicao.json"

# reações de "sendo carregada" (loop enquanto "agarrada") - o catálogo só
# declara UM fallback fixo pra "flutuando_para_agarrada" (sempre
# "arrastada_loop_calma"); sorteada na hora que ela entra em "agarrada"
# (ver `MascotWindow._ao_estado_alterado`) - pedido do usuário,
# 2026-08-29: "ela sempre ta fazendo a mesma animação ao ser carregada,
# deveria variar".
ARRASTADA_LOOPS = (
    "arrastada_loop_calma",
    "arrastada_loop_brava",
    "arrastada_loop_chorando-medo",
    "arrastada_loop_furiosa",
    "arrastada_loop_panico-1",
    "arrastada_loop_panico-2",
    "arrastada_loop_emburrada",
)

# MESMO padrão de ARRASTADA_LOOPS acima, achado 2026-09-06 investigando
# "o ficar esnobe parece q esta sem o final tbm" - `flutuando_para_leque`
# também só declara UM fallback fixo (`null` no catálogo, tratado então
# como "pose terminal"), mas ao contrário do que o CHANGELOG registrou
# antes (2026-09-04, "é INTENCIONAL... não sofre do mesmo bug"), NUNCA
# existiu nenhum código escolhendo um dos 3 loops - ela ficava mesmo
# travada no último quadro de `flutuando_para_leque`, sem entrar em
# nenhum loop de humor, até o usuário clicar manualmente "Ficar Esnobe"/
# "Ficar Neutra" pela bandeja. Sorteada aqui na hora que ela entra em
# "leque" (ver `MascotWindow._ao_estado_alterado`), mesma lógica.
LEQUE_LOOPS = (
    "leque_ironica_loop",
    "leque_esnobe_loop",
    "leque_sorriso_loop",
)


def _carregar_posicao_salva(monitores: int) -> dict | None:
    if not CAMINHO_POSICAO.is_file():
        return None
    try:
        todas = json.loads(CAMINHO_POSICAO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for contagem in range(monitores, 0, -1):
        if str(contagem) in todas:
            return todas[str(contagem)]
    return None


def _salvar_posicao_atual(monitores: int, x: int, y: int) -> None:
    todas = {}
    if CAMINHO_POSICAO.is_file():
        try:
            todas = json.loads(CAMINHO_POSICAO.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            todas = {}
    todas[str(monitores)] = {"x": x, "y": y}
    CAMINHO_POSICAO.parent.mkdir(parents=True, exist_ok=True)
    CAMINHO_POSICAO.write_text(json.dumps(todas, ensure_ascii=False, indent=2), encoding="utf-8")


class MascotWindow(QWidget):
    clicada = Signal()
    # avisos pro BehaviorScheduler (via process_main.py) cancelar/retomar
    # física e perseguição autônoma durante um arraste real - pedido do
    # usuário, 2026-08-29: "quando eu segurar ela, tem de interromper na
    # hora a animação atual".
    arraste_iniciado = Signal()
    arraste_finalizado = Signal()
    # Menu SAO (2026-09-02, `GAIA_MENU_SAO.md`) - gesto CONFIRMADO (já passou
    # do limiar de acúmulo, ver `wheelEvent`), nunca o delta bruto do evento.
    # Quem decide o que fazer com isso é `MascotApp` (process_main.py), essa
    # janela só detecta o gesto - mesma separação já usada em `clicada`.
    scroll_baixo_confirmado = Signal()
    scroll_cima_confirmado = Signal()

    _LIMIAR_SCROLL = 120  # 1 "clique" de roda tradicional (Qt: angleDelta().y() em múltiplos de 120)
    _RESET_SCROLL_OCIOSO_S = 0.3  # doc: "reset do acumulador após um curto período sem eventos" (evita ativação em trackpad por deltas pequenos contínuos)

    def __init__(self, controller: AnimationController, escala: float = 1.0):
        super().__init__()
        self._controller = controller
        self._escala = max(0.2, min(3.0, escala))
        self._arrastando = False
        self._offset_arraste = QPoint()
        self._posicao_ao_pressionar = QPoint()
        self._fluxo_arraste_ativo = False
        self._arraste_pendente_finalizacao = False
        self._reacao_arraste_definida = False
        # Sem reset em lugar nenhum ainda (2026-09-06) - `leque` não tem
        # NENHUMA transição de volta pra "flutuando" hoje (só as 3
        # variações de humor entre si), então "flutuando_para_leque" só é
        # alcançável 1x por processo mesmo; quando um dia existir um
        # "leque_para_flutuando", resetar este flag junto dele.
        self._reacao_leque_definida = False
        self._click_through = False
        self._acumulador_scroll = 0.0
        self._ultimo_scroll_s = 0.0
        self._queda = MovimentoAmortecido(rigidez=90.0, amortecimento=14.0, parent=self)
        self._queda_arraste = MovimentoQuedaGravidade(parent=self)
        self._pouso_heroico_pendente = False
        self._halo = Halo()

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        # 🔥 CORRIGIDO (2026-09-07, achado ao vivo: janela "Galateia" surgiu
        # em branco/travada depois de reiniciar) - `aplicar_protecao_captura`
        # chama `widget.winId()`, que força a criação IMEDIATA do HWND
        # nativo. Chamado aqui (no meio do `__init__`, ANTES de `resize`/
        # layout/conteúdo) força esse HWND a existir sem geometria/conteúdo
        # nenhum ainda - o mesmo tipo de problema de timing Qt/Windows já
        # visto em `bubble.py::_BolhaBase.entrar` (`raise_()` precisou do
        # mesmo adiamento). `QTimer.singleShot(0, ...)` adia a chamada pro
        # próximo tick do event loop, depois que o construtor inteiro (e o
        # primeiro `show()`) já terminou de rodar.
        QTimer.singleShot(0, lambda: platform_windows.aplicar_protecao_captura(
            self, bool(config.carregar_config_mascot().get("proteger_de_captura")),
        ))

        asset = controller.quadro_atual
        largura = int((asset.width() if asset else 384) * self._escala)
        altura = int((asset.height() if asset else 338) * self._escala)
        self.resize(largura, altura)
        self._pivot_renderizado = controller.pivot_atual or (largura // 2, altura)

        controller.quadro_alterado.connect(self._ao_quadro_alterado)
        controller.estado_alterado.connect(self._ao_estado_alterado)
        controller.clipe_concluido.connect(self._ao_clipe_concluido)
        self._voo_caos_atual: chaos_flight.ChaosFlightWindow | None = None
        self._aplicar_posicao_inicial()

    def _ao_quadro_alterado(self) -> None:
        """Redimensiona cenas amplas mantendo o ponto da personagem parado.

        O sprite normal e uma cena podem ter células diferentes, mas ambos
        declaram o mesmo ponto de ancoragem visual no manifesto.
        """
        frame = self._controller.quadro_atual
        if frame is None:
            return
        novo_tamanho = (int(frame.width() * self._escala), int(frame.height() * self._escala))
        novo_pivot_bruto = self._controller.pivot_atual or (frame.width() // 2, frame.height())
        novo_pivot = (
            int(novo_pivot_bruto[0] * self._escala), int(novo_pivot_bruto[1] * self._escala)
        )
        pivot_antigo = (
            int(self._pivot_renderizado[0] * self._escala),
            int(self._pivot_renderizado[1] * self._escala),
        )
        if (self.width(), self.height()) != novo_tamanho or self._pivot_renderizado != novo_pivot_bruto:
            ancora_global = self.pos() + QPoint(*pivot_antigo)
            self.resize(*novo_tamanho)
            self.move(ancora_global - QPoint(*novo_pivot))
            self._pivot_renderizado = novo_pivot_bruto
        self.update()

    def _aplicar_posicao_inicial(self) -> None:
        monitores = len(QApplication.screens())
        salvo = _carregar_posicao_salva(monitores)
        if salvo:
            self.move(salvo["x"], salvo["y"])
            return
        tela = QApplication.primaryScreen().availableGeometry()
        self.move(tela.right() - self.width() - 40, tela.bottom() - self.height() - 40)

    def salvar_posicao_atual(self) -> None:
        _salvar_posicao_atual(len(QApplication.screens()), self.x(), self.y())

    def definir_click_through(self, ativo: bool) -> None:
        """Alternar `WindowTransparentForInput` exige recriar a superfície
        nativa - `setWindowFlag` só some/aparece de novo depois de um
        `show()` (confirmado no spike: sem isso a flag fica setada mas o
        SO ainda entrega eventos de mouse pra janela)."""
        self._click_through = ativo
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, ativo)
        self.show()

    @property
    def click_through_ativo(self) -> bool:
        return self._click_through

    @property
    def escala(self) -> float:
        return self._escala

    @property
    def asset_atual(self):
        """Passthrough pro asset tocando agora (2026-09-02, Menu SAO) -
        quem precisa da margem lateral vazia (`AnimationAsset.margem_
        esquerda_vazia_px`/`margem_direita_vazia_px`) pra ancorar perto da
        silhueta de verdade, não da célula/canvas inteiro, sem alcançar
        `_controller` de fora."""
        return self._controller.asset_atual

    def definir_halo_modo_voz(self, modo: str | None) -> None:
        """Ponte pro `Halo` (Fase 5, redesenhado 2026-09-02 - ver docstring
        de `mascot/halo.py`) - chamado por `MascotApp._processar_
        evento_gaia` a cada `voice_mode_changed` vindo da GAIA. Só repinta
        se o halo estiver ativo OU tiver acabado de desligar (evita
        `update()` à toa quando não há halo nenhum pra mostrar)."""
        estava_ativo = self._halo.ativo
        self._halo.definir_modo_voz(modo)
        if estava_ativo or self._halo.ativo:
            self.update()

    def paintEvent(self, event) -> None:
        frame = self._controller.quadro_atual
        if frame is None:
            return
        painter = QPainter(self)
        if self._escala != 1.0:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if self._halo.ativo:
            centro, raio_base = self._geometria_halo()
            self._halo.pintar(painter, centro, raio_base)
        painter.drawPixmap(self.rect(), frame)

    def _geometria_halo(self) -> tuple[QPointF, float]:
        """Centro/raio do halo baseados na silhueta VISÍVEL do asset atual
        (`AnimationAsset.margem_*_vazia_px`), não no canvas/célula inteiro
        - achado ao vivo (2026-09-02, "o halo n ta centralizado na gaia") -
        a célula reserva a mesma margem/pivô pra TODO clipe nunca saltar
        entre eles (seção 3.1 do plano), mas isso deixa espaço vazio ao
        redor dela que não devia contar pro centro nem pro tamanho do
        halo (também deixava o halo maior/mais deslocado do que devia)."""
        asset = self._controller.asset_atual
        if asset is None:
            return QPointF(self.rect().center()), min(self.width(), self.height()) * 0.42
        esq = asset.margem_esquerda_vazia_px * self._escala
        dir_ = asset.margem_direita_vazia_px * self._escala
        sup = asset.margem_superior_vazia_px * self._escala
        inf = asset.margem_inferior_vazia_px * self._escala
        largura_visivel = max(1.0, self.width() - esq - dir_)
        altura_visivel = max(1.0, self.height() - sup - inf)
        centro = QPointF(esq + largura_visivel / 2, sup + altura_visivel / 2)
        raio_base = min(largura_visivel, altura_visivel) * 0.42
        return centro, raio_base

    _LIMIAR_ARRASTE_PX = 4  # abaixo disso, é clique; acima, foi arraste de verdade

    def _em_substituicao_ninja(self) -> bool:
        """Só a cena da Substituição Ninja bloqueia arraste bruto de mouse
        - pedido do usuário, 2026-09-02: "apenas a animação de substituição
        ninja q tem de impedir de ser agarrada ou trocar animação para
        agarrada, pq essa é a brincadeira por trás dela. O resto pode
        normalmente" (correção de uma 1ª tentativa que bloqueava QUALQUER
        cena não-interrompível, ampla demais - "trazendo o caos" e as
        outras continuam podendo ser interrompidas por um arraste normal,
        só a Ninja não). Reconhece as duas cenas encadeadas pela tag
        `"ninja"` do catálogo (`AnimationController.tags_atuais`), não uma
        lista de ids amarrada à mão."""
        return "ninja" in self._controller.tags_atuais

    def mousePressEvent(self, event) -> None:
        roda = getattr(self, "_gesture_wheel_overlay", None)
        if roda is not None and roda.esta_aberta:
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and not self._em_substituicao_ninja():
            self._arrastando = True
            self._offset_arraste = event.globalPosition().toPoint() - self.pos()
            self._posicao_ao_pressionar = self.pos()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        roda = getattr(self, "_gesture_wheel_overlay", None)
        if roda is not None and roda.esta_aberta:
            self._arrastando = False
            event.accept()
            return
        if self._arrastando and self._em_substituicao_ninja():
            # a própria Substituição Ninja nasce de um arraste em
            # andamento - solta o arraste NA HORA, em vez de continuar
            # movendo a janela por baixo da cutscene (achado ao vivo,
            # 2026-09-02: "durante toda a animação da substituição ninja,
            # gaia não pode ser arrastada ou movida").
            self._arrastando = False
            return
        if self._arrastando:
            self.move(event.globalPosition().toPoint() - self._offset_arraste)
            deslocamento = self.pos() - self._posicao_ao_pressionar
            passou_limiar = (
                abs(deslocamento.x()) > self._LIMIAR_ARRASTE_PX
                or abs(deslocamento.y()) > self._LIMIAR_ARRASTE_PX
            )
            if passou_limiar and not self._fluxo_arraste_ativo:
                self._iniciar_fluxo_animado_arraste()
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._arrastando:
            self._arrastando = False
            deslocamento = self.pos() - self._posicao_ao_pressionar
            if abs(deslocamento.x()) > self._LIMIAR_ARRASTE_PX or abs(deslocamento.y()) > self._LIMIAR_ARRASTE_PX:
                self._finalizar_fluxo_animado_arraste()
                self._acomodar_apos_arraste()
            else:
                self.clicada.emit()
            event.accept()

    def wheelEvent(self, event) -> None:
        """Menu SAO (`GAIA_MENU_SAO.md`, "Tratamento do scroll") - acumula
        `angleDelta().y()` até cruzar o limiar de uma rolagem "de verdade",
        em vez de reagir ao 1º delta bruto (doc: "não é recomendado abrir o
        menu apenas verificando `wheelDelta < 0`"). Convenção do Qt:
        `angleDelta().y()` NEGATIVO = roda girando pra baixo/em direção ao
        usuário (gesto físico de "scroll para baixo" do doc); POSITIVO =
        pra cima. Ignorado durante arraste real (`_arrastando`) - os dois
        gestos não deveriam se misturar."""
        roda = getattr(self, "_gesture_wheel_overlay", None)
        if roda is not None and roda.esta_aberta:
            delta = event.angleDelta().y()
            if delta:
                roda.trocar_pagina(-1 if delta > 0 else 1)
            event.accept()
            return
        if self._arrastando:
            event.ignore()
            return
        agora = time.monotonic()
        if agora - self._ultimo_scroll_s > self._RESET_SCROLL_OCIOSO_S:
            self._acumulador_scroll = 0.0
        self._ultimo_scroll_s = agora
        self._acumulador_scroll += event.angleDelta().y()
        if self._acumulador_scroll <= -self._LIMIAR_SCROLL:
            self._acumulador_scroll = 0.0
            self.scroll_baixo_confirmado.emit()
        elif self._acumulador_scroll >= self._LIMIAR_SCROLL:
            self._acumulador_scroll = 0.0
            self.scroll_cima_confirmado.emit()
        event.accept()

    # pausa parada antes de começar a cair de verdade (pedido do usuário,
    # 2026-08-29: "ela pode ficar no local por 1s, e só então começar a
    # cair... é assim que funciona gravidade") - a duração TOTAL volta a
    # ser a duração natural do clipe (~4s, sem tocar mais devagar); só o
    # DESLOCAMENTO físico ganha essa pausa + aceleração contínua depois
    # dela (ver `MovimentoQuedaGravidade`).
    PAUSA_QUEDA_MS = 1000.0

    # Queda heroica (2026-09-05, pedido do usuário: "ajustar o tempo de
    # queda... p tentar controlar velocidade" + trocar pra próxima
    # animação assim que ela estiver quase chegando embaixo, não num
    # tempo fixo) - duração da queda passou a ser PROPORCIONAL à
    # distância real até o piso (queda livre: distância = ½·a·t²), em
    # vez de sempre igual à duração fixa do clipe `agarrada_para_queda-
    # heroica` (~4s, não importava se a distância era de 100px ou
    # 1000px). Constantes ajustáveis por enquanto sem validação ao vivo
    # de altura variada - ver `_disparar_queda_heroica`.
    ACELERACAO_QUEDA_HEROICA_PXS2 = 140.0
    MARGEM_QUASE_CHAO_HEROICA_PX = 120.0

    # Substituição ninja (2026-09-02, pedido do usuário) - reação RARA
    # alternativa a ser agarrada quando o arraste começa a partir do idle
    # flutuando: em vez do agarrar normal, ela "poof" numa nuvem de fumaça
    # e reaparece em outro ponto da tela usando a bandana ninja. Chance
    # baixa de propósito ("continuar sendo surpresa") - pedido do usuário:
    # "Sugiro uma chance baixa, como 10%".
    CHANCE_SUBSTITUICAO_NINJA = 0.10
    # A velocidade do 1º clipe ("poof" inicial) é declarativa agora - ver
    # `state_catalog.EstadoAnimacao.velocidade_multiplicador`
    # (`data/animacoes_galateia.json::flutuando_para_substituicao-ninja
    # .state.speedMultiplier`, 2,988 ≈ 72 quadros × 83ms ÷ 2000ms) - não
    # uma constante aqui, pra `AnimationController` aplicar sozinho não
    # importa quem pediu a transição (arraste real OU o "forçar animação"
    # da bandeja do sistema - pedido do usuário, 2026-09-02: "quero q pela
    # bandeja esteja tudo funcionando como deveria tbm"). O 2º clipe
    # (`substituicao-ninja_para_flutuando`, o "reaparecer") continua sem
    # `speedMultiplier` declarado (1.0 = normal), de propósito.
    # Teleporta pra um ponto no mínimo essa distância do atual ("outro
    # ponto DISTANTE e seguro da tela") - tentativas repetidas até achar
    # um ponto longe o bastante ou esgotar o limite (telas pequenas podem
    # nunca satisfazer, aceita o último sorteio nesse caso).
    DISTANCIA_MINIMA_TELEPORTE_PX = 400
    TENTATIVAS_TELEPORTE = 8

    def _iniciar_fluxo_animado_arraste(self) -> None:
        """Inicia a reação visual assim que confirma arraste real - SEMPRE
        interrompe o que estivesse tocando (autonomia, Wander, Taskbar
        Sit, o que for), não só quando ela já estava parada flutuando
        calma (pedido do usuário, 2026-08-29: "quando eu segurar ela,
        tem de interromper na hora a animação atual"). `forcar_estado`
        pula pro idle flutuando ANTES de pedir a transição real - é
        instantâneo por dentro, mas nunca chega a ser desenhado (mesmo
        truque usado no acordar do sono, ver `BehaviorScheduler._acordar`)."""
        # zera ANTES de emitir/forçar - sem isso, uma finalização pendente
        # de um arraste anterior interrompido por este novo agarrar podia
        # disparar `arraste_finalizado` cedo demais, na emissão de
        # `estado_alterado` do próprio reset abaixo.
        self._arraste_pendente_finalizacao = False
        self._reacao_arraste_definida = False
        self.arraste_iniciado.emit()
        self._queda.parar()
        self._queda_arraste.parar()
        self._controller.forcar_estado("flutuando_idle")

        if random.random() < self.CHANCE_SUBSTITUICAO_NINJA and self._controller.solicitar_transicao(
            "flutuando_para_substituicao-ninja"
        ):
            # 🔥 As duas cenas encadeadas (`flutuando_para_substituicao-ninja`
            # -> `substituicao-ninja_para_flutuando` -> `flutuando_idle`) já
            # são NÃO-interrompíveis e já se encadeiam sozinhas via
            # `fallback` declarativo (`data/animacoes_galateia.json`) -
            # nenhum código novo precisa disso. Só falta impedir o arraste
            # de verdade durante a cena: soltar `_arrastando` AQUI (não só
            # ignorar depois) evita que segurar o botão e mover o mouse
            # depois do teleporte puxe a janela de volta pro cursor com um
            # offset velho - pedido do usuário: "o usuário não deve
            # conseguir arrastá-la durante a fumaça". O usuário simplesmente
            # solta o controle - um novo clique começa um arraste novo, com
            # offset novo, só depois da cena terminar sozinha.
            self._fluxo_arraste_ativo = False
            self._arrastando = False
            self._arraste_pendente_finalizacao = True  # libera arraste_finalizado quando ela voltar a "flutuando" - mesmo gatilho do fluxo normal
            return

        self._fluxo_arraste_ativo = self._controller.solicitar_transicao("flutuando_para_agarrada")
        if self._fluxo_arraste_ativo:
            self._arraste_pendente_finalizacao = True
        else:
            self.arraste_finalizado.emit()  # não deveria falhar (acabamos de garantir o estado válido), mas nunca trava o scheduler à toa

    def _teleportar_apos_substituicao_ninja(self) -> None:
        """Chamado quando `estado_logico` vira `"substituicao-ninja"` -
        exatamente a fronteira entre os dois clipes da cena (fallback
        declarativo troca de `flutuando_para_substituicao-ninja` pra
        `substituicao-ninja_para_flutuando` nesse instante). Medido nos
        quadros reais (não um valor arbitrário): a CAUDA do 1º clipe
        (~9 quadros) e a CABEÇA do 2º (~9 quadros) são comprovadamente
        transparentes (0 pixel opaco na amostragem) - ~1,5s de folga
        total nessa fronteira, tempo de sobra pro `move()` (instantâneo)
        acontecer sem nunca ser visto. Pedido do usuário: "enquanto os
        frames estão vazios, a janela do mascote é teleportada pra outro
        ponto distante e seguro da tela"."""
        tela = self.screen() or QApplication.primaryScreen()
        area_x, area_y, area_w, area_h = platform_windows.obter_work_area_da_tela(tela)
        x_max = max(area_x, area_x + area_w - self.width())
        y_max = max(area_y, area_y + area_h - self.height())
        origem = self.pos()
        nova_x, nova_y = origem.x(), origem.y()
        for _ in range(self.TENTATIVAS_TELEPORTE):
            candidato_x = random.randint(area_x, x_max)
            candidato_y = random.randint(area_y, y_max)
            distancia2 = (candidato_x - origem.x()) ** 2 + (candidato_y - origem.y()) ** 2
            nova_x, nova_y = candidato_x, candidato_y
            if distancia2 >= self.DISTANCIA_MINIMA_TELEPORTE_PX ** 2:
                break
        self.move(nova_x, nova_y)
        self.salvar_posicao_atual()

    def _finalizar_fluxo_animado_arraste(self) -> None:
        """Solta corta na hora, sem esperar a introdução "sendo agarrada"
        terminar sozinha (pedido do usuário, 2026-08-29: "pode cortar
        animações também, assim que eu solto ela, já realiza queda") -
        mesmo truque de `forcar_estado` usado no agarrar: pula pro
        estado "agarrada" direto se ela ainda não tinha chegado lá, e a
        queda começa no mesmo instante que o usuário soltou o botão."""
        if not self._fluxo_arraste_ativo:
            return
        self._fluxo_arraste_ativo = False
        if self._controller.estado_logico != "agarrada":
            self._controller.forcar_estado("arrastada_loop_calma")
        queda = random.choice((
            "arrastada_para_queda-joelho",
            "arrastada_para_queda-bunda",
            "agarrada_para_queda-heroica",
        ))
        self._disparar_queda_do_arraste(queda)

    def _ao_estado_alterado(self, estado: str) -> None:
        if estado == "queda-heroica" and not self._pouso_heroico_pendente:
            # Rede de segurança: só dispara AQUI se `_disparar_queda_heroica`
            # não estiver controlando a troca por posição (ex.: já estava
            # praticamente no chão quando foi solta, sem distância pra cair -
            # `_disparar_queda_do_arraste` retorna cedo nesse caso e nunca
            # arma `_pouso_heroico_pendente`). Durante uma queda de verdade,
            # esse flag fica True e quem decide a hora certa é
            # `_ao_mover_queda_heroica`, baseado na posição real, não no
            # instante em que o estado troca (loop repete até então).
            self._controller.solicitar_transicao("queda-heroica_para_pouso")
        if estado == "substituicao-ninja":
            # única fronteira que leva a esse estado_destino (catálogo,
            # `flutuando_para_substituicao-ninja`) - o próprio 1º clipe
            # acabou de terminar e o fallback declarativo já iniciou o 2º;
            # ela está 100% invisível NOS DOIS LADOS dessa fronteira.
            self._teleportar_apos_substituicao_ninja()
        if estado == "agarrada" and not self._reacao_arraste_definida:
            # a flag evita recursão infinita - trocar de loop TAMBÉM
            # emite "agarrada" de novo (todo `arrastada_loop_*` é loop),
            # e sem essa trava cada troca chamaria a si mesma pra sempre.
            self._reacao_arraste_definida = True
            self._controller.solicitar_transicao(random.choice(ARRASTADA_LOOPS))
        if estado == "leque" and not self._reacao_leque_definida:
            # MESMO raciocínio de "agarrada" acima (a flag evita
            # recursão - `leque_*_loop` também é self-loop, reemite
            # "leque") - 2026-09-06, achado ao vivo: sem isso, ela ficava
            # travada pra sempre no último quadro de `flutuando_para_leque`
            # (fallback `null` no catálogo, sem NENHUM código escolhendo
            # um dos 3 humores), só saindo do congelamento se o usuário
            # clicasse manualmente "Ficar Esnobe"/"Ficar Neutra".
            self._reacao_leque_definida = True
            self._controller.solicitar_transicao(random.choice(LEQUE_LOOPS))
        if estado == "flutuando" and self._arraste_pendente_finalizacao:
            self._arraste_pendente_finalizacao = False
            self.arraste_finalizado.emit()

    def _ao_clipe_concluido(self, clipe_id: str) -> None:
        if clipe_id == "trazendo-caos_para_flutuando":
            self._iniciar_voo_caos()

    def _iniciar_voo_caos(self) -> None:
        """Achado ao vivo, 2026-09-02: o vídeo `trazendo-caos_para_
        flutuando` termina com o caos SEPARADO dela (ela segue pro
        próprio `flutuando_idle` normal) - o caos precisa continuar
        subindo sozinho até sair do monitor, ver `chaos_flight.py`. O
        ponto de ancoragem usa a posição/escala desta janela NO INSTANTE
        em que o clipe anterior termina, pra a troca de vídeo pra janela
        não pular de lugar."""
        ancora = self.pos() + QPoint(
            round(chaos_flight.PONTO_CAOS_NO_VIDEO_ANTERIOR[0] * self._escala),
            round(chaos_flight.PONTO_CAOS_NO_VIDEO_ANTERIOR[1] * self._escala),
        )
        self._voo_caos_atual = chaos_flight.iniciar(ancora, escala=self._escala)
        self._voo_caos_atual.encerrado.connect(self._ao_voo_caos_encerrado)

    def _ao_voo_caos_encerrado(self) -> None:
        self._voo_caos_atual = None

    def _disparar_queda_do_arraste(self, queda_id: str) -> None:
        """Cai até o CHÃO de verdade (não um cochilo de alguns px) - o
        destino do clipe (`queda-joelhos`/`queda-bunda`) já é ela POUSADA,
        então parar no ar no meio do caminho não fazia sentido nenhum
        (pedido do usuário, 2026-08-29: "pode fazer ela se deslocar mais
        na animação de queda"). A duração do deslocamento é a duração
        REAL do próprio clipe (`frame_count * frame_duration_ms`), não
        uma mola que converge rápido e some no meio da animação - ela
        fica caindo pelos ~4s inteiros do clipe (pedido do usuário: "ela
        tem de estar em movimento durante toda o loop de queda").

        Conferi os quadros de verdade (`arrastada_para_queda-joelho`) -
        ela continua em queda livre franca (cabelo esvoaçando, sem
        contato com o chão) até o ÚLTIMO quadro; o pouso de verdade só
        aparece no corte pro clipe de recuperação seguinte
        (`queda-joelhos_para_flutuando`), instantâneo. Por isso NENHUMA
        desaceleração no fim - freando ela perto do chão enquanto a arte
        ainda mostra queda livre a toda velocidade ficava dessincronizado
        (pedido do usuário, 2026-08-29: "controla melhor o tempo...
        quando ela já tiver caído, ela já tem que estar no chão").

        `MovimentoQuedaGravidade` (pausa parada + aceleração contínua,
        nunca desacelerando) troca a curva de aceleração/cruzeiro/freada
        de `MovimentoComDuracaoFixa` - pedido do usuário, 2026-08-29: "a
        animação... está descendo muito rápido" tocando o clipe mais
        devagar (~8s) tirava ela do tempo real do clipe; a correção foi
        deixar a duração TOTAL como a duração natural do clipe de novo,
        e mexer só na FORMA da queda (parada -> acelera igual gravidade
        de verdade) em vez de esticar o relógio inteiro.

        Exceção: `agarrada_para_queda-heroica` desvia pra
        `_disparar_queda_heroica` - diferente de joelho/bunda (um clipe
        só, já termina pousada), a queda heroica tem um LOOP entre a
        introdução e o pouso (`queda-heroica_loop`, repete quantas vezes
        precisar) - a duração daí em diante escala com a distância real,
        não com o tamanho de nenhum clipe."""
        if not self._controller.solicitar_transicao(queda_id):
            return
        asset_queda = self._controller.asset_atual
        tela = self.screen() or QApplication.primaryScreen()
        _, tela_y, _, tela_altura = platform_windows.obter_geometria_completa_da_tela(tela)
        margem = asset_queda.margem_inferior_vazia_px if asset_queda else 0
        piso = tela_y + tela_altura - self.height() + margem
        if piso <= self.y():
            return  # já está no chão (ou muito perto) - sem espaço pra cair

        if queda_id == "agarrada_para_queda-heroica":
            self._disparar_queda_heroica(piso)
            return

        duracao_ms = (asset_queda.frame_count * asset_queda.frame_duration_ms) if asset_queda else 1000
        pausa_ms = min(self.PAUSA_QUEDA_MS, duracao_ms * 0.5)  # nunca mais que metade do clipe, pra clipes curtos não ficarem só pausados
        self._queda_arraste.finalizado.connect(self.salvar_posicao_atual, Qt.ConnectionType.SingleShotConnection)
        self._queda_arraste.iniciar(
            lambda: (self.x(), self.y()),
            lambda x, y: self.move(int(x), int(y)),
            (self.x(), piso),
            pausa_ms,
            duracao_ms - pausa_ms,
        )

    def _disparar_queda_heroica(self, piso: float) -> None:
        """Duração PROPORCIONAL à distância real até o piso (queda livre:
        distância = ½·`ACELERACAO_QUEDA_HEROICA_PXS2`·t², resolvendo pra
        t) - 2026-09-05, pedido do usuário: "ajustar o tempo de queda...
        p tentar controlar velocidade". Antes, a queda inteira (pausa +
        aceleração) sempre acabava exatamente quando o clipe de
        introdução (`agarrada_para_queda-heroica`) terminava (~4s fixos),
        então uma queda de 100px e uma de 1000px levavam o MESMO tempo -
        rápida ou lenta demais dependendo de onde ela foi largada. Agora
        o `queda-heroica_loop` (`interruptible: true`, mesma origem e
        destino - repete sozinho enquanto nada mais for pedido) cobre o
        tempo que for preciso.

        A troca pra `queda-heroica_para_pouso` deixa de ser automática
        assim que o estado entra em "queda-heroica" (ver
        `_ao_estado_alterado`) - `_pouso_heroico_pendente` suspende esse
        gatilho enquanto essa função controla a queda, e quem decide a
        hora certa é `_ao_mover` abaixo: dispara assim que a distância
        restante até o piso cai abaixo de `MARGEM_QUASE_CHAO_HEROICA_PX`,
        não importa em qual repetição do loop ela esteja."""
        distancia = piso - self.y()
        duracao_queda_ms = max(1.0, ((2 * distancia / self.ACELERACAO_QUEDA_HEROICA_PXS2) ** 0.5) * 1000)
        pausa_ms = min(self.PAUSA_QUEDA_MS, duracao_queda_ms * 0.5)
        self._pouso_heroico_pendente = True

        def _ao_mover(x: float, y: float) -> None:
            self.move(int(x), int(y))
            if self._pouso_heroico_pendente and (piso - y) <= self.MARGEM_QUASE_CHAO_HEROICA_PX:
                self._pouso_heroico_pendente = False
                self._controller.solicitar_transicao("queda-heroica_para_pouso")

        self._queda_arraste.finalizado.connect(self.salvar_posicao_atual, Qt.ConnectionType.SingleShotConnection)
        self._queda_arraste.iniciar(
            lambda: (self.x(), self.y()),
            _ao_mover,
            (self.x(), piso),
            pausa_ms,
            duracao_queda_ms,
        )

    def _acomodar_apos_arraste(self) -> None:
        """Colisão com o chão (plano, seção 7.3) - nunca deixa o Mascot
        solto flutuando longe abaixo da tela; ficar ACIMA do piso é o
        idle normal, então só corrige quando o solto ultrapassa o piso
        por baixo.

        Se a pose atual é sentada, o piso alinha o ASSENTO (não o pé) com
        o topo da barra de tarefas - `state_catalog.LINHA_ASSENTO_
        SENTADA_PX`, mesma referência usada pelo Taskbar Sit automático
        (`behavior_scheduler`), pra arrastar-e-soltar sentada acabar no
        mesmo lugar que sentar sozinha. Perna/pé abaixo do assento passar
        da barra é esperado (pedido do usuário, 2026-08-28). Flutuando,
        sem "assento" pra alinhar, usa o pé (`margem_inferior_vazia_px`)
        contra a tela inteira - só evita ela ficar solta longe da tela."""
        tela = self.screen() or QApplication.primaryScreen()
        asset_atual = self._controller.asset_atual
        entrada_atual = state_catalog.CATALOGO.get(asset_atual.id) if asset_atual else None

        if entrada_atual and entrada_atual.estado_origem == "sentada":
            _, area_y, _, area_altura = platform_windows.obter_work_area_da_tela(tela)
            linha_assento = state_catalog.LINHA_ASSENTO_SENTADA_PX * self._escala
            piso = area_y + area_altura - linha_assento
        else:
            _, tela_y, _, tela_altura = platform_windows.obter_geometria_completa_da_tela(tela)
            margem = asset_atual.margem_inferior_vazia_px if asset_atual else 0
            piso = tela_y + tela_altura - self.height() + margem

        if self.y() <= piso:
            self.salvar_posicao_atual()
            return
        self._queda.finalizado.connect(self.salvar_posicao_atual, Qt.ConnectionType.SingleShotConnection)
        self._queda.iniciar(
            lambda: (self.x(), self.y()),
            lambda x, y: self.move(int(x), int(y)),
            (self.x(), piso),
        )
