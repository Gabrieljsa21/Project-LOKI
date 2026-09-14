# -*- coding: utf-8 -*-
"""Paleta PRÓPRIA do Conversation Overlay (2026-09-06) - deliberadamente
SEPARADA de `mascot/companion_style.py` (preto/dourado, usada pelo
`CompanionPanel` tradicional) - o pedido do usuário foi por uma
identidade "navy/cristal/ciano/dourado discreto", distinta da paleta
antiga; misturar as duas arriscava o visual do painel tradicional (já
testado ao vivo) sem necessidade. Reaproveita só `GAIA_GOLD` do
`companion_style` (mesmo dourado de identidade em TODO o LOKI - Menu SAO,
CompanionPanel, agora aqui), o resto é palette nova.

Nenhum QSS de widget nativo aqui (menu/janela do Qt) - os bubbles/pílulas
são pintados à mão (`QPainter`, cantos arredondados, borda fina, glow
pintado à mão também - `_BolhaBase._desenhar_glow`, NUNCA
`QGraphicsEffect`, ver docstring de `bubble.py` sobre o achado de
2026-09-06), mesma técnica de `menu_sao.py::_CirculoMenu` e `halo.py` -
só o `QLineEdit` real do `InputBar` precisa de widget nativo (teclado/
IME), estilizado por QSS pra não ter nenhuma aparência de chrome padrão
do Qt (sem borda quadrada, sem fundo cinza claro).

**Hierarquia de cor - revertida (2026-09-07)**: a correção de 2026-09-06
("o ciano deve ser destaque, não a cor de todas as superfícies") tinha
dado à GAIA uma borda NEUTRA própria (`BORDA_NEUTRA`, removida nesta
revisão), reservando cristal só pro usuário. O usuário mostrou uma
referência visual pedindo o layout novo do Bubble Mode ("queria que
ficasse assim") com as DUAS bordas no mesmo brilho ciano vívido - a
identidade própria da GAIA passou a vir do retrato (`bubble.py`, fora do
balão, com o próprio anel dourado/azul do arquivo), não mais do contorno,
então a borda pôde voltar a ser cristal pros dois lados sem perder
diferenciação."""
from __future__ import annotations

from mascot.companion_style import GAIA_GOLD, cor_com_alpha

# Base (doc, seção 11) - do mais escuro (fundo geral/bubble da GAIA) ao
# mais claro (superfícies/bubble do usuário).
FUNDO_1 = "#0B111B"
FUNDO_2 = "#101824"
FUNDO_3 = "#141C28"

# Azul cristal/ciano - cor de INTERAÇÃO/FOCO (borda dos bubbles, glow,
# indicador de voz), nunca fundo sólido grande (doc: "evitar excesso de
# neon").
CRISTAL = "#4FD7E8"
CRISTAL_GLOW = "#3AC8DC"  # levemente mais escuro, usado só no glow (evita halo "lavado")

DOURADO = GAIA_GOLD  # "#d4af6a" - MESMO dourado do resto do LOKI, de propósito

TEXTO_PRINCIPAL = "#EAF2F6"  # quase branco
TEXTO_SECUNDARIO = "#8CA2B3"  # azul-cinza

ERRO = "#E0736B"  # só usado quando realmente necessário (doc, seção 11) - ex.: sem conexão com a GAIA

RAIO_BUBBLE = 14
RAIO_INPUT = 20  # pílula mais arredondada que o bubble, achado visual: input compacto pede cantos mais fechados que um retângulo de texto


def cor_fundo_translucido(cor_hex: str, alpha: float = 0.90) -> str:
    """Transparência CONTROLADA (doc, seção 11: "blur/transparência
    sutil... evitar excesso") - alpha alto o bastante pra nunca comprometer
    legibilidade do texto por cima da área de trabalho do usuário."""
    return cor_com_alpha(cor_hex, alpha)
