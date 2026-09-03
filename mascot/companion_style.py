# -*- coding: utf-8 -*-
"""Paleta mínima pro `CompanionPanel` (2026-09-01) - cópia deliberada só das
constantes de cor/fonte de `ui/qt_widgets.py` (linhas 22-31) + `cor_com_alpha`
(linha 56), NÃO um import do módulo inteiro: `ui/qt_widgets.py` importa
`brain_store`/`atualizacao` no topo (dependências do processo PRINCIPAL,
com efeito colateral no import - `DISCORD_CONFIGURADO` já lê disco na
hora), o que puxaria tudo isso pro subprocesso do Mascot, quebrando o
isolamento que `process_main.py` já mantém de propósito. Se a paleta
principal mudar, replicar aqui manualmente (baixo risco - são 6 cores)."""
from __future__ import annotations

BG_COLOR = "#0d0d0f"
SURFACE_COLOR = "#1a1a1d"
HIGHLIGHT_COLOR = "#28282c"
BORDA_SUTIL = "#2f2f34"
GAIA_GOLD = "#d4af6a"
GAIA_GOLD_HOVER = "#e3c284"
TEXT_COLOR = "#f1efe9"
TEXT_DIM = "#8f8d8a"
FONTE_BASE = "Segoe UI"


def cor_com_alpha(cor_hex, alpha):
    cor_hex = cor_hex.lstrip("#")
    r, g, b = (int(cor_hex[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"
