# -*- coding: utf-8 -*-
"""SafetyController do Mascot/LOKI (plano, seção 11 - Segurança Windows).

Só decide SE autonomia é permitida agora; quem usa essa decisão (parar
comportamentos, permitir click-through) fica no `behavior_scheduler`/
`window`. Checagem por polling (`QTimer`), não hook - o plano proíbe
`BlockInput` e só permite um hook (mouse) futuro no Tug of War (Fase 7,
fora de escopo aqui), sempre com `finally`/watchdog.

**Bloqueio por interação (2026-09-02, `GAIA_MENU_SAO.md`)** - além da
checagem por polling (tela cheia/jogo/RDP/desktop seguro), qualquer
componente de UI que exija ESTABILIDADE de posição enquanto está aberto
(CompanionPanel, Menu SAO) pode registrar um bloqueio próprio via
`bloquear_autonomia(motivo)`/`liberar_autonomia(motivo)`. Deliberadamente
um CONJUNTO de motivos, não um bool único - se dois componentes
bloquearem ao mesmo tempo (ex.: CompanionPanel E Menu SAO abertos juntos)
e um deles liberar, o outro ainda precisa segurar o bloqueio. Hierarquia
conceitual (interação do usuário > autonomia): enquanto qualquer motivo
estiver no conjunto, `autonomia_permitida` é `False` independente do que
o polling de tela cheia/jogo diga."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from mascot import platform_windows

INTERVALO_CHECAGEM_MS = 2000


class SafetyController(QObject):
    autonomia_alterada = Signal(bool)  # True = autonomia permitida agora

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._pausar_por_plataforma = False  # último resultado do polling (tela cheia/jogo/RDP/desktop seguro)
        self._bloqueios_interacao: set[str] = set()
        self._autonomia_permitida = True

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._checar)
        self._timer.start(INTERVALO_CHECAGEM_MS)

    @property
    def autonomia_permitida(self) -> bool:
        return self._autonomia_permitida

    def bloquear_autonomia(self, motivo: str) -> None:
        """Chamado por um componente de UI (CompanionPanel/Menu SAO) que
        acabou de abrir e precisa que ela fique parada enquanto isso."""
        self._bloqueios_interacao.add(motivo)
        self._recalcular()

    def liberar_autonomia(self, motivo: str) -> None:
        """`discard` (não `remove`) - liberar um motivo que já não estava
        bloqueando (ex.: `hideEvent` disparado 2x) nunca deve estourar."""
        self._bloqueios_interacao.discard(motivo)
        self._recalcular()

    def _checar(self) -> None:
        self._pausar_por_plataforma = platform_windows.deve_pausar_autonomia()
        self._recalcular()

    def _recalcular(self) -> None:
        permitida = not self._pausar_por_plataforma and not self._bloqueios_interacao
        if permitida != self._autonomia_permitida:
            self._autonomia_permitida = permitida
            self.autonomia_alterada.emit(permitida)
