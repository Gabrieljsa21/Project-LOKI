# -*- coding: utf-8 -*-
"""Conversation Overlay (Project LOKI, 2026-09-06) - conversa ao redor da
própria GAIA (bubbles + input flutuante), em vez do `CompanionPanel`
tradicional abrir como painel grande por padrão. Ver `docs/ARQUITETURA.md`,
seção "Conversation Overlay", pro desenho completo.

Pacote deliberadamente separado de `mascot/window.py`/`mascot/process_main.py`
(pedido do usuário: "evitar acoplar toda essa lógica diretamente em
window.py") - só consome sinais/helpers que já existem
(`platform_windows`, `MascotWindow.arraste_iniciado`, `SafetyController`,
`CompanionPanel`), nunca duplica cálculo de monitor/DPI/work area.
"""
