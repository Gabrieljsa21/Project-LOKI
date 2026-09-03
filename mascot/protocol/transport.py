# -*- coding: utf-8 -*-
"""Framing do protocolo GAIA <-> Mascot (plano, seção 8.1) - JSON
delimitado por `\\n` sobre `QLocalSocket` (named pipe local do Windows,
nunca porta TCP). Compartilhado pelo servidor (`server.py`, roda dentro
do subprocesso Mascot) e pelo cliente (`integrations/mascot/
bridge_client.py`, roda na GAIA) pra nunca existirem duas implementações
divergentes de como as mensagens são cortadas.

Tamanho máximo por mensagem (seção 8.1: "JSON com tamanho máximo e schema
validado") - uma linha maior que isso é descartada, não trava o buffer
esperando um `\\n` que talvez nunca venha.
"""
from __future__ import annotations

import json

from PySide6.QtCore import QObject, Signal

from core.mascot_events import TAMANHO_MAXIMO_MENSAGEM_BYTES, validar_envelope

_LIMITE_BUFFER_SEM_QUEBRA = TAMANHO_MAXIMO_MENSAGEM_BYTES * 4


def enviar_mensagem(socket, mensagem: dict) -> None:
    linha = json.dumps(mensagem, ensure_ascii=False).encode("utf-8") + b"\n"
    socket.write(linha)


class LeitorDeMensagens(QObject):
    """Bufferiza os bytes que chegam por `readyRead` até fechar uma linha
    completa - `QLocalSocket` entrega dados em pedaços arbitrários, nunca
    garante 1 mensagem por sinal."""

    mensagem_recebida = Signal(dict)
    erro = Signal(str)

    def __init__(self, socket, parent: QObject | None = None):
        super().__init__(parent)
        self._socket = socket
        self._buffer = b""
        socket.readyRead.connect(self._ao_receber_dados)

    def _ao_receber_dados(self) -> None:
        self._buffer += bytes(self._socket.readAll())
        if len(self._buffer) > _LIMITE_BUFFER_SEM_QUEBRA:
            self.erro.emit("buffer excedeu o limite sem encontrar uma mensagem completa")
            self._buffer = b""
            return

        while b"\n" in self._buffer:
            linha, self._buffer = self._buffer.split(b"\n", 1)
            if not linha:
                continue
            if len(linha) > TAMANHO_MAXIMO_MENSAGEM_BYTES:
                self.erro.emit(f"mensagem descartada, excede o tamanho máximo ({len(linha)} bytes)")
                continue
            try:
                mensagem = json.loads(linha.decode("utf-8"))
                validar_envelope(mensagem)
            except Exception as exc:  # noqa: BLE001 - qualquer mensagem malformada só vira log, nunca crash
                self.erro.emit(f"mensagem malformada descartada: {exc}")
                continue
            self.mensagem_recebida.emit(mensagem)
