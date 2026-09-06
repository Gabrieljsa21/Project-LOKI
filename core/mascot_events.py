# -*- coding: utf-8 -*-
"""Eventos do protocolo GAIA <-> Mascot/LOKI (plano, seção 8). Dicts
simples e um handshake versionado - SEM Qt (seção 8.4: "core publica
eventos sem importar Qt") - pra dar pra inspecionar/rotear de qualquer
parte da GAIA sem puxar dependência de UI. O transporte de verdade
(`QLocalServer`/`QLocalSocket`) fica em `features/mascot/protocol/` (lado
subprocesso) e `integrations/mascot/bridge_client.py` (lado GAIA).

Só tem construtor/validação pros eventos que já têm consumidor real hoje
(handshake, `ready`, `heartbeat`, `state_changed`, `shutdown`, e desde o
CompanionPanel MVP 2026-09-01: `chat_submitted`, `stop_speaking_requested`,
`voice_toggle_requested`, `assistant_message`; desde 2026-09-03:
`settings_requested`, pro modal de configurações nativo do Mascot) - o
resto da tabela do plano
(seção 8.2/8.3: `user_message` ecoado de outros canais, `emotion_changed`
separado, `playback_started`/`audio_level`/`playback_finished`, `caption`,
`notice`, `mascot_clicked`) segue sem construtor de propósito, mesmo
raciocínio de "assets reais antes de arquitetura imaginária" aplicado a
protocolo - `mascot_clicked` nem precisa cruzar o pipe (clique já é local
ao subprocesso, ver `MascotWindow.clicada`), e emoção viaja dentro de
`assistant_message` em vez de evento próprio no MVP.
"""
from __future__ import annotations

VERSAO_PROTOCOLO = 1
TAMANHO_MAXIMO_MENSAGEM_BYTES = 65536

ESTADOS_SEMANTICOS_VALIDOS = frozenset(
    {"hidden", "idle", "listening", "transcribing", "thinking", "speaking", "interrupted", "error"}
)


class EventoInvalido(ValueError):
    pass


def evento_handshake(token: str) -> dict:
    return {"type": "handshake", "version": VERSAO_PROTOCOLO, "token": token}


def evento_ready(**capacidades) -> dict:
    return {"type": "ready", "version": VERSAO_PROTOCOLO, **capacidades}


def evento_heartbeat(**campos) -> dict:
    return {"type": "heartbeat", **campos}


def evento_state_changed(state: str, source: str = "gaia", emotion: str | None = None) -> dict:
    """`emotion` (opcional, 2026-09-01) - vai OMITIDO do dict quando `None`,
    pra chamadas antigas (sem emoção) continuarem produzindo o MESMO dict
    de sempre, byte a byte (compatibilidade com quem já consome este
    evento). É o humor atual (`humor_persistido.obter_humor_atual()`) -
    **histórico**: até 2026-09-01 o Mascot usava isso pra decidir a cor do
    halo; redesenhado em 2026-09-02 pro halo refletir MODO DE VOZ em vez
    disso (ver `evento_voice_mode_changed`/`features/mascot/halo.py`) -
    o campo continua sendo enviado (`core/agent/turno.py` ainda popula),
    mas o Mascot não consome mais `emotion` de `state_changed` hoje."""
    if state not in ESTADOS_SEMANTICOS_VALIDOS:
        raise EventoInvalido(f"estado semântico desconhecido: {state}")
    evento = {"type": "state_changed", "state": state, "source": source}
    if emotion is not None:
        evento["emotion"] = emotion
    return evento


def evento_shutdown(reason: str = "") -> dict:
    return {"type": "shutdown", "reason": reason}


def evento_voice_mode_changed(modo) -> dict:
    """GAIA -> Mascot (2026-09-02) - halo por modo de voz (`features/mascot/
    halo.py`, substituiu o halo por estado semântico/emoção - achado ao
    vivo: "listening" nunca era disparado por nenhum caminho real de voz,
    então o halo antigo ficava sem cor a maior parte do tempo real de
    conversa). `modo` é o MESMO vocabulário de `PainelQt.disparar_modo`/
    `evento_voice_toggle_requested` - enviado dos MESMOS 4 pontos em
    `run.py` que atribuem `PainelQt.modo_de_voz_atual`, não importa qual
    caminho mudou o modo (F6/F7/F8, CompanionPanel, Menu SAO)."""
    if modo not in VOZES_MODOS_VALIDOS:
        raise EventoInvalido(f"modo de voz desconhecido: {modo}")
    return {"type": "voice_mode_changed", "modo": modo}


VOZES_MODOS_VALIDOS = frozenset({"voz_continua", "click_to_talk", "ouvir_pc", None})


def evento_chat_submitted(id: str, text: str) -> dict:
    """Mascot -> GAIA (CompanionPanel, 2026-09-01) - texto digitado no
    CompanionPanel. `id` (uuid hex) amarra a resposta correspondente, ver
    `evento_assistant_message`."""
    return {"type": "chat_submitted", "id": id, "text": text}


def evento_stop_speaking_requested() -> dict:
    """Mascot -> GAIA - botão "Parar" do CompanionPanel. Sem payload -
    cancela a fala em andamento, não importa o canal que a iniciou."""
    return {"type": "stop_speaking_requested"}


def evento_voice_toggle_requested(desired_state) -> dict:
    """Mascot -> GAIA - botão de microfone do CompanionPanel. `desired_state`
    é o mesmo vocabulário de `PainelQt.disparar_modo` (`run.py`):
    `voz_continua`/`click_to_talk`/`ouvir_pc`/`None` (desligar)."""
    if desired_state not in VOZES_MODOS_VALIDOS:
        raise EventoInvalido(f"modo de voz desconhecido: {desired_state}")
    return {"type": "voice_toggle_requested", "desired_state": desired_state}


def evento_settings_requested() -> dict:
    """GAIA -> Mascot (botão "🧚 Mascot (LOKI)" do Painel, 2026-09-03,
    revisado no mesmo dia) - pede pro Mascot mostrar o PRÓPRIO modal
    nativo de configurações (`mascot/modal_configuracoes.py`, Project
    LOKI - fonte única desde que ele passou a rodar dentro do processo do
    Mascot). A GAIA não pode instanciar esse QWidget direto (processo
    separado), só pedir que o outro lado mostre o dele. Sem payload."""
    return {"type": "settings_requested"}


def evento_user_message(id: str, text: str, channel: str = "voz") -> dict:
    """GAIA -> Mascot (2026-09-01, achado ao vivo: "falou no modo de voz, mas
    não apareceu no CompanionPanel") - eco de um turno que NÃO veio do
    CompanionPanel (voz contínua, clique-pra-falar, chat de texto do Painel
    principal) - `channel` identifica a origem só pra debug/exibição, nunca
    pra lógica. Discord fica de fora de propósito (plano, seção 8.4: "Discord/
    visitantes não fazem a janela pessoal aparecer"). O CompanionPanel nunca
    manda isso de volta pra si mesmo - o eco do que ELE MESMO envia já é
    local, imediato (`_enviar`), sem round-trip; só `run.py` emite este
    evento, nos outros pontos de entrada de turno."""
    return {"type": "user_message", "id": id, "text": text, "channel": channel}


def evento_assistant_message(id: str, text: str, emotion: str = "neutro", final: bool = True) -> dict:
    """GAIA -> Mascot - resposta de um `chat_submitted` (mesmo `id`) pro
    CompanionPanel exibir. `emotion` vem de `humor_persistido.obter_humor_atual()`
    (ver `core/agent/turno.py`), texto puro (sem parse de Markdown no MVP)."""
    return {"type": "assistant_message", "id": id, "text": text, "emotion": emotion, "final": final}


def validar_envelope(mensagem: object) -> str:
    """Confere só o mínimo comum a QUALQUER mensagem (é um dict com
    `type` string) - validação de campo específico por tipo de evento
    fica em quem trata cada um. Devolve o `type` já confirmado, ou
    levanta `EventoInvalido`."""
    if not isinstance(mensagem, dict):
        raise EventoInvalido("mensagem não é um objeto JSON")
    tipo = mensagem.get("type")
    if not isinstance(tipo, str) or not tipo:
        raise EventoInvalido("mensagem sem campo 'type' válido")
    return tipo
