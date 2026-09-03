# -*- coding: utf-8 -*-
"""Adaptador de plataforma Windows do Mascot/LOKI (plano, seção 11 -
Segurança Windows, e seção 7.3/10 - work area pra Taskbar Sit).

Só heurísticas de LEITURA (nunca `BlockInput`, nunca injeção de input) -
mesmo espírito do resto do ecossistema (`features/avatar_overlay/
vtuber_overlay.py` já usa win32gui/win32process do mesmo jeito, sem
dependência nova). Erra pro lado de PAUSAR autonomia quando incerto - é só
uma animação de idle, não uma função crítica, então falso positivo
(pausar sem precisar) é sempre mais seguro que falso negativo (continuar
"viva" durante um jogo em tela cheia ou tela de bloqueio).
"""
from __future__ import annotations

import win32api
import win32con
import win32gui


def esta_em_tela_cheia_ou_jogo() -> bool:
    """Heurística padrão: a janela em foco cobre exatamente a área do
    monitor em que está (sem borda/legenda visível) - jogo/app em tela
    cheia real faz isso; janela maximizada normal ainda deixa a barra de
    tarefas visível (`GetWindowRect` != geometria do monitor inteiro)."""
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd or hwnd == win32gui.GetDesktopWindow():
        return False
    try:
        titulo = win32gui.GetWindowText(hwnd)
    except win32gui.error:
        return False
    if not titulo:
        return False  # janelas sem título costumam ser do shell/sistema, não um app real

    try:
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        info_monitor = win32api.GetMonitorInfo(monitor)
        rect_monitor = info_monitor["Monitor"]
        rect_janela = win32gui.GetWindowRect(hwnd)
    except win32gui.error:
        return False

    return rect_janela == rect_monitor


def esta_em_area_de_trabalho_remota() -> bool:
    """Sessão de Área de Trabalho Remota (RDP) - `SM_REMOTESESSION`."""
    return bool(win32api.GetSystemMetrics(0x1000))


def esta_em_desktop_seguro_ou_bloqueada() -> bool:
    """Sem janela em foco (`GetForegroundWindow() == 0`) é o proxy mais
    barato pra "tela de bloqueio/UAC/desktop seguro trocado" - o Windows
    não expõe isso direto sem abrir handles de desktop, e o custo de um
    falso positivo aqui é só pausar a animação um instante, nunca travar
    nada do usuário."""
    return win32gui.GetForegroundWindow() == 0


def obter_segundos_ociosos() -> float:
    """Ociosidade REAL de teclado/mouse (`GetLastInputInfo`/`GetTickCount`,
    ambos em ms desde o boot) - pedido do usuário, 2026-08-29: "quero que
    ela reconheça quando estou afk". Diferente do "tempo sem falar com a
    GAIA" que `core/agent/ultima_interacao.py` já rastreia (usado pelo
    Avatar Virtual/Hidratação) - aquilo é sobre CONVERSA, isto é sobre
    estar de verdade longe do teclado, mesmo ocupado no PC sem ter
    "falado" nada. `GetTickCount` estoura e reinicia a cada ~49,7 dias
    (contador de 32 bits) - na volta ao zero, uma única leitura pode
    achar um valor sem sentido (negativo), mas corrige sozinha na
    checagem seguinte (3s depois, ver `BehaviorScheduler._tick`), sem
    exigir tratamento especial pra essa janela rara."""
    return max(0.0, win32api.GetTickCount() - win32api.GetLastInputInfo()) / 1000.0


def deve_pausar_autonomia() -> bool:
    return (
        esta_em_tela_cheia_ou_jogo()
        or esta_em_area_de_trabalho_remota()
        or esta_em_desktop_seguro_ou_bloqueada()
    )


def obter_work_area_da_tela(screen) -> "tuple[int, int, int, int]":
    """`screen` é um `QScreen` - `availableGeometry()` já exclui a barra de
    tarefas (qualquer borda dela, inclusive auto-hide quando visível) sem
    precisar de nenhuma chamada Win32 própria; `.geometry()` seria a tela
    inteira, incluindo a área por baixo da barra."""
    geometria = screen.availableGeometry()
    return geometria.x(), geometria.y(), geometria.width(), geometria.height()


def obter_geometria_completa_da_tela(screen) -> "tuple[int, int, int, int]":
    """Tela inteira, SEM excluir a barra de tarefas - usado só pro "chão"
    de sentar (Taskbar Sit/arraste), onde a intenção é a personagem ficar
    à altura da barra, aceitando pernas/parte do corpo cobertas por ela
    (mesmo espírito de ela ser cortada normalmente ao cruzar a borda de
    um monitor - pedido explícito do usuário, 2026-08-28: "não tem
    problema parte da perna não aparecer, o importante é ela conseguir
    de fato sentar na barra"). `obter_work_area_da_tela` continua sendo o
    limite certo pra outras decisões (ex.: não deixar o CompanionPanel
    nascer atrás da barra)."""
    geometria = screen.geometry()
    return geometria.x(), geometria.y(), geometria.width(), geometria.height()


def lado_com_mais_espaco(x: int, largura: int, area_x: int, area_largura: int) -> str:
    """"right" ou "left" - lado com mais espaço livre dentro da work area,
    dado o retângulo X de um elemento (ex.: a GAIA) e a área útil da tela
    (`obter_work_area_da_tela`). Mesmo critério que `companion_panel.py`
    já calculava embutido (não alterado - baixo risco tocar em código já
    testado só pra extrair); usado pelo Menu SAO (`menu_sao.py`,
    `GAIA_MENU_SAO.md`, "Posicionamento automático") e por qualquer
    elemento futuro que precise da mesma decisão."""
    espaco_direita = (area_x + area_largura) - (x + largura)
    espaco_esquerda = x - area_x
    return "right" if espaco_direita >= espaco_esquerda else "left"


def obter_geometria_todos_os_monitores(permitidos: "list[str] | None" = None) -> "tuple[int, int, int, int]":
    """União das telas conectadas - usado pelo Wander e por "ir até o
    destino" pra ela conseguir atravessar de monitor, em vez de ficar
    presa no que já está (bug real reportado pelo usuário, 2026-08-29:
    "ela não está conseguindo passar pra outro monitor"). Um monitor
    desalinhado (não encostando perfeitamente nos outros) pode deixar um
    vão dentro dessa caixa delimitadora - aceitável, o mesmo tipo de
    limitação que já existe pra ela cortar normalmente numa borda de
    monitor.

    `permitidos` (lista de `QScreen.name()`, ex.: `["Hailstorm"]`) - vazio
    ou `None` inclui todos; um nome que não bate com NENHUM monitor
    conectado (config desatualizada depois de trocar de monitor) cai de
    volta pra "todos", nunca devolve uma região vazia."""
    from PySide6.QtWidgets import QApplication

    telas = list(QApplication.screens())
    if not telas:
        return 0, 0, 1920, 1080
    if permitidos:
        filtradas = [tela for tela in telas if tela.name() in permitidos]
        if filtradas:
            telas = filtradas
    geometrias = [tela.geometry() for tela in telas]
    x_min = min(g.x() for g in geometrias)
    y_min = min(g.y() for g in geometrias)
    x_max = max(g.x() + g.width() for g in geometrias)
    y_max = max(g.y() + g.height() for g in geometrias)
    return x_min, y_min, x_max - x_min, y_max - y_min
