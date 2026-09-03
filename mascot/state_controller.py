# -*- coding: utf-8 -*-
"""StateController do Mascot/LOKI (plano, seções 5.2/8.2) - traduz um
ESTADO SEMÂNTICO (`idle`, `listening`, `thinking`, ...; hoje só disparado
pelo playground, na Fase 3 vem de eventos reais da GAIA) num pedido de
transição pro `AnimationController`. Nunca escolhe animação incompatível
com a pose atual (flutuando/sentada) - isso já é validado pelo grafo em
`state_catalog`, este módulo só decide qual clipe FAZ SENTIDO pedir.

Vários estados do plano ainda não têm clipe próprio (`listening`,
`transcribing`, `speaking`, `interrupted`, `error`, `notice`) - a ideia do
plano pra esses é um efeito auxiliar (halo/partícula, seção 5.2/9), não um
sprite novo. Sem esse efeito ainda implementado (Fase 5), pedir uma
transição de verdade pra eles seria inventar uma pose que não representa
o estado - por isso só ATUALIZAM `estado_semantico_atual` (pra quando o
efeito existir) e não tocam a animação. `idle`/`thinking` já têm clipe
real hoje e são os únicos que de fato trocam o quadro.
"""
from __future__ import annotations

from mascot.animation_controller import AnimationController

ESTADOS_SEM_CLIPE_PROPRIO = frozenset(
    # "hidden" (plano, seção 5.1) é sobre VISIBILIDADE da janela, não sobre
    # qual animação tocar - fica de fora da escolha de clipe de propósito,
    # quem decide esconder/mostrar é o MascotApp, não este módulo.
    {"hidden", "listening", "transcribing", "speaking", "interrupted", "error", "notice"}
)


class StateController:
    def __init__(self, controller: AnimationController):
        self._controller = controller
        self.estado_semantico_atual = "idle"

    def definir_estado_semantico(self, estado: str) -> None:
        self.estado_semantico_atual = estado

        if estado == "idle":
            if self._controller.estado_logico == "sentada":
                self._controller.solicitar_transicao("sentada_balancando-pernas")
            else:
                self._controller.solicitar_transicao("flutuando_idle")
            return

        if estado == "thinking":
            if self._controller.estado_logico == "sentada":
                self._controller.solicitar_transicao("sentada_pensando")
            return  # flutuando: sem clipe de pensamento próprio ainda (ver docstring)

        if estado in ESTADOS_SEM_CLIPE_PROPRIO:
            return

        raise ValueError(f"estado semântico desconhecido: {estado}")
