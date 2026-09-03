# -*- coding: utf-8 -*-
"""Script avulso pra validar a Substituição Ninja (2026-09-02, pedido do
usuário) - reação RARA alternativa ao agarrar normal quando o arraste
começa a partir do idle flutuando: em vez de ser agarrada, ela "poof" numa
fumaça, teleporta pra outro ponto da tela enquanto invisível, e reaparece
usando a bandana ninja. Sem framework de teste (mesmo padrão de
testes/testar_*.py), roda cada caso e imprime PASS/FAIL.

Roda offscreen (`QT_QPA_PLATFORM=offscreen`), mesmo motivo dos outros
testes de Mascot.
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # raiz do projeto

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)

from mascot import platform_windows, state_catalog
from mascot.animation_controller import AnimationController
from mascot.asset_repository import AssetRepository
from mascot.window import MascotWindow

# 🔥 Achado rodando este teste (2026-09-02) - a tela VIRTUAL do
# `QT_QPA_PLATFORM=offscreen` é só 800x800, estreita demais (largura útil
# real de ~188px pra uma cena de 612px de célula) pra garantir de forma
# CONFIÁVEL a distância mínima de teleporte (400px) em só 8 tentativas
# aleatórias - não é bug do teleporte, é a tela de teste pequena demais.
# Simula uma área de trabalho de desktop real (1920x1080) só pra esse
# teste ficar determinístico, independente do tamanho da tela offscreen.
platform_windows.obter_work_area_da_tela = lambda tela: (0, 0, 1920, 1080)

_falhas = []


def checar(nome, condicao, detalhe=""):
    if condicao:
        print(f"PASS: {nome}")
    else:
        print(f"FAIL: {nome} {detalhe}")
        _falhas.append(nome)


def bombear_ate(condicao, timeout_s=5):
    inicio = time.monotonic()
    while not condicao() and time.monotonic() - inicio < timeout_s:
        app.processEvents()
        time.sleep(0.01)
    return condicao()


def esperar_carregamento(timeout_s=5):
    """Mesmo motivo de `testar_mascot_behaviors.py` - carregamento
    assíncrono precisa do loop do Qt rodando pra entregar o asset."""
    return bombear_ate(lambda: controller._id_solicitado_mais_recente not in repositorio._carregando, timeout_s=timeout_s)


def avancar_ate_estavel(n):
    for _ in range(n):
        controller._avancar()
        esperar_carregamento()


repositorio = AssetRepository()
controller = AnimationController(repositorio=repositorio)
window = MascotWindow(controller, escala=1.0)

# ----------------------------------------------------------------------
# CHANCE_SUBSTITUICAO_NINJA = 0.0 - garantia estrutural (não estatística)
# de que o arraste normal continua o padrão quando a substituição está
# "desligada" (mesma configuração que os outros testes de Mascot usam
# pra manter o arraste determinístico).
# ----------------------------------------------------------------------
MascotWindow.CHANCE_SUBSTITUICAO_NINJA = 0.0
window._iniciar_fluxo_animado_arraste()
esperar_carregamento()
checar(
    "com chance 0.0, arraste normal continua indo pra flutuando_para_agarrada",
    controller.animacao_atual == "flutuando_para_agarrada",
    controller.animacao_atual,
)
window._finalizar_fluxo_animado_arraste()
# soltar dispara UMA das duas quedas (sorteada) + a recuperação dela -
# avança o bastante pras duas terminarem, não importa qual foi sorteada
avancar_ate_estavel(
    max(repositorio.obter("arrastada_para_queda-joelho").frame_count, repositorio.obter("arrastada_para_queda-bunda").frame_count)
    + max(repositorio.obter("queda-joelhos_para_flutuando").frame_count, repositorio.obter("queda-bunda_para_flutuando").frame_count)
)
checar("volta a flutuar depois do arraste normal (fim do teste anterior)", controller.estado_logico == "flutuando", controller.estado_logico)

# ----------------------------------------------------------------------
# CHANCE_SUBSTITUICAO_NINJA = 1.0 - força a substituição ninja pra testar
# o fluxo inteiro de propósito, nunca dependendo de sorteio.
# ----------------------------------------------------------------------
MascotWindow.CHANCE_SUBSTITUICAO_NINJA = 1.0
window._arrastando = True  # simula o clique-e-segure real que precede o arraste
# fixa um CANTO conhecido antes de disparar - o teleporte é melhor
# esforço (até `TENTATIVAS_TELEPORTE` sorteios, sem garantia matemática
# dura), então testar a partir do meio da tela deixaria a distância
# mínima menos confiável de bater (achado rodando este teste); do canto,
# a maior parte da área de 1920x1080 simulada acima já satisfaz os 400px.
window.move(0, 0)
posicao_antes = window.pos()
window._iniciar_fluxo_animado_arraste()
esperar_carregamento()

checar(
    "com chance 1.0, dispara flutuando_para_substituicao-ninja em vez de flutuando_para_agarrada",
    controller.animacao_atual == "flutuando_para_substituicao-ninja",
    controller.animacao_atual,
)
checar("arrastar de verdade é liberado NA HORA (usuário não consegue arrastar durante a fumaça)", window._arrastando is False)
checar("_fluxo_arraste_ativo fica False (não é o fluxo normal de agarrar)", window._fluxo_arraste_ativo is False)
checar("_arraste_pendente_finalizacao fica True (mesmo gatilho do fluxo normal libera arraste_finalizado depois)", window._arraste_pendente_finalizacao is True)

# pedido do usuário, 2026-09-02, 5 rodadas: "aumenta um pouco a
# velocidade da cena no início" -> "ainda esta bem lento" -> "pode por
# toda a nimação de intro em 1s" (errado nos DOIS clipes) -> "O tempo
# parece o msm... è apenas ele q quero agilizar" -> testando pela bandeja
# (que não aplicava multiplicador nenhum) -> arrastando de verdade "ta
# rapido, ate demais, poe 2s" + "quero q pela bandeja esteja tudo
# funcionando... n gosto de editar 2 lugares p msm coisa" - virou campo
# DECLARATIVO no catálogo (`state_catalog.EstadoAnimacao.
# velocidade_multiplicador`), lido pelo controller não importa quem pediu
# a transição (arraste real OU a bandeja).
_multiplicador_clipe1 = state_catalog.CATALOGO["flutuando_para_substituicao-ninja"].velocidade_multiplicador
_duracao_esperada_clipe1_ms = max(
    1, round(repositorio.obter("flutuando_para_substituicao-ninja").frame_duration_ms / _multiplicador_clipe1)
)
checar(
    "o 1º clipe (o 'poof') toca no ritmo acelerado calculado",
    controller._timer.interval() == _duracao_esperada_clipe1_ms,
    (controller._timer.interval(), _duracao_esperada_clipe1_ms),
)

checar("controller.tags_atuais inclui 'ninja' durante a cena", "ninja" in controller.tags_atuais, controller.tags_atuais)
checar("window._em_substituicao_ninja() reconhece a cena tocando agora", window._em_substituicao_ninja() is True)

# achado ao vivo pelo usuário, 2026-09-02: "durante toda a animação da
# substituição ninja, gaia não pode ser arrastada ou movida" - um NOVO
# clique+arraste tentado DURANTE a cutscene (não o que a disparou) não
# deveria conseguir mover a janela - mousePressEvent bruto nunca checava
# o grafo antes, só solicitar_transicao fazia isso.
posicao_durante_cena = window.pos()
evento_press_durante_cena = QMouseEvent(
    QEvent.Type.MouseButtonPress, window.rect().center().toPointF(), Qt.MouseButton.LeftButton,
    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
)
window.mousePressEvent(evento_press_durante_cena)
checar(
    "um NOVO clique durante a cena ninja não inicia arraste (_arrastando continua False)",
    window._arrastando is False,
)
evento_move_durante_cena = QMouseEvent(
    QEvent.Type.MouseMove, (window.rect().center() + QPoint(150, 150)).toPointF(), Qt.MouseButton.NoButton,
    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
)
window.mouseMoveEvent(evento_move_durante_cena)
checar(
    "a janela não se move mesmo forçando um mouseMoveEvent durante a cena",
    window.pos() == posicao_durante_cena,
    (window.pos(), posicao_durante_cena),
)

sinais_finalizado = []
window.arraste_finalizado.connect(lambda: sinais_finalizado.append(True))

# soltar o botão NÃO deveria fazer nada - a cena não pode ser interrompida
# e o usuário já perdeu o controle da janela até ela terminar sozinha
window._arrastando = True  # simula "ainda segurando fisicamente, mas o app já soltou o controle internamente"
_estado_antes_do_release = controller.animacao_atual
evento_release = QMouseEvent(
    QEvent.Type.MouseButtonRelease, window.rect().center().toPointF(), Qt.MouseButton.LeftButton,
    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
)
window.mouseReleaseEvent(evento_release)
checar(
    "soltar o botão durante a cena não corta/reinicia nada (guard de _arrastando já tinha sido zerado antes)",
    controller.animacao_atual == _estado_antes_do_release,
    controller.animacao_atual,
)

# avança até a fronteira entre os dois clipes (72 quadros do 1º) - é
# exatamente aí que o teleporte deveria acontecer (ver window.py::
# _teleportar_apos_substituicao_ninja)
avancar_ate_estavel(repositorio.obter("flutuando_para_substituicao-ninja").frame_count)
checar(
    "encadeia sozinha (fallback declarativo) pro 2º clipe, sem precisar de código novo pra isso",
    controller.animacao_atual == "substituicao-ninja_para_flutuando",
    controller.animacao_atual,
)
posicao_depois = window.pos()
distancia2 = (posicao_depois.x() - posicao_antes.x()) ** 2 + (posicao_depois.y() - posicao_antes.y()) ** 2
checar(
    "teleportou de verdade (posição mudou) na fronteira entre os dois clipes",
    posicao_depois != posicao_antes,
    (posicao_antes, posicao_depois),
)
checar(
    "teleporte respeita a distância mínima pedida (\"outro ponto DISTANTE\") quando a tela permite",
    distancia2 >= MascotWindow.DISTANCIA_MINIMA_TELEPORTE_PX ** 2,
    distancia2 ** 0.5,
)
checar(
    "o 2º clipe (o 'reaparecer') toca NORMAL - só o 1º é acelerado, pedido do usuário",
    controller._timer.interval() == repositorio.obter("substituicao-ninja_para_flutuando").frame_duration_ms,
    (controller._timer.interval(), repositorio.obter("substituicao-ninja_para_flutuando").frame_duration_ms),
)

# termina o 2º clipe - deve encadear sozinho pro flutuando_idle e liberar
# arraste_finalizado (mesmo gatilho do fluxo normal, `_ao_estado_alterado`)
avancar_ate_estavel(repositorio.obter("substituicao-ninja_para_flutuando").frame_count)
checar(
    "termina de volta em flutuando_idle sem intervenção manual",
    controller.animacao_atual == "flutuando_idle" and controller.estado_logico == "flutuando",
    (controller.animacao_atual, controller.estado_logico),
)
checar("arraste_finalizado dispara sozinho ao voltar pra flutuando (scheduler pode retomar autonomia)", sinais_finalizado == [True])
checar(
    "o ritmo acelerado do 1º clipe NÃO vaza pro flutuando_idle depois (multiplicador nunca persiste sozinho)",
    controller._timer.interval() == repositorio.obter("flutuando_idle").frame_duration_ms,
    (controller._timer.interval(), repositorio.obter("flutuando_idle").frame_duration_ms),
)

# ----------------------------------------------------------------------
# a cena não pode ser interrompida - pedir uma transição concorrente no
# meio dela precisa ser rejeitada, igual qualquer outro clipe não-loop
# não-interrompível do catálogo (mesma regra geral, sem código novo).
# ----------------------------------------------------------------------
MascotWindow.CHANCE_SUBSTITUICAO_NINJA = 1.0
window._arrastando = True
window._iniciar_fluxo_animado_arraste()
esperar_carregamento()
aceitou = controller.solicitar_transicao("flutuando_para_agarrada")
checar(
    "flutuando_para_agarrada é rejeitada no meio da cena ninja (não-interrompível)",
    aceitou is False and controller.animacao_atual == "flutuando_para_substituicao-ninja",
    (aceitou, controller.animacao_atual),
)
avancar_ate_estavel(
    repositorio.obter("flutuando_para_substituicao-ninja").frame_count
    + repositorio.obter("substituicao-ninja_para_flutuando").frame_count
)

# ----------------------------------------------------------------------
# correção do usuário, 2026-09-02: "apenas a animação de substituição
# ninja q tem de impedir de ser agarrada ou trocar animação para
# agarrada... o resto pode normalmente" - QUALQUER outra cena
# não-interrompível (ex.: "trazendo o caos") continua aceitando arraste
# bruto de mouse igual antes, só a Ninja bloqueia.
# ----------------------------------------------------------------------
window.move(0, 0)
controller.solicitar_transicao("flutuando_para_trazendo-caos")
esperar_carregamento()
checar(
    "'trazendo o caos' (outra cena não-interrompível) NÃO é reconhecida como Ninja",
    window._em_substituicao_ninja() is False,
)
ponto_local_press = window.rect().center()
evento_press_caos = QMouseEvent(
    QEvent.Type.MouseButtonPress, ponto_local_press.toPointF(), window.mapToGlobal(ponto_local_press).toPointF(),
    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
)
window.mousePressEvent(evento_press_caos)
checar("clique durante 'trazendo o caos' inicia arraste normalmente (_arrastando vira True)", window._arrastando is True)
posicao_antes_caos = window.pos()
ponto_local_move = window.rect().center() + QPoint(150, 150)
evento_move_caos = QMouseEvent(
    QEvent.Type.MouseMove, ponto_local_move.toPointF(), window.mapToGlobal(ponto_local_move).toPointF(),
    Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
)
window.mouseMoveEvent(evento_move_caos)
checar(
    "a janela se move normalmente durante 'trazendo o caos' (arraste não é bloqueado)",
    window.pos() != posicao_antes_caos,
    (window.pos(), posicao_antes_caos),
)

controller.parar()

# ----------------------------------------------------------------------
# pedido do usuário, 2026-09-02: "quero q pela bandeja esteja tudo
# funcionando como deveria tbm. N gosto de ter q editar 2 lugares p msm
# coisa" - a bandeja do sistema (`process_main.py::_montar_submenu_
# playground`) chama `controller.solicitar_transicao(id_)` DIRETO, sem
# NENHUMA janela/multiplicador envolvido - controller novo, sem
# MascotWindow nenhuma, simula exatamente esse caminho.
# ----------------------------------------------------------------------
controller_bandeja = AnimationController(repositorio=repositorio)
esperar_carregamento_bandeja = lambda: bombear_ate(
    lambda: controller_bandeja._id_solicitado_mais_recente not in repositorio._carregando, timeout_s=5
)
esperar_carregamento_bandeja()
aceitou_bandeja = controller_bandeja.solicitar_transicao("flutuando_para_substituicao-ninja")
esperar_carregamento_bandeja()
_duracao_esperada_bandeja_ms = max(
    1, round(repositorio.obter("flutuando_para_substituicao-ninja").frame_duration_ms / _multiplicador_clipe1)
)
checar(
    "a bandeja (forçar animação, sem MascotWindow nenhuma) TAMBÉM toca a ninja no ritmo acelerado",
    aceitou_bandeja and controller_bandeja._timer.interval() == _duracao_esperada_bandeja_ms,
    (aceitou_bandeja, controller_bandeja._timer.interval(), _duracao_esperada_bandeja_ms),
)
controller_bandeja.parar()

print()
if _falhas:
    print(f"{len(_falhas)} FALHA(S): {_falhas}")
    sys.exit(1)
print("Todos os casos passaram.")
