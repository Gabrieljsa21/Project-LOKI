# -*- coding: utf-8 -*-
"""MascotBridgeServer (plano, seção 8.1) - roda DENTRO do subprocesso
Mascot, aceita a conexão da GAIA (`integrations/mascot/bridge_client.py`)
por named pipe local (`QLocalServer`), confere o token efêmero e a versão
no handshake antes de aceitar qualquer evento de verdade.

Só 1 cliente por vez - não existe cenário de duas GAIAs falando com o
mesmo Mascot, uma segunda tentativa de conexão é fechada na hora.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer

from core import mascot_events
from mascot.protocol.transport import LeitorDeMensagens, enviar_mensagem

logger = logging.getLogger(__name__)


class MascotBridgeServer(QObject):
    evento_recebido = Signal(dict)  # só eventos JÁ autenticados (pós-handshake)
    cliente_conectado = Signal()
    cliente_desconectado = Signal()

    def __init__(self, nome_canal: str, token: str, parent: QObject | None = None):
        super().__init__(parent)
        self._token = token
        self._socket = None
        self._leitor = None
        self._handshake_ok = False

        QLocalServer.removeServer(nome_canal)  # limpa socket órfão de uma execução anterior que crashou
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._ao_nova_conexao)
        if not self._server.listen(nome_canal):
            raise RuntimeError(f"não consegui abrir o canal local '{nome_canal}': {self._server.errorString()}")

    @property
    def cliente_autenticado(self) -> bool:
        return self._handshake_ok

    def _ao_nova_conexao(self) -> None:
        if self._socket is not None:
            conexao_extra = self._server.nextPendingConnection()
            conexao_extra.close()
            return
        self._socket = self._server.nextPendingConnection()
        self._socket.disconnected.connect(self._ao_desconectar)
        self._leitor = LeitorDeMensagens(self._socket, parent=self)
        self._leitor.mensagem_recebida.connect(self._ao_receber)
        self._leitor.erro.connect(lambda msg: logger.warning("Mascot bridge (servidor): %s", msg))

    def _ao_receber(self, mensagem: dict) -> None:
        if not self._handshake_ok:
            self._processar_handshake(mensagem)
            return
        self.evento_recebido.emit(mensagem)

    def _processar_handshake(self, mensagem: dict) -> None:
        valido = (
            mensagem.get("type") == "handshake"
            and mensagem.get("token") == self._token
            and mensagem.get("version") == mascot_events.VERSAO_PROTOCOLO
        )
        if not valido:
            logger.warning("Mascot bridge (servidor): handshake inválido, encerrando conexão")
            self._socket.close()
            return
        self._handshake_ok = True
        self.enviar(mascot_events.evento_ready())
        self.cliente_conectado.emit()

    def enviar(self, mensagem: dict) -> None:
        if self._socket is not None and self._handshake_ok:
            enviar_mensagem(self._socket, mensagem)

    def _ao_desconectar(self) -> None:
        self._socket = None
        self._leitor = None
        self._handshake_ok = False
        self.cliente_desconectado.emit()

    def fechar(self) -> None:
        if self._socket is not None:
            self._socket.close()
        self._server.close()
