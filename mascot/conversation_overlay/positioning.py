# -*- coding: utf-8 -*-
"""Cálculo de posição do Conversation Overlay - reescrito 2026-09-06
(correção do usuário: a v1 ancorava o `InputBar` em `GAIA.bottom + gap` e
só clampava contra a work area, nunca contra a própria GAIA - sentada na
barra de tarefas, sem espaço "abaixo", o clamp deslizava a barra de volta
pra CIMA do corpo dela).

Modelo novo, estrutural (não um ajuste de pixels):

1. `character_safe_rect` - bounding box VISÍVEL da GAIA (silhueta real,
   descontando a margem vazia do asset - mesmo truque de `menu_sao.py::
   _calcular_ancoragem`/`window.py::_geometria_halo`) + margem de
   segurança. Lida do asset ATUAL a cada chamada - acompanha pose/escala
   sozinha (flutuando/sentada/deitada/transformada/escala diferente),
   nunca hardcoded.
2. `regioes_candidatas` - 4 faixas de espaço LIVRE ao redor do safe rect
   (acima/abaixo/esquerda/direita), já recortadas pela work area
   (monitor/DPI/barra de tarefas via `platform_windows`).
3. `escolher_layout_conversa` - decide um ÚNICO lado pra bubbles+composer
   JUNTOS (nunca um de cada lado - "GAIA + bubbles + composer formam um
   pequeno sistema de layout ao redor dela"): tenta o vertical canônico
   (bubbles acima, composer abaixo - são lados OPOSTOS, cabem
   independentemente); se qualquer um dos dois não couber nesse eixo, os
   DOIS migram juntos pra uma coluna lateral única (o lado com mais
   espaço), composer perto do centro vertical dela e bubbles empilhados
   acima do composer na MESMA coluna."""
from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from mascot import platform_windows

MARGEM_SEGURANCA_PADRAO = 12  # doc, seção 1: "margem de segurança, por exemplo 8 a 16 px"
GAP_ENTRE_ELEMENTOS = 14  # respiro entre bubbles e composer quando empilhados na MESMA coluna lateral (doc, polimento 2026-09-06: "stack ↔ composer: 12-16px")


def _margem(janela, nome: str) -> float:
    asset = janela.asset_atual
    return (getattr(asset, nome) if asset else 0) * janela.escala


def limite_esquerdo_gaia(janela) -> int:
    return int(janela.x() + _margem(janela, "margem_esquerda_vazia_px"))


def limite_direito_gaia(janela) -> int:
    return int(janela.x() + janela.width() - _margem(janela, "margem_direita_vazia_px"))


def topo_visivel_gaia(janela) -> int:
    return int(janela.y() + _margem(janela, "margem_superior_vazia_px"))


def base_visivel_gaia(janela) -> int:
    return int(janela.y() + janela.height() - _margem(janela, "margem_inferior_vazia_px"))


def centro_x_gaia(janela) -> int:
    return (limite_esquerdo_gaia(janela) + limite_direito_gaia(janela)) // 2


def centro_y_gaia(janela) -> int:
    return (topo_visivel_gaia(janela) + base_visivel_gaia(janela)) // 2


def character_safe_rect(janela, margem: int = MARGEM_SEGURANCA_PADRAO) -> QRect:
    """Bounding box da GAIA + margem de segurança - NENHUM elemento da
    conversa (bubble, composer, botão) pode intersectar isto. Regra
    ESTRUTURAL do posicionador (usada por `regioes_candidatas` abaixo),
    nunca um ajuste visual pra uma pose específica."""
    esq = limite_esquerdo_gaia(janela)
    dir_ = limite_direito_gaia(janela)
    topo = topo_visivel_gaia(janela)
    base = base_visivel_gaia(janela)
    return QRect(esq - margem, topo - margem, (dir_ - esq) + 2 * margem, (base - topo) + 2 * margem)


def regioes_candidatas(janela, margem: int = MARGEM_SEGURANCA_PADRAO) -> "dict[str, QRect]":
    """4 faixas de espaço LIVRE ao redor do `character_safe_rect`, cada
    uma já recortada pela work area (`platform_windows.
    obter_work_area_da_tela` - monitor atual/DPI/barra de tarefas).
    Largura/altura zero (ou negativa, nunca) quando não sobra espaço
    nenhum desse lado - `cabe()` abaixo rejeita essas na hora."""
    tela = janela.screen() or QApplication.primaryScreen()
    area_x, area_y, area_w, area_h = platform_windows.obter_work_area_da_tela(tela)
    safe = character_safe_rect(janela, margem)
    # 🔥 CORRIGIDO (2026-09-06, achado escrevendo o teste de exclusão) -
    # `QRect.bottom()`/`.right()` são INCLUSIVOS (= top()+height()-1, ver
    # docs do Qt) - usar `safe.bottom()`/`safe.right()` como início direto
    # das faixas "abaixo"/"direita" sobrepunha a última LINHA/COLUNA do
    # safe rect por 1px (a região "abaixo" começava DENTRO dele, não
    # depois). "acima"/"esquerda" nunca tiveram esse problema (a altura/
    # largura calculada já termina uma unidade ANTES do safe rect começar).
    return {
        "acima": QRect(area_x, area_y, area_w, max(0, safe.top() - area_y)),
        "abaixo": QRect(area_x, safe.bottom() + 1, area_w, max(0, (area_y + area_h) - (safe.bottom() + 1))),
        "esquerda": QRect(area_x, area_y, max(0, safe.left() - area_x), area_h),
        "direita": QRect(safe.right() + 1, area_y, max(0, (area_x + area_w) - (safe.right() + 1)), area_h),
    }


def cabe(regiao: QRect, largura: int, altura: int) -> bool:
    return regiao.width() >= largura and regiao.height() >= altura


def eixo_perpendicular(eixo: str, regiao: QRect, janela, largura: int) -> int:
    """Coordenada no eixo PERPENDICULAR ao empilhamento - `x` pro layout
    `"vertical"` (centralizado na GAIA, clampado dentro da região - cada
    item pode ter sua PRÓPRIA largura, ex.: `IndicadorVoz` é mais estreito
    que `Bubble`) ou `x` pro layout lateral (encostado na borda da região
    mais perto da GAIA, nunca centralizado - é assim que bubble/composer
    de larguras diferentes ficam alinhados "grudados" nela, não soltos no
    meio da coluna)."""
    if eixo == "vertical":
        x = centro_x_gaia(janela) - largura // 2
        return max(regiao.left(), min(x, regiao.right() - largura + 1))
    if eixo == "esquerda":
        return regiao.right() - largura + 1
    return regiao.left()  # "direita"


def ancorar_em_regiao(lado: str, regiao: QRect, janela, largura: int, altura: int) -> "tuple[int, int]":
    """Posição final de um elemento dentro da região `lado` (`"acima"`/
    `"abaixo"`/`"esquerda"`/`"direita"`) - SEMPRE encostado na borda mais
    próxima da GAIA (o mais perto dela possível sem invadir o safe rect).
    Clampa dentro da própria região mesmo se `largura`/`altura` for maior
    que ela (degrada com elegância em telas minúsculas, nunca crasha)."""
    eixo_x = "vertical" if lado in ("acima", "abaixo") else lado
    if lado in ("acima", "abaixo"):
        x = eixo_perpendicular(eixo_x, regiao, janela, largura)
        y = (regiao.bottom() - altura + 1) if lado == "acima" else regiao.top()
        return x, max(regiao.top(), min(y, regiao.bottom() - altura + 1))
    y = centro_y_gaia(janela) - altura // 2
    y = max(regiao.top(), min(y, regiao.bottom() - altura + 1))
    x = eixo_perpendicular(eixo_x, regiao, janela, largura)
    return x, y


def escolher_layout_conversa(
    janela, largura_bubbles: int, altura_bubbles: int, largura_composer: int, altura_composer: int,
    margem: int = MARGEM_SEGURANCA_PADRAO,
) -> dict:
    """Decide o layout da CONVERSA INTEIRA (bubbles + composer sempre o
    MESMO sistema - nunca um de cada lado). Prioridade (doc, seções 4-5):

    1. Vertical canônico - bubbles ACIMA, composer ABAIXO (lados OPOSTOS
       da GAIA, cabem de forma independente um do outro);
    2. Se qualquer um dos dois não couber nesse eixo (ex.: GAIA sentada
       na barra de tarefas, zero espaço abaixo) - os DOIS migram JUNTOS
       pra uma coluna lateral única (o lado com mais espaço primeiro,
       depois o outro), empilhados na mesma coluna: composer perto do
       centro vertical dela, bubbles acima do composer;
    3. Nada coube perfeito (tela minúscula) - degrada pro vertical mesmo
       clampado (nunca quebra, só fica visualmente apertado).

    Devolve `{"eixo", "composer_pos", "bubbles_regiao", "bubbles_y_base"}`
    - `bubbles_y_base` é a borda (mais perto da GAIA) de onde `BubbleStack`
    empilha PRA CIMA; `bubbles_regiao` é a faixa onde cada bubble calcula
    seu PRÓPRIO eixo perpendicular (larguras diferentes entre `Bubble`/
    `IndicadorVoz` ficam igualmente "grudadas" na GAIA, ver
    `eixo_perpendicular`)."""
    regioes = regioes_candidatas(janela, margem)

    if cabe(regioes["acima"], largura_bubbles, altura_bubbles) and cabe(regioes["abaixo"], largura_composer, altura_composer):
        composer_pos = ancorar_em_regiao("abaixo", regioes["abaixo"], janela, largura_composer, altura_composer)
        return {
            "eixo": "vertical",
            "composer_pos": composer_pos,
            "bubbles_regiao": regioes["acima"],
            "bubbles_y_base": regioes["acima"].bottom() + 1,
        }

    maior, menor = ("esquerda", "direita") if regioes["esquerda"].width() >= regioes["direita"].width() else ("direita", "esquerda")
    largura_coluna = max(largura_bubbles, largura_composer)
    altura_coluna = altura_bubbles + GAP_ENTRE_ELEMENTOS + altura_composer
    for lado in (maior, menor):
        if cabe(regioes[lado], largura_coluna, altura_coluna):
            composer_pos = ancorar_em_regiao(lado, regioes[lado], janela, largura_composer, altura_composer)
            return {
                "eixo": lado,
                "composer_pos": composer_pos,
                "bubbles_regiao": regioes[lado],
                "bubbles_y_base": composer_pos[1] - GAP_ENTRE_ELEMENTOS + 1,
            }

    # nada coube perfeito - degrada pro vertical mesmo clampado (nunca crasha/quebra)
    composer_pos = ancorar_em_regiao("abaixo", regioes["abaixo"], janela, largura_composer, altura_composer)
    return {
        "eixo": "vertical",
        "composer_pos": composer_pos,
        "bubbles_regiao": regioes["acima"],
        "bubbles_y_base": regioes["acima"].bottom() + 1,
    }
