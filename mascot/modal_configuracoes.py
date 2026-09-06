# -*- coding: utf-8 -*-
"""Modal de configurações NATIVO do LOKI (2026-09-03) - porta pra dentro do
próprio processo o que até aqui só existia no modal "🧚 Mascot (LOKI)" do
Painel da GAIA (`ui/qt_modais/mascot.py`, `assistant`). Motivo (pedido do
usuário): "o LOKI tem que conseguir se virar sozinho" - configurar
aparência/monitores/desempenho/comportamentos não podia depender da GAIA
estar rodando. Fonte única daqui pra frente ("o ideal é mantermos sempre o
modal do LOKI atualizado"): o modal da GAIA vira um atalho fino que pede
pra ESTE modal abrir (`mascot_events.evento_settings_requested`), em vez de
manter uma segunda cópia dos mesmos campos - ver `_ao_evento_gaia` em
`process_main.py` e o CHANGELOG/ARQUITETURA da GAIA pro lado de lá.

Recebe a `MascotApp` inteira (não uma cópia de config) - `self._config`/
`self._behaviors` são os MESMOS dicts que `BehaviorScheduler`/`MascotWindow`
já leem por referência a cada ciclo (`config.py::carregar_config_mascot`,
chamado 1x na largada em `MascotApp.__init__`). Isso significa que a
maioria dos campos aqui aplica DE VERDADE na hora, de graça, só por rodar
no MESMO processo (autonomia, movimento reduzido, minutos AFK, velocidade
de voo, monitores permitidos, comportamentos) - diferente do modal da GAIA
antigo, que escrevia num arquivo que o subprocesso só lia 1x na largada
("Aplicar agora" reiniciava o subprocesso inteiro pra qualquer mudança
valer). Só duas exceções continuam precisando de reinício pra valer de
verdade - **escala** (afeta o dimensionamento dos assets já carregados,
`AssetRepository`/`MascotWindow` não têm um caminho de "re-escalar ao
vivo") e **orçamento de memória do cache** (`AssetRepository._orcamento_bytes`
também só é lido no construtor) - a UI avisa isso explicitamente nesses
dois campos, não deixa a pessoa achar que já valeu."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from mascot import config
from mascot.gesture_wheel_editor import EditorGestureWheel
from mascot.qt_widgets import (
    BG_COLOR, GAIA_GOLD, SURFACE_COLOR, CheckboxQuadrado, ModalBase, Switch,
    confirmar_acao, criar_botao, criar_descricao, criar_dropdown, criar_scroll_area,
    criar_slider, criar_spinbox, criar_tabwidget, criar_titulo_secao,
)

AUTONOMIAS_CONFIG_PARA_ROTULO = {"parada": "parada", "subtle": "sutil", "viva": "viva", "travessuras": "travessuras"}
AUTONOMIA_ROTULO_PARA_CONFIG = {v: k for k, v in AUTONOMIAS_CONFIG_PARA_ROTULO.items()}

MODIFICADORES = ("alt", "ctrl", "shift")
BOTOES_MOUSE = ("esquerdo", "direito", "meio")

MENU_SAO_ESTILO_PARA_ROTULO = {
    "classico": "Dourado clássico",
    "vidro": "Vidro translúcido",
    "selo": "Selo (contorno)",
    "aurora": "Aurora",
}
MENU_SAO_ROTULO_PARA_ESTILO = {v: k for k, v in MENU_SAO_ESTILO_PARA_ROTULO.items()}

BEHAVIORS_LABELS = {
    "taskbar_sit": "Sentar na barra de tarefas",
    "sitting_variations": "Variações sentadas (espreguiçar, cochilar)",
    "wander": "Vagar pela tela (voo autônomo entre monitores)",
    "cursor_swing": "Balançar no cursor (precisa de clipes próprios, ainda sem cobertura)",
    "cursor_hunt": "Caçar o cursor (precisa de clipes próprios, ainda sem cobertura)",
    "tug_of_war": "Cabo de guerra (usa hook de mouse por até 3s - desligado por padrão)",
}


class ModalConfiguracoes(ModalBase):
    def __init__(self, mascot_app, parent=None):
        super().__init__(parent)
        self._app = mascot_app
        self._config = mascot_app.config_mascot
        self._behaviors = mascot_app.config_behaviors
        self.setWindowTitle("⚙️ Configurações do LOKI")
        # 940x780 (2026-09-04, achado ao vivo com print: a janela abria
        # cortada por padrão - última pill de categoria e os botões do
        # rodapé da aba "Ações" saindo da borda direita). Um 1º ajuste pra
        # 1400x820 tinha sido calibrado por captura de tela OFFSCREEN (sem
        # fontes reais no ambiente de teste - `QT_QPA_PLATFORM=offscreen`
        # substitui a fonte por um fallback mais largo que o Segoe UI de
        # verdade do Windows), superestimando a largura necessária - o
        # usuário mandou print do app RODANDO DE VERDADE mostrando tudo
        # cabendo sem cortar em ~940px; esse valor é o que manda, não a
        # medição offscreen.
        self.resize(940, 780)
        self.setMinimumSize(760, 620)
        self.setStyleSheet(f"background-color: {BG_COLOR};")

        # Layout modelado no modal "🧑‍🎨 Avatar Virtual" da GAIA
        # (`ui/qt_modais/avatar_virtual.py`) - `QVBoxLayout(self)` sem
        # margem própria (as abas ocupam a janela inteira). SEM emoji no
        # título das abas (2026-09-04, usuário: "os icones sao inuteis") -
        # ao contrário do Avatar Virtual, aqui os 5 títulos já são curtos e
        # autoexplicativos, o emoji só somava ruído visual sem ajudar a
        # identificar a aba mais rápido.
        lay = QVBoxLayout(self)
        abas = criar_tabwidget()
        lay.addWidget(abas, stretch=1)

        aba_geral, geral = self._aba_com_scroll()
        geral.addWidget(criar_descricao(
            "A maioria dos campos abaixo aplica na hora, sem precisar reiniciar "
            "- só Escala e Orçamento de memória (marcados abaixo) precisam de um "
            "reinício do Mascot pra valer de verdade. Ligar/desligar o Mascot "
            "em si continua pela bandeja do sistema (\"Sair\") ou, se estiver "
            "rodando junto da GAIA, pelo Painel principal dela."
        ))
        self._montar_card_presenca(geral)
        geral.addStretch(1)
        abas.addTab(aba_geral, "Geral")

        aba_aparencia, aparencia = self._aba_com_scroll()
        self._montar_card_aparencia(aparencia)
        aparencia.addStretch(1)
        abas.addTab(aba_aparencia, "Aparência")

        aba_acoes, acoes = self._aba_com_scroll()
        self._montar_card_gesture_wheel(acoes)
        acoes.addStretch(1)
        abas.addTab(aba_acoes, "Ações")

        aba_movimento, movimento = self._aba_com_scroll()
        self._montar_card_velocidade_atalho(movimento)
        self._montar_card_monitores(movimento)
        self._montar_card_comportamentos(movimento)
        movimento.addStretch(1)
        abas.addTab(aba_movimento, "Movimento")

        aba_sistema, sistema = self._aba_com_scroll()
        self._montar_card_desempenho(sistema)
        self._montar_card_reiniciar(sistema)
        sistema.addStretch(1)
        abas.addTab(aba_sistema, "Sistema")

        self._abas = abas

    # ------------------------------------------------------------------
    def _salvar_mascot(self, chave, valor):
        self._config[chave] = valor
        config.salvar_config_mascot({chave: valor})

    def _salvar_behavior(self, chave, valor):
        self._behaviors[chave] = valor
        config.salvar_config_behaviors({chave: valor})

    def _aba_com_scroll(self):
        aba = QWidget()
        lay_raiz = QVBoxLayout(aba)
        lay_raiz.setContentsMargins(0, 0, 0, 0)
        scroll, lay = criar_scroll_area()
        lay_raiz.addWidget(scroll)
        return aba, lay

    def _card(self, lay_pai, titulo, cor=GAIA_GOLD):
        f = QFrame()
        f.setStyleSheet(f"background-color: {SURFACE_COLOR}; border-radius: 8px;")
        lay_f = QVBoxLayout(f)
        lay_f.addWidget(criar_titulo_secao(titulo, cor, 14))
        lay_pai.addWidget(f)
        return lay_f

    # ================================================================
    def _montar_card_presenca(self, lay):
        lay_f = self._card(lay, "Presença")

        linha_autonomia = QHBoxLayout()
        linha_autonomia.addWidget(criar_descricao("Autonomia:"))
        combo_autonomia = criar_dropdown(
            list(AUTONOMIA_ROTULO_PARA_CONFIG.keys()),
            AUTONOMIAS_CONFIG_PARA_ROTULO.get(self._config["autonomy"], "sutil"),
            largura=160,
        )
        combo_autonomia.currentTextChanged.connect(
            lambda texto: self._salvar_mascot("autonomy", AUTONOMIA_ROTULO_PARA_CONFIG.get(texto, "subtle"))
        )
        linha_autonomia.addWidget(combo_autonomia)
        linha_autonomia.addStretch(1)
        lay_f.addLayout(linha_autonomia)
        lay_f.addWidget(criar_descricao(
            "parada = sem movimento autônomo · sutil = padrão · viva = mais "
            "frequente · travessuras = inclui comportamentos arriscados, se "
            "ligados abaixo. Aplica na hora."
        ))

        sw_clique = Switch(
            "Clique-através quando ociosa: LIGADO", "Clique-através quando ociosa: desligado",
            cor=GAIA_GOLD, marcado=self._config["click_through_when_idle"],
        )
        sw_clique.stateChanged.connect(lambda estado: self._salvar_mascot("click_through_when_idle", bool(estado)))
        lay_f.addWidget(sw_clique)
        lay_f.addWidget(criar_descricao("Só vale no próximo início do Mascot (lido 1x na largada)."))

        sw_reduzido = Switch(
            "Movimento reduzido: LIGADO", "Movimento reduzido: desligado",
            cor=GAIA_GOLD, marcado=self._config["reduce_motion"],
        )
        sw_reduzido.stateChanged.connect(lambda estado: self._salvar_mascot("reduce_motion", bool(estado)))
        lay_f.addWidget(sw_reduzido)
        lay_f.addWidget(criar_descricao("Remove autonomia/transições decorativas, mantém estados funcionais. Aplica na hora."))

        linha_afk = QHBoxLayout()
        linha_afk.addWidget(criar_descricao("Minutos AFK antes dela fingir dormir:"))
        spin_afk = criar_spinbox(1, 240, self._config["afk_minutos"], largura=70)
        spin_afk.valueChanged.connect(lambda v: self._salvar_mascot("afk_minutos", max(1, v)))
        linha_afk.addWidget(spin_afk)
        linha_afk.addStretch(1)
        lay_f.addLayout(linha_afk)

    # ================================================================
    def _montar_card_aparencia(self, lay):
        lay_f = self._card(lay, "Aparência")

        linha_opacidade = QHBoxLayout()
        linha_opacidade.addWidget(criar_descricao("Opacidade:"))
        valor_opacidade = round(self._config["opacity"] * 100)
        slider_opacidade = criar_slider(5, 100, valor_opacidade)
        spin_opacidade = criar_spinbox(5, 100, valor_opacidade, largura=60)

        def _aplicar_opacidade(v):
            self._salvar_mascot("opacity", v / 100)
            self._app.window.setWindowOpacity(v / 100)

        def _do_slider(v):
            spin_opacidade.blockSignals(True)
            spin_opacidade.setValue(v)
            spin_opacidade.blockSignals(False)
            _aplicar_opacidade(v)

        def _do_spin(v):
            slider_opacidade.blockSignals(True)
            slider_opacidade.setValue(v)
            slider_opacidade.blockSignals(False)
            _aplicar_opacidade(v)

        slider_opacidade.valueChanged.connect(_do_slider)
        spin_opacidade.valueChanged.connect(_do_spin)
        linha_opacidade.addWidget(slider_opacidade, stretch=1)
        linha_opacidade.addWidget(spin_opacidade)
        linha_opacidade.addWidget(criar_descricao("% - aplica na hora"))
        lay_f.addLayout(linha_opacidade)

        linha_escala = QHBoxLayout()
        linha_escala.addWidget(criar_descricao("Escala:"))
        valor_escala = round(self._config["scale"] * 100)
        slider_escala = criar_slider(50, 150, valor_escala)
        spin_escala = criar_spinbox(50, 150, valor_escala, largura=60)

        def _aplicar_escala(v):
            self._salvar_mascot("scale", v / 100)

        def _do_slider_escala(v):
            spin_escala.blockSignals(True)
            spin_escala.setValue(v)
            spin_escala.blockSignals(False)
            _aplicar_escala(v)

        def _do_spin_escala(v):
            slider_escala.blockSignals(True)
            slider_escala.setValue(v)
            slider_escala.blockSignals(False)
            _aplicar_escala(v)

        slider_escala.valueChanged.connect(_do_slider_escala)
        spin_escala.valueChanged.connect(_do_spin_escala)
        linha_escala.addWidget(slider_escala, stretch=1)
        linha_escala.addWidget(spin_escala)
        linha_escala.addWidget(criar_descricao("% - precisa reiniciar o Mascot"))
        lay_f.addLayout(linha_escala)

        linha_estilo_menu = QHBoxLayout()
        linha_estilo_menu.addWidget(criar_descricao("Estilo do Menu SAO:"))
        combo_estilo_menu = criar_dropdown(
            list(MENU_SAO_ROTULO_PARA_ESTILO.keys()),
            MENU_SAO_ESTILO_PARA_ROTULO.get(self._config.get("menu_sao_estilo", "vidro"), "Vidro translúcido"),
            largura=180,
        )
        combo_estilo_menu.currentTextChanged.connect(
            lambda texto: self._salvar_mascot("menu_sao_estilo", MENU_SAO_ROTULO_PARA_ESTILO.get(texto, "vidro"))
        )
        linha_estilo_menu.addWidget(combo_estilo_menu)
        linha_estilo_menu.addStretch(1)
        lay_f.addLayout(linha_estilo_menu)
        lay_f.addWidget(criar_descricao(
            "Cor/textura dos botões que aparecem ao rolar a roda do mouse sobre "
            "ela. Só vale a partir do próximo scroll (o menu já montado não muda)."
        ))

    # ================================================================
    def _montar_card_gesture_wheel(self, lay):
        # Sem `self._card(...)` aqui de propósito (2026-09-04) - o editor
        # agora tem seu próprio banner/título/descrição (ver
        # `EditorGestureWheel._montar_banner`), então embrulhar de novo
        # num card com "Roda de ações" duplicaria o título.
        self._editor_gesture_wheel = EditorGestureWheel(self)
        lay.addWidget(self._editor_gesture_wheel)

    # ================================================================
    def _montar_card_velocidade_atalho(self, lay):
        lay_f = self._card(lay, "Velocidade e atalho de destino")

        linha_vel = QHBoxLayout()
        linha_vel.addWidget(criar_descricao("Velocidade de voo:"))
        valor_vel = round(self._config["velocidade_voo"] * 100)
        spin_vel = criar_spinbox(100, 500, valor_vel, largura=70, passo=100)
        spin_vel.valueChanged.connect(lambda v: self._salvar_mascot("velocidade_voo", v / 100))
        linha_vel.addWidget(spin_vel)
        linha_vel.addWidget(criar_descricao("% (também na bandeja do sistema) - aplica na hora"))
        linha_vel.addStretch(1)
        lay_f.addLayout(linha_vel)

        sw_hotkey = Switch(
            "Atalho \"ir até aqui\": LIGADO", "Atalho \"ir até aqui\": desligado",
            cor=GAIA_GOLD, marcado=self._config["hotkey_destino_ativo"],
        )
        sw_hotkey.stateChanged.connect(lambda estado: self._salvar_mascot("hotkey_destino_ativo", bool(estado)))
        lay_f.addWidget(sw_hotkey)

        linha_combo = QHBoxLayout()
        linha_combo.addWidget(criar_descricao("Modificador:"))
        combo_mod = criar_dropdown(list(MODIFICADORES), self._config["hotkey_destino_modificador"], largura=100)
        combo_mod.currentTextChanged.connect(lambda texto: self._salvar_mascot("hotkey_destino_modificador", texto))
        linha_combo.addWidget(combo_mod)

        linha_combo.addWidget(criar_descricao("+ Botão do mouse:"))
        combo_botao = criar_dropdown(list(BOTOES_MOUSE), self._config["hotkey_destino_botao"], largura=100)
        combo_botao.currentTextChanged.connect(lambda texto: self._salvar_mascot("hotkey_destino_botao", texto))
        linha_combo.addWidget(combo_botao)
        linha_combo.addStretch(1)
        lay_f.addLayout(linha_combo)

    # ================================================================
    def _montar_card_monitores(self, lay):
        lay_f = self._card(lay, "Monitores permitidos")
        lay_f.addWidget(criar_descricao("Nenhum marcado = todos os monitores conectados valem. Aplica na hora."))

        permitidos = set(self._config.get("monitores_permitidos") or [])
        telas = QApplication.screens()
        if not telas:
            lay_f.addWidget(criar_descricao("Nenhum monitor detectado nesta sessão."))
            return

        self._checks_monitor = {}
        for tela in telas:
            nome = tela.name()
            chk = CheckboxQuadrado(nome, marcado=(nome in permitidos), cor=GAIA_GOLD)
            chk.stateChanged.connect(lambda estado, n=nome: self._mudar_monitor(n, bool(estado)))
            self._checks_monitor[nome] = chk
            lay_f.addWidget(chk)

    def _mudar_monitor(self, nome, marcado):
        permitidos = set(self._config.get("monitores_permitidos") or [])
        if marcado:
            permitidos.add(nome)
        else:
            permitidos.discard(nome)
        self._salvar_mascot("monitores_permitidos", sorted(permitidos))

    # ================================================================
    def _montar_card_desempenho(self, lay):
        lay_f = self._card(lay, "Desempenho")

        linha_orcamento = QHBoxLayout()
        linha_orcamento.addWidget(criar_descricao("Orçamento de memória do cache de animações:"))
        spin_orcamento = criar_spinbox(150, 1000, round(self._config["memoria_orcamento_mb"]), largura=70, passo=10)
        spin_orcamento.valueChanged.connect(lambda v: self._salvar_mascot("memoria_orcamento_mb", float(v)))
        linha_orcamento.addWidget(spin_orcamento)
        linha_orcamento.addWidget(criar_descricao("MB - precisa reiniciar o Mascot"))
        linha_orcamento.addStretch(1)
        lay_f.addLayout(linha_orcamento)
        lay_f.addWidget(criar_descricao(
            "Quanto o cache guarda decodificado em RAM antes de despejar as "
            "animações menos usadas. Mais alto = menos travadinha ao trocar de "
            "animação fora do fluxo comum, ao custo de mais memória. 320MB é o "
            "padrão calibrado medindo a autonomia \"viva\" ao vivo - baixe se a "
            "RAM for curta, suba se sobrar de sobra."
        ))

    # ================================================================
    def _montar_card_reiniciar(self, lay):
        # Pedido do usuário, 2026-09-04: "Tem q ter um botao p reiniciar
        # nela, n apenas na gaia" - até aqui só dava pra reiniciar o Mascot
        # desligando/ligando o switch "Ativado" do Painel da GAIA, ou
        # fechando pela bandeja e subindo de novo na mão. Motivo do pedido
        # ("quando vou reiniciar, é com proposito de pegar as correcoes e
        # atualizações"): só um processo NOVO de verdade recarrega código
        # do disco - por isso o botão sobe um processo antes de fechar o
        # atual, em vez de tentar recarregar algo "por dentro".
        lay_f = self._card(lay, "Reiniciar")
        lay_f.addWidget(criar_descricao(
            "Fecha este Mascot e abre um novo na hora, sem precisar do Painel da "
            "GAIA. Útil depois de mudar Escala/Orçamento de memória (que não "
            "aplicam ao vivo) ou de atualizar o código do LOKI."
        ))
        linha = QHBoxLayout()
        linha.addStretch(1)
        botao = criar_botao("🔄 Reiniciar Mascot", preenchido=True)
        botao.clicked.connect(self._reiniciar_mascot)
        linha.addWidget(botao)
        lay_f.addLayout(linha)

    def _reiniciar_mascot(self) -> None:
        """Fonte de verdade em `MascotApp.reiniciar_mascot` (2026-09-06,
        pedido do usuário: "coloca o botão de reiniciar loki tbm na
        bandeja") - a bandeja passou a ter o MESMO botão, então a lógica
        de subir um processo novo/fechar o atual mora só lá agora, não
        duplicada aqui."""
        self._app.reiniciar_mascot()

    # ================================================================
    def _montar_card_comportamentos(self, lay):
        lay_f = self._card(lay, "Comportamentos autônomos")
        lay_f.addWidget(criar_descricao(
            "O scheduler só escolhe um comportamento se TODOS os clipes "
            "necessários existirem, mesmo que ligado aqui. Aplica na hora."
        ))

        grid = QGridLayout()
        for i, (chave, rotulo) in enumerate(BEHAVIORS_LABELS.items()):
            chk = CheckboxQuadrado(rotulo, marcado=self._behaviors.get(chave, False), cor=GAIA_GOLD)

            def _mudar(estado, c=chave, w=chk):
                if c == "tug_of_war" and estado:
                    if not confirmar_acao(
                        self, "Cabo de guerra",
                        "Esse comportamento usa um hook de mouse por até 3 "
                        "segundos (resistência leve, liberação garantida por "
                        "clique/Esc/arraste/watchdog). Confirma que quer ligar?"
                    ):
                        w.blockSignals(True)
                        w.setChecked(False)
                        w.blockSignals(False)
                        return
                self._salvar_behavior(c, bool(estado))

            chk.stateChanged.connect(_mudar)
            grid.addWidget(chk, i, 0)
        lay_f.addLayout(grid)
