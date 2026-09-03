# -*- coding: utf-8 -*-
"""Script avulso pra validar o voo do "caos" (2026-09-02, pedido do
usuário) - depois de `trazendo-caos_para_flutuando` terminar, ELA volta
sozinha pro `flutuando_idle` normal (já coberto por `testar_mascot_
assets.py`), mas o caos SEPARADO dela precisa continuar subindo até sair
do monitor (`features/mascot/chaos_flight.py`). Sem framework de teste
(mesmo padrão de testes/testar_*.py), roda cada caso e imprime PASS/FAIL.

Roda offscreen (`QT_QPA_PLATFORM=offscreen`), mesmo motivo dos outros
testes de Mascot.
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # raiz do projeto

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)

from mascot import chaos_flight, platform_windows
from mascot.animation_controller import AnimationController
from mascot.asset_repository import AssetRepository
from mascot.window import MascotWindow

# mesmo achado do teste de Substituição Ninja - tela virtual do offscreen
# é só 800x800, estreita demais pra simular "sair do monitor" de forma
# confiável (a célula da cena já tem 612px de largura). Área de trabalho
# de desktop real só pra este teste ficar determinístico.
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
    return bombear_ate(lambda: controller._id_solicitado_mais_recente not in repositorio._carregando, timeout_s=timeout_s)


def avancar_ate_estavel(n):
    for _ in range(n):
        controller._avancar()
        esperar_carregamento()


repositorio = AssetRepository()
controller = AnimationController(repositorio=repositorio)
window = MascotWindow(controller, escala=1.0)

clipes_concluidos = []
controller.clipe_concluido.connect(clipes_concluidos.append)

# espiona a posição REAL da janela da Gaia no instante exato em que o voo
# nasce (ela está na célula LARGA da cena nesse momento, 612x344 -
# diferente da célula estreita do personagem normal, 384x338 - o
# `_ao_quadro_alterado` reancora o TOPO-ESQUERDA da janela quando a
# célula muda de tamanho pra manter o pivô fixo na tela, então a posição
# capturada ANTES de começar a cena não serve de referência aqui).
posicoes_gaia_no_disparo = []
_iniciar_voo_original = chaos_flight.iniciar


def _iniciar_voo_espiao(ponto_ancora_tela, escala=1.0):
    posicoes_gaia_no_disparo.append(window.pos())
    return _iniciar_voo_original(ponto_ancora_tela, escala=escala)


chaos_flight.iniciar = _iniciar_voo_espiao

# ----------------------------------------------------------------------
# id fora do catálogo do caos não deveria fazer o voo nascer à toa -
# guarda de regressão simples antes de disparar a cena de verdade.
# ----------------------------------------------------------------------
window._ao_clipe_concluido("flutuando_para_agarrada")
checar("clipe concluído qualquer NÃO cria voo do caos à toa", window._voo_caos_atual is None)

# ----------------------------------------------------------------------
# fluxo real: flutuando -> trazendo o caos -> (fallback) trazendo-caos_
# para_flutuando -> (fallback) flutuando_idle - mesma cena já coberta por
# testar_mascot_assets.py, mas aqui o que importa é o EFEITO COLATERAL na
# janela (nascer o voo do caos), não só o estado_logico final.
# ----------------------------------------------------------------------
posicao_gaia_antes = window.pos()
aceitou = controller.solicitar_transicao("flutuando_para_trazendo-caos")
checar("'trazendo o caos' é aceita a partir do idle flutuando", aceitou)
esperar_carregamento()

avancar_ate_estavel(repositorio.obter("flutuando_para_trazendo-caos").frame_count)
checar(
    "encadeia sozinha pro 2º clipe (trazendo-caos_para_flutuando)",
    controller.animacao_atual == "trazendo-caos_para_flutuando",
    controller.animacao_atual,
)
checar("voo do caos ainda não nasceu (2º clipe ainda tocando)", window._voo_caos_atual is None)

avancar_ate_estavel(repositorio.obter("trazendo-caos_para_flutuando").frame_count)
checar(
    "ela termina de volta em flutuando_idle, tocando a PRÓPRIA animação normalmente",
    controller.animacao_atual == "flutuando_idle" and controller.estado_logico == "flutuando",
    (controller.animacao_atual, controller.estado_logico),
)
checar(
    "clipe_concluido emitiu os dois IDs certos, na ordem",
    clipes_concluidos == ["flutuando_para_trazendo-caos", "trazendo-caos_para_flutuando"],
    clipes_concluidos,
)
checar("o voo do caos nasceu sozinho ao terminar o 2º clipe", window._voo_caos_atual is not None)
voo = window._voo_caos_atual

checar("o espião capturou a posição da Gaia no instante do disparo", len(posicoes_gaia_no_disparo) == 1, posicoes_gaia_no_disparo)
ancora_esperada = posicoes_gaia_no_disparo[0] + QPoint(*chaos_flight.PONTO_CAOS_NO_VIDEO_ANTERIOR)
topo_esquerdo_esperado = ancora_esperada - QPoint(*chaos_flight.PONTO_CAOS_NO_PROPRIO_LOOP)
checar(
    "a janela do voo nasce alinhada ao ponto exato onde o caos estava no vídeo anterior (sem pular de lugar)",
    voo.pos() == topo_esquerdo_esperado,
    (voo.pos(), topo_esquerdo_esperado),
)
checar(
    "a janela da Gaia NÃO se mexeu (ela continua flutuando parada, separada do caos)",
    window.pos() == posicao_gaia_antes,
    (window.pos(), posicao_gaia_antes),
)

# ----------------------------------------------------------------------
# o loop de voo continua girando quadro-a-quadro enquanto ele sobe.
# ----------------------------------------------------------------------
indice_antes = voo._indice_quadro
for _ in range(voo._asset.frame_count + 3):
    voo._avancar_quadro()
checar(
    "o quadro do voo dá a volta (loop) em vez de parar no fim",
    voo._indice_quadro == (indice_antes + voo._asset.frame_count + 3) % voo._asset.frame_count,
    voo._indice_quadro,
)

# ----------------------------------------------------------------------
# sobe até sair de vez do monitor simulado (1920x1080) e some sozinho -
# chama `_subir()` direto em vez de esperar o QTimer real (determinístico
# e rápido, mesmo espírito de `avancar_ate_estavel` acima).
# ----------------------------------------------------------------------
y_inicial = voo.y()
sinais_encerrado = []
voo.encerrado.connect(lambda: sinais_encerrado.append(True))

for _ in range(10_000):
    if not voo.isVisible() and sinais_encerrado:
        break
    voo._subir()
checar("o voo realmente subiu (y diminuiu) antes de sumir", voo.y() < y_inicial or sinais_encerrado, (voo.y(), y_inicial))
checar("o voo emite 'encerrado' sozinho ao sair da tela", sinais_encerrado == [True])
app.processEvents()  # entrega o `deleteLater()`/o slot que zera `_voo_caos_atual`
checar("a janela some (referência volta a None) sem intervenção manual", window._voo_caos_atual is None)

controller.parar()

print()
if _falhas:
    print(f"{len(_falhas)} FALHA(S): {_falhas}")
    sys.exit(1)
print("Todos os casos passaram.")
