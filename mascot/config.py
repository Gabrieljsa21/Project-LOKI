# -*- coding: utf-8 -*-
"""Configuração do Mascot/LOKI. Lida direto de `data/mascot_config.json`
(raw json), próprio deste repositório desde a extração de 2026-09-03
(`Project-LOKI`, antes vivia em `data/brain.json` da GAIA) - o Painel da
GAIA ("🧚 Mascot (LOKI)") lê/escreve o MESMO arquivo direto pelo caminho
(`integrations/mascot_config_client.py` do lado da GAIA), sem import
Python cruzando repositórios.
"""
from __future__ import annotations

import json
from pathlib import Path

CAMINHO_CONFIG = Path(__file__).resolve().parents[1] / "data" / "mascot_config.json"

MASCOT_PADRAO = {
    "enabled": True,
    "autonomy": "subtle",  # parada | subtle | viva | travessuras
    "always_on_top": True,
    "click_through_when_idle": False,
    "reduce_motion": False,
    "pause_in_fullscreen": True,
    "opacity": 1.0,
    "scale": 1.0,
    # Lista de QScreen.name() (ex.: "Hailstorm", "25UM58G") - vazia = todos
    # os monitores conectados valem. Substitui o `stay_on_current_monitor`
    # binário que o plano original previa (seção 12) por algo mais
    # granular, a pedido do usuário (2026-08-29: "tem que ser configurável
    # quais monitores ele pode ficar").
    "monitores_permitidos": [],
    # Hotkey de "ir até aqui" (seção 8.3 do plano ainda não previa isso -
    # pedido do usuário, 2026-08-29). Só o combo modificador+botão do
    # mouse; sem tecla extra nenhuma além do modificador, de propósito
    # (mais simples que um atalho de teclado completo).
    "hotkey_destino_ativo": True,
    "hotkey_destino_modificador": "alt",  # alt | ctrl | shift
    "hotkey_destino_botao": "esquerdo",  # esquerdo | direito | meio
    # Multiplicador de velocidade de voo (pedido do usuário, 2026-08-29:
    # "tem como deixar ela mais rápida?") - escala quanto CHÃO cada volta
    # do loop cobre (`DISTANCIA_POR_CICLO_LOOP_PX` em
    # `behavior_scheduler.py`), não o ritmo do bater de asas/pernas do
    # clipe em si. 1.0 = 100% (calibração original) - escolhível na
    # bandeja do sistema (`process_main.py::_montar_submenu_velocidade`)
    # de 100% a 500% em passos de 100, persistindo a cada troca (pedido
    # do usuário, 2026-08-29: "tem que persistir" - via
    # `salvar_config_mascot`, diferente do resto de `mascot_config` que
    # ainda só vale pra sessão). 2.0 (200%) é só o padrão de fábrica pra
    # quem nunca mexeu no menu ainda.
    "velocidade_voo": 2.0,
    # Ociosidade REAL de teclado/mouse antes dela fingir dormir (pedido
    # do usuário, 2026-08-29: "quero que ela reconheça quando estou afk,
    # pra por a GAIA pra dormir") - `platform_windows.obter_segundos_ociosos`,
    # NADA a ver com "tempo sem falar com a GAIA" (Avatar Virtual/
    # Hidratação usam outro contador, sobre conversa). Só efeito VISUAL
    # (a Galateia flutuante finge dormir) - escopo pedido pelo usuário
    # explicitamente exclui pausar qualquer função real da GAIA.
    "afk_minutos": 10,
    # CompanionPanel MVP (2026-09-01) - hotkey global registrado DIRETO no
    # subprocesso (lib `keyboard`, mesma já usada em `run.py`/no antigo
    # `vtuber_overlay.py`) - funciona mesmo em modo demonstração, sem GAIA
    # rodando. Sugestão do plano (seção 9.1), "sempre configurável".
    "companion_panel_shortcut": "ctrl+shift+space",
    # Menu SAO (2026-09-02) - estilo visual do botão hover-expand
    # (`mascot/menu_sao.py::ESTILOS`) - "vidro" (translúcido)
    # escolhido pelo usuário entre as 4 opções mostradas num artifact de
    # comparação; os outros 3 ficam disponíveis pra troca no Painel
    # ("classico" | "vidro" | "selo" | "aurora").
    "menu_sao_estilo": "vidro",
    # Orçamento de memória do cache de animações em MB decodificados de
    # verdade, não o tamanho comprimido do arquivo (`AssetRepository`,
    # `mascot/asset_repository.py::ORCAMENTO_MEMORIA_PADRAO_MB`) -
    # até aqui só um valor fixo no código (320MB, calibrado medindo ao
    # vivo - ver `C:\Workspace\Project LOKI.md`, Achados 4/5 da Fase 5).
    # Pedido do usuário, 2026-09-02: "coloca aqueles limites de memoria e
    # tudo p ser configuravel" - exposto no Painel ("🧚 Mascot (LOKI)" →
    # Desempenho).
    "memoria_orcamento_mb": 320.0,
}

BEHAVIORS_PADRAO = {
    "taskbar_sit": True,
    "sitting_variations": True,
    "wander": True,  # validado ao vivo em 2026-08-28 (sit/stand/wander sem erro) - ligado por pedido do usuário
    "cursor_swing": False,
    "cursor_hunt": False,
    "tug_of_war": False,
}


def _ler_config() -> dict:
    try:
        with open(CAMINHO_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def carregar_config_mascot() -> dict:
    """Config inválida ou ausente volta ao padrão seguro (plano, seção 12) -
    nunca propaga um valor parcialmente corrompido pro resto do Mascot."""
    salvo = _ler_config().get("mascot_config", {})
    config = dict(MASCOT_PADRAO)
    if isinstance(salvo, dict):
        for chave in MASCOT_PADRAO:
            if chave in salvo and isinstance(salvo[chave], type(MASCOT_PADRAO[chave])):
                config[chave] = salvo[chave]
    return config


def salvar_config_mascot(atualizacoes: dict) -> None:
    """Lê-modifica-escreve PARCIAL (só as chaves em `atualizacoes` mudam,
    o resto de `mascot_config` e do `data/mascot_config.json` fica
    intocado). Falha silenciosa se o disco não deixar escrever - a
    escolha só fica valendo pra sessão atual nesse caso, em vez de
    derrubar o Mascot por um erro de I/O num toggle de menu."""
    dados = _ler_config()
    config_salvo = dados.get("mascot_config")
    if not isinstance(config_salvo, dict):
        config_salvo = {}
    config_salvo.update(atualizacoes)
    dados["mascot_config"] = config_salvo
    try:
        with open(CAMINHO_CONFIG, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)
    except OSError:
        pass


def carregar_config_behaviors() -> dict:
    salvo = _ler_config().get("mascot_behaviors_config", {})
    config = dict(BEHAVIORS_PADRAO)
    if isinstance(salvo, dict):
        for chave in BEHAVIORS_PADRAO:
            if chave in salvo and isinstance(salvo[chave], bool):
                config[chave] = salvo[chave]
    return config


def salvar_config_behaviors(atualizacoes: dict) -> None:
    """Mesmo padrão de `salvar_config_mascot` (leia a docstring lá) - lê-
    modifica-escreve PARCIAL só em `mascot_behaviors_config`, usado pelo
    Painel (`ui/qt_modais/mascot.py`)."""
    dados = _ler_config()
    config_salvo = dados.get("mascot_behaviors_config")
    if not isinstance(config_salvo, dict):
        config_salvo = {}
    config_salvo.update(atualizacoes)
    dados["mascot_behaviors_config"] = config_salvo
    try:
        with open(CAMINHO_CONFIG, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)
    except OSError:
        pass
