# -*- coding: utf-8 -*-
"""Estado e envio da conversa do LOKI, sem criar nenhuma janela.

O ``CompanionPanel`` antigo deixou de fazer parte da interface quando o
Conversation Overlay passou a exibir composer, mensagens e histórico. Ainda
restavam nele duas responsabilidades sem relação com UI: enviar eventos pelo
bridge e manter o modo de voz usado pelo Menu SAO. Este objeto concentra só
essas responsabilidades e, por herdar de ``QObject`` em vez de ``QWidget``,
jamais cria um HWND nativo no Windows.
"""
from __future__ import annotations

import uuid

from PySide6.QtCore import QObject, Signal

from core import mascot_events


MOTIVO_SEM_CONEXAO = "Sem conexão com a GAIA (modo demonstração)."
MODOS_VOZ_CICLO = (None, "voz_continua", "click_to_talk")
MODOS_VOZ_GLIFO = {
    None: "⊘",
    "voz_continua": "◉",
    "click_to_talk": "🎙",
}
MODOS_VOZ_TEXTO = {
    None: "Voz desligada",
    "voz_continua": "Voz contínua",
    "click_to_talk": "Push-to-talk",
}
MODOS_VOZ_ROTULO = {
    modo: f"{MODOS_VOZ_GLIFO[modo]} {MODOS_VOZ_TEXTO[modo]}"
    for modo in MODOS_VOZ_CICLO
}


class ConversationService(QObject):
    """Ponte não visual entre o Conversation Overlay, o Menu SAO e a GAIA."""

    modo_voz_alterado = Signal(object)
    falha_envio = Signal(str)

    def __init__(self, bridge_provider, parent=None):
        super().__init__(parent)
        self._obter_bridge = bridge_provider
        self._modo_voz_atual = None
        # Compatibilidade temporária com diagnósticos/testes cross-repo que
        # inspecionam o eco de mensagens. Não há renderização associada.
        self._mensagens: list[tuple[str, str, object]] = []

    @property
    def modo_voz_atual(self) -> str | None:
        return self._modo_voz_atual

    def definir_modo_voz(self, modo: str | None) -> None:
        if modo not in MODOS_VOZ_CICLO:
            raise ValueError(f"Modo de voz inválido: {modo!r}")
        self._modo_voz_atual = modo
        self._enviar_evento(mascot_events.evento_voice_toggle_requested(modo))
        self.modo_voz_alterado.emit(modo)

    def ciclar_modo_voz(self) -> None:
        indice = MODOS_VOZ_CICLO.index(self._modo_voz_atual)
        self.definir_modo_voz(MODOS_VOZ_CICLO[(indice + 1) % len(MODOS_VOZ_CICLO)])

    def enviar_mensagem(self, payload: dict) -> None:
        texto = payload["texto"]
        self._registrar_mensagem("usuario", texto, payload.get("imagem_preview"))
        evento = mascot_events.evento_chat_submitted(
            uuid.uuid4().hex,
            texto,
            imagem_base64=payload.get("imagem_base64"),
            imagem_mime=payload.get("imagem_mime") or "image/jpeg",
        )
        if not self._enviar_evento(evento):
            self.falha_envio.emit(MOTIVO_SEM_CONEXAO)

    def receber_resposta(self, mensagem: dict) -> None:
        self._registrar_mensagem("gaia", mensagem.get("text", ""))

    def receber_mensagem_usuario(self, mensagem: dict) -> None:
        self._registrar_mensagem("usuario", mensagem.get("text", ""))

    def _registrar_mensagem(self, remetente: str, texto: str, imagem=None) -> None:
        self._mensagens.append((remetente, texto, imagem))
        self._mensagens = self._mensagens[-20:]

    def _enviar_evento(self, mensagem: dict) -> bool:
        bridge = self._obter_bridge()
        if bridge is None:
            self._registrar_mensagem("sistema", MOTIVO_SEM_CONEXAO)
            return False
        bridge.enviar(mensagem)
        return True
