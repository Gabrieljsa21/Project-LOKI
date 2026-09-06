# -*- coding: utf-8 -*-
"""Preenchimento do menu "Forçar animação" - extraído (2026-09-03) de
`process_main.py::_preencher_submenu_playground` porque `menu_sao.py`
("Ações") passou a precisar do MESMO conteúdo num popup próprio; antes de
existir um 2º consumidor, essa lógica vivia só dentro de `MascotApp` e
copiá-la ali era o jeito mais rápido de expor o mesmo recurso pelo Menu
SAO - virou duplicação real assim que os dois lados precisaram do mesmo
comportamento, sem justificativa arquitetural pra manter duas cópias."""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

from mascot import state_catalog
from mascot.animation_controller import AnimationController


def ids_animacoes_validas(controller: AnimationController) -> list[str]:
    """Fonte única dos atalhos executáveis no estado lógico atual - exclui
    `state_catalog.IDS_OCULTOS_DE_SELECAO` (2026-09-05: "essa cortina
    abrindo pode remover, e a perdida tbm") - continuam válidas se pedidas
    DIRETO (`solicitar_transicao`, outros fluxos/testes as exercitam de
    propósito), só param de aparecer como opção aqui (bandeja/Menu SAO) e,
    por consequência, na Gesture Wheel (`GestureWheel.abrir` reusa isso)."""
    return sorted(
        entrada.id
        for entrada in state_catalog.transicoes_validas_a_partir_de(controller.estado_logico)
        if entrada.id not in state_catalog.IDS_OCULTOS_DE_SELECAO
    )


def preencher_menu_forcar_animacao(menu: QMenu, controller: AnimationController) -> None:
    """Só lista animações VÁLIDAS a partir do estado lógico ATUAL (mesmo
    grafo que `AnimationController.solicitar_transicao` já usa pra validar,
    `state_catalog.transicoes_validas_a_partir_de`) - nunca o catálogo
    INTEIRO (~60 ids), que incluiria "complementos" que só existem dentro
    de uma sequência (ex.: toda ação "sentada_*" tem
    `estado_origem="sentada"` - exige estar sentada primeiro). Clicar um
    complemento fora de hora já é REJEITADO em silêncio por
    `solicitar_transicao` (só loga um aviso, nada visível pro usuário) -
    pedido do usuário (2026-09-01): "Algumas animações são complementos de
    outras, n devem ser listadas ali na bandeja, ou se clicadas, tem de ser
    ativas desde o inicio do fluxo". Resolvido filtrando, não encadeando
    automaticamente - um complemento só aparece (e só fica clicável) depois
    que o usuário já disparou a transição que leva até o estado-pai dele,
    o mesmo caminho que o fluxo real de animação percorreria.

    Limpa `menu` antes de preencher - seguro chamar em cima de um `QMenu`/
    submenu já usado antes (bandeja) ou recém-criado (Menu SAO)."""
    menu.clear()
    validas = ids_animacoes_validas(controller)
    if not validas:
        acao_vazia = QAction("(nenhuma a partir do estado atual)", menu)
        acao_vazia.setEnabled(False)
        menu.addAction(acao_vazia)
        return
    for animation_id in validas:
        acao = QAction(animation_id, menu)
        acao.triggered.connect(lambda _checked=False, id_=animation_id: controller.solicitar_transicao(id_))
        menu.addAction(acao)
