# -*- coding: utf-8 -*-
"""Entrypoint do subprocesso Galateia Mascot (plano, seção 6.2). Roda como
processo separado (`python -m mascot.process_main`, lançado
manualmente em desenvolvimento ou pelo `MascotSupervisor` a partir da
GAIA) - sem `QApplication` nenhuma no processo principal da GAIA (seção
6.1).

`GAIA_MASCOT_CANAL`/`GAIA_MASCOT_TOKEN` (variáveis de ambiente, nunca
argv - ver `integrations/mascot/supervisor.py`) ligam o `MascotBridgeServer`
se estiverem presentes; sem elas, roda em "modo demonstração" sozinho
(plano, seção 2: "funcione em modo demonstração sem iniciar a GAIA") -
é assim que rodei manualmente o tempo todo até aqui. A bandeja do sistema
continua sendo o playground ("forçar clipe e sequência") até o
CompanionPanel existir.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import keyboard

RAIZ_APP = Path(__file__).resolve().parents[1]
if str(RAIZ_APP) not in sys.path:
    sys.path.insert(0, str(RAIZ_APP))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from core import mascot_events
from mascot import config, state_catalog
from mascot.animation_controller import AnimationController
from mascot.asset_repository import AssetRepository
from mascot.behavior_scheduler import BehaviorScheduler
from mascot.click_destino import ClickDestinoWatcher
from mascot.companion_panel import CompanionPanel
from mascot.menu_sao import MenuSAO
from mascot.protocol.server import MascotBridgeServer
from mascot.safety import SafetyController
from mascot.state_controller import StateController
from mascot.window import MascotWindow

VAR_AMBIENTE_CANAL = "GAIA_MASCOT_CANAL"
VAR_AMBIENTE_TOKEN = "GAIA_MASCOT_TOKEN"
INTERVALO_HEARTBEAT_MS = 5000
# Sem isso, um subprocesso "amarrado" (com canal/token - ver
# `_montar_bridge`) sobrevivia pra sempre depois da GAIA morrer sem
# avisar (`taskkill`/crash/restart do watchdog nunca chamam
# `MascotSupervisor.encerrar()`, que é a única coisa que mata a árvore
# de verdade) - a próxima GAIA sobe um Mascot NOVO com canal/token
# diferente, e o órfão antigo fica pra sempre flutuando junto (bug real
# reportado pelo usuário, 2026-08-29: "às vezes abre vários mascotes").
# 30s pra conectar pela 1ª vez cobre um handshake lento; 20s de graça
# depois de um `cliente_desconectado` cobre uma soneca/reconexão real no
# MESMO canal (a GAIA reconectando sozinha) sem se confundir com "a GAIA
# sumiu de vez" - como cada `MascotSupervisor.iniciar()` gera canal/token
# NOVOS, não existe cenário de uma GAIA diferente reconectar no canal de
# um órfão, então esse tempo só protege contra um soluço passageiro.
TIMEOUT_PRIMEIRA_CONEXAO_MS = 30_000
TIMEOUT_RECONEXAO_MS = 20_000


class MascotApp:
    def __init__(self):
        self.config_mascot = config.carregar_config_mascot()
        self.config_behaviors = config.carregar_config_behaviors()

        self.repositorio = AssetRepository(orcamento_mb=self.config_mascot["memoria_orcamento_mb"])
        self.controller = AnimationController(repositorio=self.repositorio)
        self.estados = StateController(self.controller)
        self.window = MascotWindow(self.controller, escala=self.config_mascot["scale"])
        self.window.setWindowOpacity(self.config_mascot["opacity"])
        self.window.definir_click_through(self.config_mascot["click_through_when_idle"])

        self.safety = SafetyController()
        self.scheduler = BehaviorScheduler(
            self.controller,
            self.window,
            self.repositorio,
            self.safety,
            self.config_mascot,
            self.config_behaviors,
        )
        # arraste manual real precisa cancelar física/perseguição autônoma
        # em andamento - pedido do usuário, 2026-08-29: "quando eu segurar
        # ela, tem de interromper na hora a animação atual".
        self.window.arraste_iniciado.connect(self.scheduler.interromper_para_arraste)
        self.window.arraste_finalizado.connect(self.scheduler.retomar_apos_arraste)

        self.click_destino = self._montar_click_destino()
        self.tray = self._montar_tray()

        # 🔥 CompanionPanel (Fase 4 MVP, 2026-09-01) - `bridge_provider` é um
        # lambda (não a referência direta) porque `self.bridge` só é
        # atribuído mais abaixo (`_montar_bridge`, pode até ficar `None` em
        # modo demonstração) - o lambda sempre lê o valor ATUAL no momento
        # de enviar, nunca uma cópia antiga.
        self.companion_panel = CompanionPanel(self.window, lambda: self.bridge, self.safety)
        self.window.clicada.connect(self.companion_panel.alternar_visibilidade_solicitado.emit)
        self._registrar_hotkey_companion_panel()

        # 🔥 Menu SAO (2026-09-02, `GAIA_MENU_SAO.md`) - camada ADICIONAL,
        # não substitui o clique direto acima ("Conversar" é redundante de
        # propósito, ver docstring de `menu_sao.py`). Arraste real sempre
        # fecha o menu na hora (`imediato=True` - sem animação, o usuário já
        # está com a mão nela), mesmo sinal que já interrompe física/Wander
        # (`scheduler.interromper_para_arraste`, acima).
        self.menu_sao = MenuSAO(
            self.window, self.safety, self.companion_panel,
            estilo_id=self.config_mascot.get("menu_sao_estilo", "vidro"),
        )
        self.window.scroll_baixo_confirmado.connect(self.menu_sao.abrir)
        self.window.scroll_cima_confirmado.connect(self.menu_sao.fechar)
        self.window.arraste_iniciado.connect(lambda: self.menu_sao.fechar(imediato=True))

        self.bridge = self._montar_bridge()

        self.window.show()

    def _registrar_hotkey_companion_panel(self) -> None:
        """Hotkey global registrado DIRETO neste subprocesso (lib `keyboard`,
        mesma já usada em `run.py`/no antigo `vtuber_overlay.py`) - funciona
        mesmo em modo demonstração, sem GAIA rodando. O callback do
        `keyboard` roda numa thread PRÓPRIA da lib, nunca na do Qt - por
        isso emite `alternar_visibilidade_solicitado` (sinal, thread-safe)
        em vez de chamar `alternar_visibilidade()` direto (ver docstring do
        sinal em `companion_panel.py`)."""
        atalho = self.config_mascot.get("companion_panel_shortcut")
        if not atalho:
            return
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            # 🔥 Nunca registra hook global de teclado DE VERDADE em teste
            # automatizado (`QT_QPA_PLATFORM=offscreen`, mesmo sinal que
            # `testes/testar_mascot_*.py` já usa pra rodar sem tela) - um
            # `MascotApp()` construído em teste não pode deixar um hotkey
            # do sistema inteiro pra trás sem limpar.
            return
        try:
            keyboard.add_hotkey(atalho, self.companion_panel.alternar_visibilidade_solicitado.emit)
        except Exception as e:
            # 🔥 Falha isolada (plano, seção 4, princípio 6) - um atalho
            # inválido/conflitante nunca deve impedir o resto do Mascot de
            # subir; ainda dá pra abrir o CompanionPanel clicando na
            # personagem.
            print(f" [LOKI] Não consegui registrar o atalho do CompanionPanel ({atalho}): {e}")

    def _montar_click_destino(self) -> ClickDestinoWatcher | None:
        """"Ir até aqui" (pedido do usuário, 2026-08-29) - padrão Alt +
        clique esquerdo, configurável em `mascot_config` (sem Painel
        ainda, só editando `data/mascot_config.json` por enquanto)."""
        if not self.config_mascot["hotkey_destino_ativo"]:
            return None
        watcher = ClickDestinoWatcher(
            modificador=self.config_mascot["hotkey_destino_modificador"],
            botao=self.config_mascot["hotkey_destino_botao"],
        )
        watcher.destino_solicitado.connect(lambda x, y: self.scheduler.ir_para_destino(x, y))
        return watcher

    def _montar_bridge(self) -> MascotBridgeServer | None:
        canal = os.environ.get(VAR_AMBIENTE_CANAL)
        token = os.environ.get(VAR_AMBIENTE_TOKEN)
        if not canal or not token:
            return None  # modo demonstração - sem GAIA nenhuma pra conectar
        bridge = MascotBridgeServer(canal, token)
        bridge.evento_recebido.connect(self._processar_evento_gaia)
        bridge.cliente_conectado.connect(self._cancelar_watchdog_orfao)
        bridge.cliente_desconectado.connect(self._agendar_watchdog_orfao)
        self._agendar_watchdog_orfao(TIMEOUT_PRIMEIRA_CONEXAO_MS)

        # heartbeat é o Mascot quem manda (plano, seção 8.3) - só ele sabe
        # fps/animação atual; a GAIA só recebe, nunca pede.
        timer_heartbeat = QTimer()
        timer_heartbeat.timeout.connect(self._enviar_heartbeat)
        timer_heartbeat.start(INTERVALO_HEARTBEAT_MS)
        self._timer_heartbeat = timer_heartbeat  # referência precisa sobreviver (mesmo motivo do mascot_app em main())

        return bridge

    def _agendar_watchdog_orfao(self, timeout_ms: float = TIMEOUT_RECONEXAO_MS) -> None:
        self._cancelar_watchdog_orfao()
        self._timer_watchdog_orfao = QTimer()
        self._timer_watchdog_orfao.setSingleShot(True)
        self._timer_watchdog_orfao.timeout.connect(self._encerrar_se_orfao)
        self._timer_watchdog_orfao.start(timeout_ms)

    def _cancelar_watchdog_orfao(self) -> None:
        timer = getattr(self, "_timer_watchdog_orfao", None)
        if timer is not None:
            timer.stop()

    def _encerrar_se_orfao(self) -> None:
        if self.bridge is not None and not self.bridge.cliente_autenticado:
            QApplication.quit()

    def _enviar_heartbeat(self) -> None:
        self.bridge.enviar(
            mascot_events.evento_heartbeat(
                state=self.controller.estado_logico,
                current_animation=self.controller.animacao_atual,
                hook_active=False,  # nenhum hook existe até o Tug of War (Fase 7)
            )
        )

    def _processar_evento_gaia(self, mensagem: dict) -> None:
        """Só os eventos com consumidor real hoje - ver docstring de
        `core/mascot_events.py` sobre por que o resto da tabela do plano
        ainda não tem construtor nem tratamento aqui."""
        tipo = mensagem.get("type")
        if tipo == "state_changed":
            estado = mensagem.get("state")
            if estado in mascot_events.ESTADOS_SEMANTICOS_VALIDOS:
                self.estados.definir_estado_semantico(estado)
        elif tipo == "voice_mode_changed":
            # 🔥 Halo (Fase 5, redesenhado 2026-09-02 - ver docstring de
            # `mascot/halo.py`) - reflete o modo de voz atual, não
            # mais estado semântico/emoção.
            self.window.definir_halo_modo_voz(mensagem.get("modo"))
        elif tipo == "assistant_message":
            self.companion_panel.receber_resposta(mensagem)
        elif tipo == "user_message":
            self.companion_panel.receber_mensagem_usuario(mensagem)
        elif tipo == "shutdown":
            QApplication.quit()

    def _montar_tray(self) -> QSystemTrayIcon:
        # `QIcon.fromTheme` depende de um tema de ícones freedesktop, que o
        # Windows não tem - sempre resolvia vazio aqui, gerando
        # `QSystemTrayIcon::setVisible: No Icon set` (confirmado ao vivo,
        # 2026-08-28) e um ícone invisível na bandeja. Ícone PRÓPRIO
        # (2026-08-30, pedido do usuário: "a eris tem o icone dela, assim
        # como o loki e todos os outros... troca o icone na bandeja
        # Galateia mascot por LOKI, com o icones dele") - esse subprocesso É
        # o Project LOKI (avatar/sprites/skins/animações, hoje ainda dentro
        # de `Project-LOKI/mascot/`, ver
        # `project_gaia_ecossistema_nomes_dominios_2026-08-24` na memória),
        # o ícone genérico do app (`app_theme.ico`) que era reaproveitado
        # aqui não fazia mais sentido agora que o LOKI tem identidade
        # visual própria.
        icone_loki = RAIZ_APP / "assets" / "icone_loki.png"
        tray = QSystemTrayIcon(QIcon(str(icone_loki)))
        tray.setToolTip("LOKI")
        menu = QMenu()

        acao_mostrar = QAction("Mostrar", menu, checkable=True, checked=True)
        acao_mostrar.toggled.connect(lambda ativo: self.window.show() if ativo else self.window.hide())
        menu.addAction(acao_mostrar)

        acao_click_through = QAction("Clique-através", menu, checkable=True, checked=self.window.click_through_ativo)
        acao_click_through.toggled.connect(self.window.definir_click_through)
        menu.addAction(acao_click_through)

        acao_centralizar = QAction("Centralizar", menu)
        acao_centralizar.triggered.connect(self._centralizar_janela)
        menu.addAction(acao_centralizar)

        acao_modo_seguro = QAction("Modo seguro (pausar autonomia)", menu, checkable=True)
        acao_modo_seguro.toggled.connect(self._alternar_modo_seguro)
        menu.addAction(acao_modo_seguro)

        menu.addMenu(self._montar_submenu_velocidade(menu))

        menu.addSeparator()
        menu.addMenu(self._montar_submenu_playground(menu))

        menu.addSeparator()
        acao_sair = QAction("Sair", menu)
        acao_sair.triggered.connect(QApplication.quit)
        menu.addAction(acao_sair)

        tray.setContextMenu(menu)
        tray.show()
        return tray

    def _montar_submenu_velocidade(self, pai: QMenu) -> QMenu:
        """Velocidade de voo (pedido do usuário, 2026-08-29) - 100% a
        500% em passos de 100, escolha única (`QActionGroup` exclusivo,
        igual um rádio). Muda `config_mascot["velocidade_voo"]` no MESMO
        dict que o `BehaviorScheduler` já guarda como `self._config`
        (passado por referência no construtor) - não precisa reiniciar
        nada nem re-injetar config pra valer no próximo salto. Persiste
        em `data/mascot_config.json` a cada troca (pedido do usuário, 2026-08-29:
        "tem que persistir") - sobrevive a um restart da GAIA, diferente
        do resto de `mascot_config` (ver docstring de `config.py`)."""
        submenu = QMenu("Velocidade de voo", pai)
        grupo = QActionGroup(submenu)
        grupo.setExclusive(True)
        atual = self.config_mascot.get("velocidade_voo", 1.0)
        for percentual in range(100, 501, 100):
            multiplicador = percentual / 100
            acao = QAction(f"{percentual}%", submenu, checkable=True)
            acao.setChecked(abs(atual - multiplicador) < 0.01)
            acao.triggered.connect(lambda _checked=False, m=multiplicador: self._definir_velocidade_voo(m))
            grupo.addAction(acao)
            submenu.addAction(acao)
        return submenu

    def _definir_velocidade_voo(self, multiplicador: float) -> None:
        self.config_mascot["velocidade_voo"] = multiplicador
        config.salvar_config_mascot({"velocidade_voo": multiplicador})

    def _montar_submenu_playground(self, pai: QMenu) -> QMenu:
        """Playground exigido pela Fase 2 ("forçar clipe e sequência") -
        conteúdo recalculado toda vez que o submenu abre (`aboutToShow`),
        nunca fixo - ver `_preencher_submenu_playground`."""
        submenu = QMenu("Forçar animação", pai)
        submenu.aboutToShow.connect(lambda: self._preencher_submenu_playground(submenu))
        return submenu

    def _preencher_submenu_playground(self, submenu: QMenu) -> None:
        """Só lista animações VÁLIDAS a partir do estado lógico ATUAL (mesmo
        grafo que `AnimationController.solicitar_transicao` já usa pra
        validar, `state_catalog.transicoes_validas_a_partir_de`) - antes
        listava o catálogo INTEIRO (~60 ids) sempre, incluindo
        "complementos" que só existem dentro de uma sequência (ex.: toda
        ação "sentada_*" tem `estado_origem="sentada"` - exige estar sentada
        primeiro). Clicar um complemento fora de hora já era REJEITADO em
        silêncio por `solicitar_transicao` (só loga um aviso, nada visível
        pro usuário) - pedido do usuário (2026-09-01): "Algumas animações
        são complementos de outras, n devem ser listadas ali na bandeja, ou
        se clicadas, tem de ser ativas desde o inicio do fluxo". Resolvido
        filtrando, não encadeando automaticamente - um complemento só
        aparece (e só fica clicável) depois que o usuário já disparou a
        transição que leva até o estado-pai dele, o mesmo caminho que o
        fluxo real de animação percorreria."""
        submenu.clear()
        validas = sorted(e.id for e in state_catalog.transicoes_validas_a_partir_de(self.controller.estado_logico))
        if not validas:
            acao_vazia = QAction("(nenhuma a partir do estado atual)", submenu)
            acao_vazia.setEnabled(False)
            submenu.addAction(acao_vazia)
            return
        for animation_id in validas:
            acao = QAction(animation_id, submenu)
            acao.triggered.connect(lambda _checked=False, id_=animation_id: self.controller.solicitar_transicao(id_))
            submenu.addAction(acao)

    def _centralizar_janela(self) -> None:
        tela = self.window.screen() or QApplication.primaryScreen()
        area = tela.availableGeometry()
        self.window.move(
            area.x() + (area.width() - self.window.width()) // 2,
            area.y() + (area.height() - self.window.height()) // 2,
        )

    def _alternar_modo_seguro(self, ativo: bool) -> None:
        self.config_mascot["autonomy"] = "parada" if ativo else config.MASCOT_PADRAO["autonomy"]
        if ativo:
            self.window.definir_click_through(False)


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # a bandeja continua viva com a janela oculta
    mascot_app = MascotApp()  # referência precisa sobreviver ao app.exec() (senão o GC recolhe tudo)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
