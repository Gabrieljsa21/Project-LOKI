"""Receptor local dos eventos ``siren.playback.v1``."""

from __future__ import annotations

import json
import os
import socket
import threading

from PySide6.QtCore import QObject, Signal

PORTA_PADRAO = 8771
TIPOS = {"track_started", "playback_paused", "playback_resumed", "progress", "track_ended"}


def validar_evento(dados):
    if not isinstance(dados, dict) or dados.get("schema") != "siren.playback.v1":
        return None
    if dados.get("type") not in TIPOS:
        return None
    sessao = dados.get("session_id")
    # 🔥 Achado na revisão (2026-09-07) - `session_id` só era checado por
    # truthiness, não por tipo: um pacote UDP malformado com
    # `"session_id": ["algo"]` (JSON válido, lista não-vazia = truthy)
    # passava aqui e depois quebrava `_ultima_sequencia.get(sessao, ...)`
    # com `TypeError: unhashable type: 'list'`, matando a thread receptora
    # em silêncio (sem derrubar o processo, mas o recurso parava de
    # funcionar pro resto da sessão). Exigir str/int garante que o valor é
    # hashable antes de usar como chave do dict.
    if not isinstance(sessao, (str, int)) or not sessao or not isinstance(dados.get("sequence"), int):
        return None
    return dados


class ReceptorPlayback(QObject):
    evento_recebido = Signal(dict)

    def __init__(self, host="127.0.0.1", porta=None, parent=None):
        super().__init__(parent)
        self.host = host
        self.porta = int(porta or os.getenv("LOKI_PLAYBACK_EVENT_PORT", PORTA_PADRAO))
        self._socket = None
        self._thread = None
        self._parar = threading.Event()
        self._ultima_sequencia = {}

    def iniciar(self):
        if self._thread and self._thread.is_alive():
            return True
        try:
            canal = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            canal.settimeout(0.5)
            canal.bind((self.host, self.porta))
        except OSError as erro:
            print(f" [LOKI] Eventos do SIREN indisponíveis na porta {self.porta}: {erro}")
            return False
        self._socket = canal
        self._parar.clear()
        self._thread = threading.Thread(target=self._receber, daemon=True, name="loki-siren-events")
        self._thread.start()
        return True

    def _receber(self):
        while not self._parar.is_set():
            try:
                pacote, _origem = self._socket.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                evento = validar_evento(json.loads(pacote.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if evento is None:
                continue
            sessao = evento["session_id"]
            sequencia = evento["sequence"]
            if sequencia <= self._ultima_sequencia.get(sessao, 0):
                continue
            self._ultima_sequencia[sessao] = sequencia
            self.evento_recebido.emit(evento)

    def encerrar(self):
        self._parar.set()
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
