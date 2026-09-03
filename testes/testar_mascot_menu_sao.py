# -*- coding: utf-8 -*-
"""Script avulso pra validar o Menu SAO (`GAIA_MENU_SAO.md`, 2026-09-02) -
sem framework de teste (mesmo padrão de testes/testar_mascot_*.py), roda
cada caso e imprime PASS/FAIL. Cobre: `platform_windows.lado_com_mais_
espaco` (helper novo), `SafetyController` como conjunto de bloqueios (não
um bool único), `BehaviorScheduler` reiniciando cooldown ao liberar
autonomia sem gastar orçamento por hora, `MenuSAO` (estado/animação/
roteamento de clique/bloqueio) construindo um `MascotApp` real em modo
demonstração, e o acumulador de scroll de `MascotWindow.wheelEvent`.

Roda offscreen (`QT_QPA_PLATFORM=offscreen`) - sem janela/hotkey global de
verdade, mesmo motivo de `testar_mascot_protocolo.py`.
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # raiz do projeto

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)

from mascot import platform_windows
from mascot.animation_controller import AnimationController
from mascot.asset_repository import AssetRepository
from mascot.safety import SafetyController
from mascot.window import MascotWindow

# 🔥 Achado rodando este teste várias vezes (2026-09-02) - `MascotApp` usa
# um `SafetyController` REAL (não um substituto fixo como `_SafetyFixo`
# de `testar_mascot_behaviors.py`, que já documenta esse mesmo problema:
# "SafetyController real depende do foco de janela do Windows no momento
# do teste, não-determinístico"). Sem neutralizar isso, qualquer janela
# em tela cheia/jogo/RDP no MOMENTO do teste (nada a ver com o Menu SAO)
# faz `autonomia_permitida` ficar `False` mesmo com o conjunto de
# bloqueios de interação vazio - falha intermitente, não bug do Menu SAO.
platform_windows.deve_pausar_autonomia = lambda: False

_falhas = []


def checar(nome, condicao, detalhe=""):
    if condicao:
        print(f"PASS: {nome}")
    else:
        print(f"FAIL: {nome} {detalhe}")
        _falhas.append(nome)


def bombear(segundos):
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        app.processEvents()
        time.sleep(0.01)


def evento_roda(delta_y: int) -> QWheelEvent:
    return QWheelEvent(
        QPointF(0, 0), QPointF(0, 0), QPoint(0, 0), QPoint(0, delta_y),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )


# ----------------------------------------------------------------------
# platform_windows.lado_com_mais_espaco
checar(
    "mais espaço à direita escolhe 'right'",
    platform_windows.lado_com_mais_espaco(x=100, largura=50, area_x=0, area_largura=1000) == "right",
)
checar(
    "mais espaço à esquerda escolhe 'left'",
    platform_windows.lado_com_mais_espaco(x=900, largura=50, area_x=0, area_largura=1000) == "left",
)
checar(
    "empate exato cai em 'right'",
    platform_windows.lado_com_mais_espaco(x=475, largura=50, area_x=0, area_largura=1000) == "right",
)

# ----------------------------------------------------------------------
# SafetyController como CONJUNTO de bloqueios (2026-09-02) - não um bool
safety = SafetyController()
safety._pausar_por_plataforma = False  # nunca depende do foco de janela real do Windows neste teste
safety._recalcular()

eventos_autonomia = []
safety.autonomia_alterada.connect(lambda permitida: eventos_autonomia.append(permitida))

checar("autonomia permitida por padrão (sem bloqueios)", safety.autonomia_permitida is True)
safety.bloquear_autonomia("companion_panel")
checar("um bloqueio já é suficiente pra negar autonomia", safety.autonomia_permitida is False)
safety.bloquear_autonomia("menu_sao")
checar("dois bloqueios simultâneos - ainda negada", safety.autonomia_permitida is False)
safety.liberar_autonomia("companion_panel")
checar("liberar UM dos dois motivos não libera autonomia - o outro ainda segura", safety.autonomia_permitida is False)
safety.liberar_autonomia("menu_sao")
checar("liberar o ÚLTIMO motivo libera autonomia de verdade", safety.autonomia_permitida is True)
safety.liberar_autonomia("motivo_que_nunca_bloqueou")
checar("liberar um motivo que não estava bloqueando não crasha nem re-emite à toa", eventos_autonomia == [False, True])

# ----------------------------------------------------------------------
# MascotWindow.wheelEvent - acumulador com limiar e reset por inatividade
repositorio = AssetRepository()
controller = AnimationController(repositorio=repositorio)
janela = MascotWindow(controller)

scroll_baixo, scroll_cima = [], []
janela.scroll_baixo_confirmado.connect(lambda: scroll_baixo.append(True))
janela.scroll_cima_confirmado.connect(lambda: scroll_cima.append(True))

janela.wheelEvent(evento_roda(-60))
checar("um delta abaixo do limiar (60 de 120) ainda não confirma nada", not scroll_baixo and not scroll_cima)
janela.wheelEvent(evento_roda(-60))
checar("acumulado até o limiar confirma scroll pra baixo", scroll_baixo == [True])

janela._acumulador_scroll = 0.0
janela.wheelEvent(evento_roda(200))
checar("um delta bem acima do limiar confirma scroll pra cima na hora", scroll_cima == [True])

janela._acumulador_scroll = -100.0  # se NÃO resetasse, +(-90) do próximo evento cruzaria o limiar (-190)
janela._ultimo_scroll_s = time.monotonic() - 1.0  # mais velho que o limiar de reset (0.3s)
janela.wheelEvent(evento_roda(-90))
checar(
    "acumulador reseta depois de um gap de inatividade - -100 acumulado antigo + -90 novo NÃO se somam",
    scroll_baixo == [True],  # continua só o 1 disparo anterior; o -90 sozinho não cruza o limiar de -120
)

janela._arrastando = True
janela._acumulador_scroll = 0.0
janela.wheelEvent(evento_roda(-200))
checar("scroll ignorado durante arraste real", scroll_baixo == [True])
janela._arrastando = False

controller.parar()

# ----------------------------------------------------------------------
# MenuSAO completo - via MascotApp real em modo demonstração (mesmo padrão
# de testar_mascot_protocolo.py: sem GAIA_MASCOT_CANAL/TOKEN)
from mascot import menu_sao as menu_sao_module
from mascot import process_main

mascot_app = process_main.MascotApp()
menu = mascot_app.menu_sao

checar("menu_sao existe e começa fechado", menu is not None and menu._estado == "closed")
checar("autonomia permitida antes de abrir o menu", mascot_app.safety.autonomia_permitida is True)

menu.abrir()
checar("abrir() muda o estado pra 'opening' na hora", menu._estado == "opening")
checar("abrir() bloqueia autonomia imediatamente (não espera a animação)", mascot_app.safety.autonomia_permitida is False)
checar("direção fica registrada (doc: 'armazenada enquanto o menu estiver aberto')", menu.direcao in ("left", "right"))

checar("círculo ainda animando (progresso < 1) não dispara hover-expand", menu._circulos[0]._progresso < 0.999)
menu._circulos[0].enterEvent(None)
checar("hover num círculo AINDA animando é ignorado (evita expandir antes dele assentar)", menu._hover_estado == "closed")
menu._circulos[0].leaveEvent(None)  # limpa o hover simulado antes de deixar a animação real terminar

bombear(1.0)  # sobra de tempo pros 4 itens (3*55ms atraso + 220ms cada) convergirem
checar("estado converge pra 'open' sozinho", menu._estado == "open")
checar("os 4 círculos terminam com progresso 1.0", all(c._progresso >= 0.999 for c in menu._circulos))

# hover-expand button (2026-09-02, "Oq eu queria era a ideia de
# hover-expand button" - o PRÓPRIO círculo vira pílula, sem rótulo separado)
primeiro_circulo = menu._circulos[0]
checar("círculo começa sem expandir (hover_progresso 0)", primeiro_circulo._hover_progresso == 0.0)
checar("largura reservada do widget é a MAIOR pílula entre os 4 itens (todos alinhados na mesma borda)", primeiro_circulo.width() == menu.width())
checar(
    "TODOS os círculos expandem pra MESMA largura (achado ao vivo: 'os botoes... tem de ter a msm largura')",
    len({c._largura_expandida for c in menu._circulos}) == 1,
)

# largura reservada tem que caber o texto de VERDADE na fonte de VERDADE
# usada em paintEvent - achado ao vivo (2026-09-02): "o texto maior esta
# sendo cortado quando o botao abre para a esquerda" (media com a fonte
# PADRÃO do widget, menor que a fonte de desenho de 10pt, cortava
# "Conversar", o mais longo).
from PySide6.QtGui import QFont, QFontMetrics as _QFM  # noqa: E402

_fonte_medida = QFont(menu.font())
_fonte_medida.setPointSizeF(menu_sao_module.FONTE_ROTULO_PT)
_fm_rotulo = _QFM(_fonte_medida)
for _id_, _rotulo, _, _ in menu_sao_module.ITENS:
    _necessario = (
        menu_sao_module.DIAMETRO_CIRCULO + menu_sao_module.PADDING_PILULA_H
        + _fm_rotulo.horizontalAdvance(_rotulo) + menu_sao_module.PADDING_PILULA_H
    )
    checar(
        f"largura reservada cabe '{_rotulo}' na fonte de desenho (10pt) sem cortar",
        menu.width() >= _necessario,
        (menu.width(), _necessario),
    )
primeiro_circulo.enterEvent(None)
checar("hover num círculo já assentado (progresso 1.0) começa a expandir", menu._hover_estado == "opening" and menu._circulo_animando is primeiro_circulo)
bombear(0.5)
checar("expansão converge pra 'open' com hover_progresso 1.0", menu._hover_estado == "open" and primeiro_circulo._hover_progresso >= 0.999)
primeiro_circulo.leaveEvent(None)
checar("tirar o mouse começa a recolher", menu._hover_estado == "closing")
bombear(0.5)
checar("recolhe de vez (hover_progresso volta a 0, estado 'closed')", menu._hover_estado == "closed" and primeiro_circulo._hover_progresso == 0.0)

segundo_circulo = menu._circulos[1]
primeiro_circulo.enterEvent(None)
bombear(0.5)
checar("hover no 1º círculo expandiu ele", primeiro_circulo._hover_progresso >= 0.999)
primeiro_circulo.leaveEvent(None)
segundo_circulo.enterEvent(None)
bombear(0.5)
checar("trocar de círculo (leave do 1º + enter do 2º) recolhe o antigo e expande o novo", primeiro_circulo._hover_progresso <= 0.001 and segundo_circulo._hover_progresso >= 0.999)
segundo_circulo.leaveEvent(None)
bombear(0.5)

visivel_antes = mascot_app.companion_panel.isVisible()
menu._ao_clicar("conversar")
checar("clicar 'Conversar' alterna o CompanionPanel (redundante de propósito com o clique direto)", mascot_app.companion_panel.isVisible() != visivel_antes)
checar("qualquer clique fecha o menu", menu._estado in ("closing", "closed"))
checar("CompanionPanel sozinho (motivo próprio) já segura o bloqueio mesmo com o menu fechando", mascot_app.safety.autonomia_permitida is False)
bombear(1.0)
checar("menu terminou de fechar", menu._estado == "closed")
checar("autonomia CONTINUA bloqueada - o CompanionPanel ainda está aberto", mascot_app.safety.autonomia_permitida is False)
mascot_app.companion_panel.hide()
checar("fechar o CompanionPanel libera o motivo dele", mascot_app.safety.autonomia_permitida is True)

modo_antes = mascot_app.companion_panel._modo_voz_atual
menu.abrir()
bombear(1.0)
menu._ao_clicar("voz")
checar("clicar 'Voz' ciclou o MESMO modo do CompanionPanel (nunca um estado próprio duplicado)", mascot_app.companion_panel._modo_voz_atual != modo_antes)
bombear(1.0)

checar(
    "'Ações' e 'GAIA' nascem marcadas como desabilitadas (achado ao vivo: GPT sugeriu, usuário endossou)",
    menu_sao_module.IDS_DESABILITADOS == {"acoes", "gaia"},
    menu_sao_module.IDS_DESABILITADOS,
)
circulo_acoes = menu._circulos[2]
circulo_gaia = menu._circulos[3]
checar("círculo 'Ações' está marcado desabilitado", circulo_acoes._desabilitado is True)
checar("círculo 'GAIA' está marcado desabilitado", circulo_gaia._desabilitado is True)
checar("círculo 'Conversar'/'Voz' NÃO estão desabilitados", menu._circulos[0]._desabilitado is False and menu._circulos[1]._desabilitado is False)

menu.abrir()
bombear(1.0)
circulo_acoes.enterEvent(None)
checar("hover em item desabilitado ainda expande (revela o rótulo)", menu._hover_estado == "opening")
checar("mas NUNCA destaca cor (self._hover fica False mesmo em hover de verdade)", circulo_acoes._hover is False)
circulo_acoes.leaveEvent(None)
bombear(0.3)

estado_antes = menu._estado
menu._ao_clicar("acoes")
checar("clicar 'Ações' (desabilitado) NÃO fecha o menu nem finge uma ação", menu._estado == estado_antes)
menu._ao_clicar("gaia")
checar("clicar 'GAIA' (idem) também não faz nada", menu._estado == estado_antes)
menu.fechar(imediato=True)

for b in mascot_app.scheduler._behaviors:
    b.ultimo_disparo = 0.0
    b.disparos_na_janela = ["marcador"]
menu.abrir()
bombear(1.0)
antes_de_fechar = time.monotonic()
menu.fechar(imediato=True)
checar("fechar(imediato=True) muda pra 'closed' na hora, sem esperar animação", menu._estado == "closed")
checar("fechar(imediato=True) libera autonomia na hora também", mascot_app.safety.autonomia_permitida is True)
checar(
    "liberar autonomia reinicia ultimo_disparo pra AGORA (não deixa ela sair voando na hora de fechar)",
    all(abs(b.ultimo_disparo - antes_de_fechar) < 1.0 for b in mascot_app.scheduler._behaviors),
)
checar(
    "reiniciar cooldown NÃO conta como disparo real - orçamento por hora intacto",
    all(b.disparos_na_janela == ["marcador"] for b in mascot_app.scheduler._behaviors),
)

# reabrir NO MEIO de um fechamento em andamento - achado por um teste
# intermitente (o menu.abrir() de uma rodada anterior às vezes corria
# contra o fechamento da rodada anterior ainda não ter convergido) -
# sobrescrever _estado pra "opening" sem nunca liberar o bloqueio antigo
# vazava "menu_sao" pra sempre. bombear(0.05) simula "reabriu rápido, mas
# não instantâneo" - o suficiente pra estar em "closing" de verdade, não
# mais em "open".
menu.abrir()
bombear(1.0)
menu.fechar()  # começa a fechar, com animação
bombear(0.05)  # NÃO espera terminar - ainda em "closing" de verdade
checar("confirma que ainda está fechando (não terminou) antes do teste de verdade", menu._estado == "closing")
menu.abrir()  # reabre NO MEIO do fechamento anterior
checar("reabrir no meio do fechamento não trava num estado inválido", menu._estado == "opening")
checar("reabrir no meio do fechamento não vaza o bloqueio antigo (recalculado do zero)", mascot_app.safety.autonomia_permitida is False)
bombear(1.0)
checar("converge normalmente pra 'open' depois da reabertura no meio do fechamento", menu._estado == "open")
menu.fechar(imediato=True)
bombear(0.2)
checar("fecha de vez sem deixar bloqueio vazado depois de todo esse malabarismo", mascot_app.safety.autonomia_permitida is True)

mascot_app.controller.parar()


print()
if _falhas:
    print(f"{len(_falhas)} FALHA(S): {_falhas}")
    sys.exit(1)
print("Todos os casos passaram.")
