# -*- coding: utf-8 -*-
"""Hotkey de "ir até aqui" (pedido do usuário, 2026-08-29: modificador +
clique do mouse, padrão Alt+botão esquerdo, configurável) - detecta o
combo em QUALQUER lugar do desktop (não só sobre a janela do Mascot).

Deliberadamente por POLLING de `GetAsyncKeyState` (QTimer, ~30ms) em vez
de um hook global de mouse (`SetWindowsHookEx`) - o plano (seção 11) só
autoriza hook mesmo pro Tug of War (Fase 7, ainda não existe), sempre com
cuidado extra de `finally`/watchdog/liberação. `GetAsyncKeyState` é só
LEITURA passiva de estado de tecla/botão (mesmo espírito das heurísticas
de `platform_windows.py` - nunca intercepta nem injeta nada), evitando
esse nível de risco pra uma conveniência.

O bit baixo de `GetAsyncKeyState` marca "foi pressionado desde a última
chamada" - mesmo cochilando entre polls (30ms), um clique curto nunca é
perdido, porque o bit fica "travado" até a próxima leitura."""
from __future__ import annotations

import win32api
import win32con

from PySide6.QtCore import QObject, QTimer, Signal

INTERVALO_POLL_MS = 30

MODIFICADORES_VK = {
    "alt": win32con.VK_MENU,
    "ctrl": win32con.VK_CONTROL,
    "shift": win32con.VK_SHIFT,
}
BOTOES_VK = {
    "esquerdo": win32con.VK_LBUTTON,
    "direito": win32con.VK_RBUTTON,
    "meio": win32con.VK_MBUTTON,
}


class ClickDestinoWatcher(QObject):
    destino_solicitado = Signal(int, int)  # posição do cursor (coordenadas de tela, globais)

    def __init__(self, modificador: str = "alt", botao: str = "esquerdo", parent: QObject | None = None):
        super().__init__(parent)
        self._vk_modificador = MODIFICADORES_VK.get(modificador, win32con.VK_MENU)
        self._vk_botao = BOTOES_VK.get(botao, win32con.VK_LBUTTON)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(INTERVALO_POLL_MS)

    def parar(self) -> None:
        self._timer.stop()

    def _poll(self) -> None:
        modificador_pressionado = bool(win32api.GetAsyncKeyState(self._vk_modificador) & 0x8000)
        botao_clicado_agora = bool(win32api.GetAsyncKeyState(self._vk_botao) & 0x0001)
        if modificador_pressionado and botao_clicado_agora:
            x, y = win32api.GetCursorPos()
            self.destino_solicitado.emit(x, y)
