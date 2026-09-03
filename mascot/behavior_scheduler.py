# -*- coding: utf-8 -*-
"""BehaviorScheduler (plano, seção 10) - decide QUANDO rodar cada Behavior
viável hoje com os assets existentes: Floating Idle (fallback universal,
não precisa de lógica própria - é só nunca escolher nada e deixar o loop
atual continuar), Taskbar Sit e Variações sentadas (espreguiçar e as 14
reações - todas com o MESMO toggle `sitting_variations`, seção 12, já que
o plano só prevê essa UMA chave pra tudo que acontece sentada), Levantar
(`sentada_para_flutuando` - reaproveita o toggle `taskbar_sit`, já que é
literalmente o oposto dele; sem isso, sentar seria uma viagem só de ida) e
Wander (as 8 direções de flutuar importadas em 2026-08-28 - toggle
`wander`, que o plano já previa e vem `false` por padrão até ser validado
ao vivo).

A sequência de sono (`sentada_caindo-no-sono`/`sentada_deitando`) fica DE
FORA do sorteio autônomo de propósito (2026-08-28) - ela é
fisiológica/temporal (só faz sentido depender de hora do dia/tempo
ocioso real), não um tique aleatório como espreguiçar ou rir. Sem um
gatilho de tempo real ainda (isso é Fase 3, junto com o resto do
contexto vindo da GAIA), sortear ela junto das reações faria a
personagem "ter sono" as 14h só porque o RNG quis - só fica acessível
pelo playground até existir esse gatilho de verdade.

Cada Behavior declara peso, cooldown, orçamento por hora e os assets que
exige - "o scheduler nunca seleciona um Behavior sem todos os assets
necessários" (seção 10) é `Behavior.elegivel` conferindo que o
`AssetRepository` carrega cada um deles pelo próprio id, sem cair em
fallback.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QObject, QTimer

from mascot import platform_windows, state_catalog
from mascot.animation_controller import AnimationController
from mascot.asset_repository import AssetRepository
from mascot.physics import MovimentoAmortecido, MovimentoComDuracaoFixa
from mascot.safety import SafetyController
from mascot.window import MascotWindow

INTERVALO_TICK_MS = 3000
TIMEOUT_OCUPADO_SEGUNDOS = 60  # trava de segurança - nenhuma ação legítima (fila de saltos + queda + recuperação, o pior caso real) passa disso; se passar, algum callback de transição não disparou (bug real, 2026-08-29: "ja tem mais de 10min q ela ta em idle flutuando" sem tela cheia/RDP/trava de tela) e `_ocupado` ficava preso pra sempre, sem isso, até reiniciar o processo do zero
COOLDOWN_FAMILIA_SEGUNDOS = 180  # evita rir_01 -> rir_02 -> rir_03 em sequência (tags de state_catalog)
DISTANCIA_WANDER_PX = 900  # ver DISTANCIA_POR_CICLO_LOOP_PX - recalibrado junto pra caber ~3 ciclos de loop reais
MARGEM_TELA_WANDER_PX = 20  # mantém o destino do Wander DENTRO da tela - autonomia sem intenção do usuário não deveria cortar como um arraste
TOLERANCIA_DESTINO_PX = 60  # o suficiente pra não ficar dando saltos de 1px tentando encostar exato num alvo que só 8 direções não alcançam certeiro
MAX_SALTOS_DESTINO = 8  # trava de segurança - nunca persegue um destino pra sempre
DISTANCIA_POR_CICLO_LOOP_PX = 350  # quanto cada repetição do loop "deveria" cobrir - decide quantos ciclos tocar antes de frear
CICLOS_LOOP_MINIMO = 1  # nunca corta o loop antes de completar pelo menos 1 volta inteira (bug real, 2026-08-29: "faz iniciar->loop->pausa, em vez de repetir o loop")
MARGEM_COSSENO_DIRECAO = 0.06  # ~14-20° de tolerância - direções quase tão alinhadas quanto a melhor entram no sorteio (ver _direcao_mais_proxima)
# reações sentada->sentada já existentes que COMBINAM com "acabou de
# acordar" - reaproveitadas por `_acordar` pra disfarçar o salto de
# estado sem arte de "acordando" (ver _acordar).
REACOES_ACORDAR = ("sentada_espreguicando", "sentada_bocejando")

DIRECOES_VETOR = {
    "direita": (1.0, 0.0),
    "esquerda": (-1.0, 0.0),
    "subida": (0.0, -1.0),
    "descida": (0.0, 1.0),
    "superior-direita": (0.7071, -0.7071),
    "superior-esquerda": (-0.7071, -0.7071),
    "inferior-direita": (0.7071, 0.7071),
    "inferior-esquerda": (-0.7071, 0.7071),
}


def _clamp_para_direcao(atual: float, alvo_natural: float, minimo: float, maximo: float) -> float:
    """Clampa `alvo_natural` em `[minimo, maximo]` sem NUNCA cruzar pro
    lado oposto de `atual` - bug real reportado pelo usuário (2026-08-29:
    "ela está tentando descer já estando no ponto mais baixo"). Com o
    clamp simples (`min(max(...))`), quando o teto da região permitida
    ficava ABAIXO da posição atual dela (ex.: Taskbar Sit mirando um
    "piso" mais baixo do que o topo da janela consegue voar sem sair da
    tela), o resultado saía do lado ERRADO de `atual` e a movia pra CIMA
    ao pedir "descida"."""
    limite = min(max(alvo_natural, minimo), maximo)
    if alvo_natural > atual:
        return max(atual, limite)
    if alvo_natural < atual:
        return min(atual, limite)
    return atual

# "stand_up" não tem chave própria no config (seção 12 do plano só prevê
# `taskbar_sit`) - é o oposto exato dele, sentar sem poder levantar de
# volta seria uma viagem só de ida. Behaviors fora daqui usam o próprio
# id como chave (comportamento padrão).
CHAVE_CONFIG_POR_BEHAVIOR = {"stand_up": "taskbar_sit"}

ANIMACOES_VARIACOES_SENTADAS = tuple(
    sorted(
        id_
        for id_, entrada in state_catalog.CATALOGO.items()
        # destino "sentada" (não "dormindo"/"deitada") exclui a sequência
        # de sono do sorteio autônomo - ver docstring do módulo.
        if entrada.estado_origem == "sentada" and entrada.estado_destino == "sentada" and not entrada.loop
    )
)


@dataclass
class Behavior:
    id: str
    peso: float
    cooldown_segundos: float
    orcamento_por_hora: int
    assets_necessarios: tuple[str, ...]
    executar: Callable[[], None]
    ultimo_disparo: float = field(default=0.0, init=False)
    disparos_na_janela: list = field(default_factory=list, init=False)

    def elegivel(self, agora: float, repositorio: AssetRepository) -> bool:
        """`assets_necessarios` é a lista de candidatos do Behavior - basta
        UM deles carregar de verdade (sem cair em fallback) pra valer a
        pena rodar; behaviors com um só clipe obrigatório (ex.: Taskbar
        Sit) continuam se comportando como "tudo ou nada" porque só têm
        aquele único candidato pra checar."""
        if agora - self.ultimo_disparo < self.cooldown_segundos:
            return False
        self.disparos_na_janela = [t for t in self.disparos_na_janela if agora - t < 3600]
        if len(self.disparos_na_janela) >= self.orcamento_por_hora:
            return False
        return any(repositorio.obter(id_).id == id_ for id_ in self.assets_necessarios)

    def marcar_disparo(self, agora: float) -> None:
        self.ultimo_disparo = agora
        self.disparos_na_janela.append(agora)


class BehaviorScheduler(QObject):
    def __init__(
        self,
        controller: AnimationController,
        window: MascotWindow,
        repositorio: AssetRepository,
        safety: SafetyController,
        config_mascot: dict,
        config_behaviors: dict,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._controller = controller
        self._window = window
        self._repositorio = repositorio
        self._safety = safety
        self._config = config_mascot
        self._behaviors_config = config_behaviors
        self.__ocupado = False  # trava re-entrada enquanto uma ação não-interrompível toca (ver property _ocupado abaixo)
        self._ocupado_desde: float | None = None  # timestamp de quando ficou ocupada - alimenta o watchdog de TIMEOUT_OCUPADO_SEGUNDOS em _tick
        self._callback_estado_pendente: Callable[[str], None] | None = None  # qual callback está esperando o próximo estado_alterado agora (nunca mais de um por vez, _ocupado impede re-entrada) - evita warning do Qt ao desconectar um slot que não estava conectado (ver interromper_para_arraste)
        self._ultimo_disparo_por_familia: dict[str, float] = {}
        self._movimento = MovimentoAmortecido(rigidez=25.0, amortecimento=9.0, parent=self)
        self._movimento_wander = MovimentoComDuracaoFixa(parent=self)
        self._destino_ativo: tuple[float, float] | None = None
        self._destino_ao_chegar: Callable[[], None] | None = None
        self._destino_tolerancia_px: float = TOLERANCIA_DESTINO_PX
        self._saltos_destino_restantes = 0

        self._behaviors = [
            Behavior(
                id="taskbar_sit",
                peso=1.0,
                cooldown_segundos=180,
                orcamento_por_hora=6,
                assets_necessarios=("flutuando_para_sentada",),
                executar=self._executar_taskbar_sit,
            ),
            Behavior(
                id="sitting_variations",
                peso=2.0,
                cooldown_segundos=45,
                orcamento_por_hora=20,
                assets_necessarios=ANIMACOES_VARIACOES_SENTADAS,
                executar=self._executar_variacao_sentada,
            ),
            Behavior(
                id="stand_up",
                peso=1.0,
                cooldown_segundos=180,
                orcamento_por_hora=6,
                assets_necessarios=("sentada_para_flutuando",),
                executar=self._executar_levantar,
            ),
            Behavior(
                id="wander",
                peso=1.0,
                cooldown_segundos=120,
                orcamento_por_hora=8,
                assets_necessarios=tuple(f"flutuando_{d}_iniciar" for d in DIRECOES_VETOR),
                executar=self._executar_wander,
            ),
        ]

        # 🔥 Reinicia o cooldown a partir do FIM de um bloqueio de autonomia
        # (CompanionPanel/Menu SAO fechados, ou saiu de tela cheia/jogo -
        # `safety.py`, 2026-09-02) em vez de deixar os timers correndo
        # durante o bloqueio inteiro - sem isso, se um Behavior já estivesse
        # elegível (ou ficasse elegível) enquanto bloqueado, ele dispararia
        # QUASE NA HORA em que o bloqueio caísse (ex.: fechar o menu SAO e
        # ela sair voando na mesma hora) - comportamento estranho descrito
        # em `Project LOKI.md`/`GAIA_MENU_SAO.md`. `ultimo_disparo = agora`
        # direto (NUNCA `marcar_disparo`, que também contaria pro orçamento
        # por hora - `Behavior.elegivel`, `disparos_na_janela` - um reinício
        # de cooldown não é um disparo de verdade).
        self._safety.autonomia_alterada.connect(self._ao_autonomia_alterada)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(INTERVALO_TICK_MS)

    def _ao_autonomia_alterada(self, permitida: bool) -> None:
        if not permitida:
            return
        agora = time.monotonic()
        for behavior in self._behaviors:
            behavior.ultimo_disparo = agora

    @property
    def _ocupado(self) -> bool:
        return self.__ocupado

    @_ocupado.setter
    def _ocupado(self, valor: bool) -> None:
        self.__ocupado = valor
        self._ocupado_desde = time.monotonic() if valor else None

    def _tick(self) -> None:
        self._verificar_afk()
        if self._ocupado:
            if self._ocupado_desde is not None and time.monotonic() - self._ocupado_desde > TIMEOUT_OCUPADO_SEGUNDOS:
                print(
                    f" [SISTEMA] Mascot: presa em _ocupado por mais de {TIMEOUT_OCUPADO_SEGUNDOS}s sem "
                    "liberar sozinha (algum callback de transição não disparou) - destravando."
                )
                self._cancelar_movimento_e_sinais_pendentes()
                self._ocupado = False
            else:
                return
        if self._config.get("reduce_motion") or self._config.get("autonomy") == "parada":
            return
        if not self._safety.autonomia_permitida:
            return

        agora = time.monotonic()
        candidatos = [
            behavior
            for behavior in self._behaviors
            if self._behaviors_config.get(CHAVE_CONFIG_POR_BEHAVIOR.get(behavior.id, behavior.id), False)
            and self._elegivel_pelo_estado(behavior.id)
            and behavior.elegivel(agora, self._repositorio)
        ]
        if not candidatos:
            return

        escolhido = random.choices(candidatos, weights=[c.peso for c in candidatos], k=1)[0]
        escolhido.marcar_disparo(agora)
        escolhido.executar()

    def _verificar_afk(self) -> None:
        """Ociosidade REAL de teclado/mouse (pedido do usuário,
        2026-08-29: "quero que ela reconheça quando estou afk, pra por a
        GAIA pra dormir") - `platform_windows.obter_segundos_ociosos`,
        nada a ver com "tempo sem falar com a GAIA" (Avatar Virtual/
        Hidratação usam outro contador, sobre CONVERSA). Só efeito
        visual - a "sequência de sono" do catálogo (`sentada_caindo-no-sono`)
        ficava fora do sorteio autônomo de propósito até existir esse
        gatilho de tempo real (ver docstring do módulo).

        Acordar roda SEMPRE que ela estiver dormindo e a ociosidade cair
        de novo (só respeita `_ocupado` - voltar da ausência não deveria
        depender de `reduce_motion`/autonomia estarem ligados, isso é
        reação ao usuário, não ação espontânea). Dormir É espontâneo,
        então respeita os mesmos freios das outras autonomias."""
        if self._ocupado:
            return
        dormindo = self._controller.estado_logico in ("dormindo", "deitada")
        segundos_ociosos = platform_windows.obter_segundos_ociosos()
        afk = segundos_ociosos >= self._config.get("afk_minutos", 10) * 60
        if dormindo:
            if not afk:
                self._acordar()
            return
        if afk and not (self._config.get("reduce_motion") or self._config.get("autonomy") == "parada") and self._safety.autonomia_permitida:
            self._iniciar_sono()

    def _iniciar_sono(self) -> None:
        if self._controller.animacao_atual == "sentada_balancando-pernas":
            self._ocupado = True
            if not self._controller.solicitar_transicao("sentada_caindo-no-sono"):
                self._ocupado = False
                return
            self._conectar_liberar_ocupado()
        elif self._controller.animacao_atual == "flutuando_idle" and self._behaviors_config.get("taskbar_sit", False):
            # sem sentar primeiro ela passaria o AFK inteiro flutuando à
            # toa (não existe arte de "flutuando dormindo") - senta com o
            # comportamento já existente; a checagem se repete no próximo
            # tick (3s) e ela cai no sono assim que estiver sentada.
            self._executar_taskbar_sit()

    def _acordar(self) -> None:
        # sem arte de "acordando" ainda (ver docstring de
        # `AnimationController.forcar_estado`) - o salto de estado em si
        # (dormindo/deitada -> sentada) é instantâneo por dentro, mas
        # NUNCA chega a ser desenhado: a ação real (espreguiçar/bocejar,
        # ambas já existem e combinam com "acabou de acordar") entra no
        # lugar na mesma chamada síncrona, antes de qualquer quadro
        # renderizar - pra quem está olhando, ela pula do sono direto pra
        # uma reação animada de acordar, nunca pro idle parado seco
        # (pedido do usuário, 2026-08-29: "tem de ter uma transição
        # suave entre animações").
        self._controller.forcar_estado("sentada_balancando-pernas")
        self._ocupado = True
        if not self._controller.solicitar_transicao(random.choice(REACOES_ACORDAR)):
            self._ocupado = False
            return
        self._conectar_liberar_ocupado()

    def interromper_para_arraste(self) -> None:
        """Chamado por `MascotWindow` (via `process_main.py`) assim que o
        usuário agarra ela de verdade - pedido do usuário, 2026-08-29:
        "quando eu segurar ela, tem de interromper na hora a animação
        atual". Cancela QUALQUER física/perseguição autônoma em
        andamento - sem isso, um salto de Wander ou uma perseguição de
        destino/Taskbar Sit ainda em curso continuava chamando
        `window.move(...)` brigando com o arraste manual do usuário.

        `_ocupado=True` fica travado durante TODO o arraste (inclusive
        queda/recuperação depois de soltar) - `retomar_apos_arraste`
        libera de volta assim que ela volta a flutuar calma. Desconectar
        `_liberar_ocupado` evita que ele dispare TARDE, na emissão de
        `estado_alterado` do que estava em andamento antes da
        interrupção (ex.: ao entrar em "agarrada"), e libere a trava no
        momento errado."""
        self._cancelar_movimento_e_sinais_pendentes()
        self._ocupado = True

    def retomar_apos_arraste(self) -> None:
        self._ocupado = False

    def _cancelar_movimento_e_sinais_pendentes(self) -> None:
        """Para qualquer física/perseguição autônoma em andamento e
        desconecta o callback de `estado_alterado` pendente (seja ele
        `_liberar_ocupado` ou outro, ex.: `_ao_levantar_concluido`) -
        compartilhado por `interromper_para_arraste` (o usuário agarrou
        ela no meio de uma ação) e pelo watchdog de `_tick` (`_ocupado`
        preso além de `TIMEOUT_OCUPADO_SEGUNDOS`), os dois precisam
        limpar o que estava em curso antes de mudar o estado de
        ocupação."""
        self._movimento_wander.parar()
        self._movimento.parar()
        self._destino_ativo = None
        self._destino_ao_chegar = None
        if self._callback_estado_pendente is not None:
            self._controller.estado_alterado.disconnect(self._callback_estado_pendente)
            self._callback_estado_pendente = None

    def _elegivel_pelo_estado(self, behavior_id: str) -> bool:
        if behavior_id == "taskbar_sit":
            return self._controller.estado_logico != "sentada"
        if behavior_id == "sitting_variations":
            return self._controller.animacao_atual == "sentada_balancando-pernas"
        if behavior_id == "stand_up":
            # só levanta do idle sentado calmo, nunca no meio de uma
            # ação/variação (mesmo critério de sitting_variations).
            return self._controller.animacao_atual == "sentada_balancando-pernas"
        if behavior_id == "wander":
            # só sai voando do idle flutuando calmo, nunca no meio de
            # outra ação flutuando (perdida/cortina).
            return self._controller.animacao_atual == "flutuando_idle"
        return True

    def _executar_taskbar_sit(self) -> None:
        self._ocupado = True
        tela = self._window.screen()
        area_x, area_y, area_largura, area_altura = platform_windows.obter_work_area_da_tela(tela)
        # alinha o ASSENTO (não o pé) com o topo da barra - state_catalog.
        # LINHA_ASSENTO_SENTADA_PX, medido visualmente na pose de repouso
        # (é nela que ela vai ficar descansando). Perna/pé abaixo do
        # assento passar da barra é esperado (pedido do usuário,
        # 2026-08-28) - só o assento precisa encostar certo.
        linha_assento = state_catalog.LINHA_ASSENTO_SENTADA_PX * self._window.escala
        piso = area_y + area_altura - linha_assento
        x_alvo = min(max(self._window.x(), area_x), area_x + area_largura - self._window.width())

        def _ao_chegar_perto() -> None:
            # ajuste FINAL preciso (mola silenciosa, sem animação de voo -
            # é só a última correção de alguns px) - o encadeamento de
            # saltos acima cobre a distância "de voo" real, mas não
            # cravaria o pivô exatamente na linha do assento calibrada.
            # `_ocupado` precisa voltar a True AQUI - `_perseguir_ponto`
            # já liberou ele achando que a perseguição acabou, e a mola
            # ainda vai rodar por um tempo real (QTimer próprio); sem
            # isso, o `_tick()` autônomo lia `_ocupado=False` no meio do
            # pouso e sequestrava ela pra outro Behavior (ex.: Wander) -
            # bug real, 2026-08-29: a "travada" ao mandar ir pra um lugar
            # era esse sequestro, não um congelamento de verdade.
            self._ocupado = True

            def _ao_encostar_exato() -> None:
                self._movimento.finalizado.disconnect(_ao_encostar_exato)
                if not self._controller.solicitar_transicao("flutuando_para_sentada"):
                    self._ocupado = False
                    return
                self._conectar_liberar_ocupado()

            self._movimento.finalizado.connect(_ao_encostar_exato)
            self._movimento.iniciar(
                lambda: (self._window.x(), self._window.y()),
                lambda x, y: self._window.move(int(x), int(y)),
                (x_alvo, piso),
            )

        # se ela estiver longe da barra (ex.: numa posição alta), voa até
        # perto de verdade primeiro (animação de descer, não só deslizar
        # em silêncio) - bug real reportado pelo usuário, 2026-08-29:
        # "ela só rusha lá pra baixo e senta". Perto o bastante, pula
        # direto pra correção final (sem sair voando por 10px de tolerância).
        self._perseguir_ponto(x_alvo, piso, ao_chegar=_ao_chegar_perto)

    def _executar_variacao_sentada(self) -> None:
        self._ocupado = True
        agora = time.monotonic()
        disponiveis = [
            id_
            for id_ in ANIMACOES_VARIACOES_SENTADAS
            if self._repositorio.obter(id_).id == id_ and self._familia_disponivel(id_, agora)
        ]
        if not disponiveis:
            self._ocupado = False
            return
        escolhida = random.choice(disponiveis)
        for tag in state_catalog.CATALOGO[escolhida].tags:
            if tag != "action":  # "action" é genérica, marcar ela em cooldown baniria o pool inteiro
                self._ultimo_disparo_por_familia[tag] = agora
        if not self._controller.solicitar_transicao(escolhida):
            self._ocupado = False
            return
        self._conectar_liberar_ocupado()

    def _executar_levantar(self) -> None:
        """Oposto do Taskbar Sit - sem isso, sentar era uma viagem só de
        ida (nenhuma transição saía de "sentada" de volta pra
        "flutuando" até `sentada_para_flutuando` existir, 2026-08-28)."""
        self._ocupado = True
        if not self._controller.solicitar_transicao("sentada_para_flutuando"):
            self._ocupado = False
            return
        self._conectar_callback_estado(self._ao_levantar_concluido)

    def _ao_levantar_concluido(self, _estado: str) -> None:
        """Só dispara quando a animação de levantar já terminou de
        verdade (próximo `estado_alterado` depois dela, tipicamente
        `flutuando_idle`) - NUNCA em paralelo com o clipe ainda tocando.
        Antes disso corrigia a posição na mesma hora que a transição
        começava (pedido do usuário, 2026-08-29: "deixa ela terminar
        animação de levantar primeiro, só depois sobe ela na tela" -
        mesmo o fix anterior, animar em vez de `.move()` instantâneo,
        ainda começava o movimento CEDO DEMAIS, em paralelo com o clipe).

        A posição sentada é calibrada pela linha do ASSENTO (o pé pode
        passar da barra de propósito, ver `_executar_taskbar_sit`) - de
        pé, a caixa inteira da janela conta, e podia sobrar fora da
        região de voo permitida (bug exposto ao perseguir um destino
        logo depois de levantar). Reencaixa nos limites de voo aqui, com
        mola (nunca `.move()` instantâneo - bug real anterior, 2026-08-29:
        "quando ela está sentada e levanta, ela dá uma teleportada pra
        cima")."""
        self._controller.estado_alterado.disconnect(self._ao_levantar_concluido)
        self._callback_estado_pendente = None
        self._ocupado = False
        area_x, area_y, area_largura, area_altura = self._geometria_permitida()
        m = MARGEM_TELA_WANDER_PX
        x_alvo = min(max(self._window.x(), area_x + m), area_x + area_largura - self._window.width() - m)
        y_alvo = min(max(self._window.y(), area_y + m), area_y + area_altura - self._window.height() - m)
        if (x_alvo, y_alvo) != (self._window.x(), self._window.y()):
            self._movimento.iniciar(
                lambda: (self._window.x(), self._window.y()),
                lambda x, y: self._window.move(int(x), int(y)),
                (x_alvo, y_alvo),
            )

    def _direcoes_disponiveis(self) -> list[str]:
        return [
            d
            for d in DIRECOES_VETOR
            if all(
                self._repositorio.obter(f"flutuando_{d}_{sufixo}").id == f"flutuando_{d}_{sufixo}"
                for sufixo in ("iniciar", "loop", "parar")
            )
        ]

    def _direcao_mais_proxima(self, dx: float, dy: float, disponiveis: list[str]) -> str:
        """Snap do vetor livre (`dx`, `dy`) pra uma das 8 direções REAIS
        que existem como clipe - usado por "ir até o destino", que mira
        num ponto qualquer da tela, não numa das 8 direções exatas. COM
        variação: quando mais de uma direção está quase igualmente
        alinhada (ex.: o alvo cai só um pouco fora do eixo - direita
        "ganha" da diagonal inferior-direita por uma margem mínima),
        sorteia entre as quase-empatadas em vez de sempre escolher a
        mesma - sem isso, o mesmo tipo de alvo sempre gerava o mesmo
        trajeto "só horizontal, depois só vertical" (bug real reportado
        pelo usuário, 2026-08-29: "como ela pode ir na diagonal, não
        deixe fixo pra ela sempre ir full horizontal depois vertical").
        Comparação por COSSENO (produto escalar / magnitude), não o
        produto escalar bruto - assim a margem de tolerância significa a
        mesma coisa (um ângulo) independente da distância até o alvo."""
        magnitude = math.hypot(dx, dy)
        if magnitude < 1e-6:
            return random.choice(disponiveis)
        cossenos = {d: (dx * DIRECOES_VETOR[d][0] + dy * DIRECOES_VETOR[d][1]) / magnitude for d in disponiveis}
        melhor = max(cossenos.values())
        candidatas = [d for d in disponiveis if melhor - cossenos[d] <= MARGEM_COSSENO_DIRECAO]
        return random.choice(candidatas)

    def _geometria_permitida(self) -> tuple[float, float, float, float]:
        return platform_windows.obter_geometria_todos_os_monitores(self._config.get("monitores_permitidos"))

    def _pode_avancar(self, direcao: str, distancia_px: float = DISTANCIA_WANDER_PX) -> bool:
        """Confere se ainda cabe pelo menos 1px de deslocamento REAL nessa
        direção, PRA ESSA DISTÂNCIA ESPECÍFICA, antes de gastar um salto
        tentando - sem isso, perseguir (ou vagar) na direção de um teto já
        alcançado (ex.: Taskbar Sit mirando um "piso" mais baixo do que o
        voo pode chegar sem sair da tela) ficava reexecutando o mesmo
        salto pra sempre sem progredir (bug real, 2026-08-29: "ela está
        tentando descer já estando no ponto mais baixo"). O parâmetro
        `distancia_px` (em vez de sempre usar `DISTANCIA_WANDER_PX` como
        sonda) importa pra diagonais: com uma sonda genérica grande, uma
        direção como "inferior-direita" perto de uma borda podia passar
        no teste só porque UM dos dois eixos tinha espaço numa distância
        de sonda de 900px, mesmo quando o salto de verdade (bem mais
        curto) não avançava quase nada em NENHUM eixo de fato - ela
        tocava a animação diagonal inteira parada no lugar (bug real,
        2026-08-29: "vi ela na borda da direita... ficando parado por
        estar no limite"). O Wander autônomo (sem alvo, chama sem esse
        argumento) mantém a sonda padrão, já que o salto dele SEMPRE usa
        essa mesma distância."""
        dx, dy = DIRECOES_VETOR[direcao]
        area_x, area_y, area_largura, area_altura = self._geometria_permitida()
        m = MARGEM_TELA_WANDER_PX
        x_alvo = _clamp_para_direcao(
            self._window.x(),
            self._window.x() + dx * distancia_px,
            area_x + m,
            area_x + area_largura - self._window.width() - m,
        )
        y_alvo = _clamp_para_direcao(
            self._window.y(),
            self._window.y() + dy * distancia_px,
            area_y + m,
            area_y + area_altura - self._window.height() - m,
        )
        return math.hypot(x_alvo - self._window.x(), y_alvo - self._window.y()) >= 1.0

    def _executar_wander(self) -> None:
        disponiveis = [d for d in self._direcoes_disponiveis() if self._pode_avancar(d)]
        if not disponiveis:
            return
        self._ocupado = True
        direcao = random.choice(disponiveis)
        self._iniciar_hop(direcao, DISTANCIA_WANDER_PX)

    def ir_para_destino(self, x: float, y: float) -> None:
        """"Ir até aqui" (pedido do usuário, 2026-08-29: hotkey de
        modificador+clique, ver `click_destino.py`) - persegue um ponto
        qualquer da tela encadeando saltos na direção mais próxima das 8
        disponíveis (não existe clipe de "flutuar num ângulo exato"),
        até chegar perto o bastante ou estourar `MAX_SALTOS_DESTINO`."""
        if self._ocupado or self._controller.animacao_atual != "flutuando_idle":
            return  # ação em andamento nunca é cortada - clique de novo quando ela estiver livre
        area_x, area_y, area_largura, area_altura = self._geometria_permitida()
        alvo_x = min(max(x, area_x), area_x + area_largura)
        alvo_y = min(max(y, area_y), area_y + area_altura)
        # mira o CENTRO da janela no ponto clicado (não o canto superior
        # esquerdo) - "ela vai até onde eu cliquei" é mais intuitivo assim.
        self._perseguir_ponto(
            alvo_x - self._window.width() / 2,
            alvo_y - self._window.height() / 2,
            ao_chegar=None,
        )

    def _perseguir_ponto(
        self,
        alvo_x: float,
        alvo_y: float,
        ao_chegar: Callable[[], None] | None,
        tolerancia_px: float = TOLERANCIA_DESTINO_PX,
        max_saltos: int = MAX_SALTOS_DESTINO,
    ) -> None:
        """Persegue um ponto qualquer encadeando saltos de 8 direções -
        usado tanto por "ir até o destino" (`ao_chegar=None`, só chega e
        para) quanto pelo Taskbar Sit (`ao_chegar` inicia a transição de
        sentar, ver `_executar_taskbar_sit`) quando ela está longe demais
        da barra pra simplesmente deslizar até lá sem nenhuma animação de
        voo (bug real reportado pelo usuário, 2026-08-29: "se ela tiver
        numa posição alta, ela tem que fazer animação de descer")."""
        self._destino_ativo = (alvo_x, alvo_y)
        self._destino_ao_chegar = ao_chegar
        self._destino_tolerancia_px = tolerancia_px
        self._saltos_destino_restantes = max_saltos
        self._continuar_perseguicao()

    def _continuar_perseguicao(self) -> None:
        if self._destino_ativo is None:
            return
        tx, ty = self._destino_ativo
        dx, dy = tx - self._window.x(), ty - self._window.y()
        distancia = math.hypot(dx, dy)
        if distancia <= self._destino_tolerancia_px or self._saltos_destino_restantes <= 0:
            ao_chegar, self._destino_ativo = self._destino_ao_chegar, None
            if ao_chegar is not None:
                ao_chegar()
            else:
                self._ocupado = False
            return
        disponiveis = self._direcoes_disponiveis()
        if not disponiveis:
            self._destino_ativo = None
            self._ocupado = False
            return
        direcao = self._direcao_mais_proxima(dx, dy, disponiveis)
        ux, uy = DIRECOES_VETOR[direcao]
        # PROJEÇÃO no eixo escolhido, não a distância reta até o alvo -
        # com a distância reta, um alvo fora de eixo fazia ela ultrapassar
        # o ponto certo NAQUELE eixo e precisar reverter no salto seguinte
        # (bug real, 2026-08-29: "fluxo de girar da esquerda pra direita
        # em vez de só ir pra direita"). A pior discrepância possível
        # entre a direção escolhida (a mais alinhada) e o vetor real é
        # 22,5° - a projeção nunca fica pequena demais por causa disso.
        #
        # SEM teto de `DISTANCIA_WANDER_PX` aqui (diferente do Wander
        # autônomo) - com o teto, um destino a mais de 900px na mesma
        # direção fazia ela FRENAR (animação "parar", volta pro idle) e
        # reiniciar do zero ("iniciar" de novo) só pra continuar na MESMA
        # direção - bug real, 2026-08-29: "as animações não usam o loop
        # corretamente, ela chegou a parar 1x e continuar". Um destino de
        # verdade já sabe a distância exata (não é um passeio aleatório
        # que precisa de teto pra não viajar demais) - um salto só cobre
        # o trecho reto inteiro, sem cortar e retomar no meio.
        distancia_salto = max(0.0, dx * ux + dy * uy)
        # `_pode_avancar` confere com a distância REAL deste salto
        # (`distancia_salto`), não uma sonda genérica grande - com a
        # sonda genérica, uma direção DIAGONAL perto de uma borda podia
        # passar no teste só porque UM dos dois eixos ainda tinha espaço
        # numa distância de sonda grande, mesmo quando o salto de
        # verdade (curto, ex.: Taskbar Sit com o "piso" fora do alcance
        # de voo) não avançava quase nada em NENHUM eixo de fato - ela
        # tocava a animação diagonal inteira parada no lugar (bug real
        # reportado pelo usuário, 2026-08-29: "vi ela na borda da direita
        # e começar fazer movimento diagonal direita inferior, e ficando
        # parado por estar no limite").
        if not self._pode_avancar(direcao, distancia_salto):
            # já encostou no teto/borda da região permitida nessa direção -
            # voar não chega mais perto (ex.: Taskbar Sit mirando um "piso"
            # abaixo do que o voo alcança sem sair da tela). Chega o quanto
            # dá e deixa o passo final (mola precisa, sem essa margem de
            # tela) cobrir o resto, em vez de repetir o mesmo salto parado
            # até estourar `max_saltos` (bug real, 2026-08-29: "ela está
            # tentando descer já estando no ponto mais baixo").
            ao_chegar, self._destino_ativo = self._destino_ao_chegar, None
            if ao_chegar is not None:
                ao_chegar()
            else:
                self._ocupado = False
            return
        self._saltos_destino_restantes -= 1
        self._ocupado = True
        self._iniciar_hop(direcao, distancia_salto, ao_concluir=self._continuar_perseguicao)

    def _iniciar_hop(self, direcao: str, distancia_px: float, ao_concluir: Callable[[], None] | None = None) -> None:
        """Desloca a janela em PARALELO com a animação, não depois dela -
        bug real reportado pelo usuário (2026-08-29): o deslocamento só
        começava depois de `iniciar` terminar de tocar (ela ficava
        "patinando" no lugar por ~4s) e "parar" tocava só depois dela já
        ter chegado (animação de frear rodando parada). `MovimentoComDuracaoFixa`
        corre numa duração CONHECIDA de antemão (`iniciar` + `parar` reais
        do clipe, não uma mola que "chega" num instante imprevisível) -
        isso é o que permite os dois relógios (animação e posição física)
        começarem e terminarem juntos. Compartilhado pelo Wander aleatório
        e por "ir até o destino" - só diferem na direção/distância."""
        if not self._controller.solicitar_transicao(f"flutuando_{direcao}_iniciar"):
            self._ocupado = False
            return

        asset_iniciar = self._repositorio.obter(f"flutuando_{direcao}_iniciar")
        asset_parar = self._repositorio.obter(f"flutuando_{direcao}_parar")
        asset_loop = self._repositorio.obter(f"flutuando_{direcao}_loop")
        duracao_iniciar_ms = asset_iniciar.frame_count * asset_iniciar.frame_duration_ms
        duracao_parar_ms = asset_parar.frame_count * asset_parar.frame_duration_ms
        duracao_loop_ms = asset_loop.frame_count * asset_loop.frame_duration_ms
        # quantas voltas do loop cabem nessa distância - sem isso ela
        # cortava o loop assim que entrava nele (bug real, 2026-08-29:
        # "faz iniciar->loop->pausa, em vez de repetir o loop"); mínimo de
        # 1 volta inteira sempre, mesmo pra saltos curtos. `velocidade_voo`
        # (config, pedido do usuário 2026-08-29: "tem como deixar ela mais
        # rápida?") escala quanto CHÃO cada volta cobre, não o ritmo do
        # bater de asas/pernas do clipe - aumenta a velocidade física sem
        # deixar a animação com cara de acelerada/derrapando.
        distancia_por_ciclo_efetiva = DISTANCIA_POR_CICLO_LOOP_PX * self._config.get("velocidade_voo", 1.0)
        ciclos_loop = max(CICLOS_LOOP_MINIMO, round(distancia_px / distancia_por_ciclo_efetiva))
        duracao_cruzeiro_ms = ciclos_loop * duracao_loop_ms

        dx, dy = DIRECOES_VETOR[direcao]
        # geometria de TODOS os monitores PERMITIDOS (não só a atual) -
        # sem isso ela nunca conseguia atravessar de tela, ficava sempre
        # clampada na mesma (bug real reportado, 2026-08-29); a lista de
        # permitidos (config `monitores_permitidos`) deixa o usuário
        # restringir onde ela pode ficar.
        area_x, area_y, area_largura, area_altura = self._geometria_permitida()
        m = MARGEM_TELA_WANDER_PX
        x_alvo = _clamp_para_direcao(
            self._window.x(),
            self._window.x() + dx * distancia_px,
            area_x + m,
            area_x + area_largura - self._window.width() - m,
        )
        y_alvo = _clamp_para_direcao(
            self._window.y(),
            self._window.y() + dy * distancia_px,
            area_y + m,
            area_y + area_altura - self._window.height() - m,
        )

        self._movimento_wander.iniciar(
            lambda: (self._window.x(), self._window.y()),
            lambda x, y: self._window.move(int(x), int(y)),
            (x_alvo, y_alvo),
            duracao_iniciar_ms,
            duracao_cruzeiro_ms,
            duracao_parar_ms,
        )

        estado_movimento_alvo = f"flutuando-{direcao}"

        def _pedir_parada() -> None:
            if self._controller.estado_logico != estado_movimento_alvo:
                return  # já saiu do loop por outro motivo enquanto o timer de cruzeiro esperava
            if not self._controller.solicitar_transicao(f"flutuando_{direcao}_parar"):
                self._ocupado = False
                return
            self._aguardar_fim_wander(ao_concluir)

        def _ao_entrar_no_loop(estado: str) -> None:
            if estado != estado_movimento_alvo:
                return  # emissão de outro estado no meio do caminho - ainda não chegou
            self._controller.estado_alterado.disconnect(_ao_entrar_no_loop)
            # espera o loop dar suas voltas de verdade (`ciclos_loop`)
            # antes de pedir "parar" - sem isso ela cortava a volta no
            # meio, mal entrando no loop (bug real, 2026-08-29). A
            # duração total já foi calibrada pra esse tempo de cruzeiro +
            # iniciar + parar coincidir com o fim do deslocamento físico.
            QTimer.singleShot(duracao_cruzeiro_ms, _pedir_parada)

        self._controller.estado_alterado.connect(_ao_entrar_no_loop)

    def _aguardar_fim_wander(self, ao_concluir: Callable[[], None] | None = None) -> None:
        """Só libera `_ocupado` quando a ANIMAÇÃO ("parar" terminou, voltou
        pro `flutuando_idle`) e o DESLOCAMENTO FÍSICO já tiverem os dois
        acabado - calibrados pra terminar juntos, mas não são a mesma
        coisa (dois relógios reais independentes, um por quadro, outro a
        cada passo de física); liberar só no primeiro dos dois a
        terminar deixava o scheduler livre pra escolher um Behavior novo
        (inclusive outro Wander) enquanto o deslocamento anterior ainda
        estava rodando, resetando ele no meio do caminho."""
        pendente = {"animacao": True, "movimento": self._movimento_wander.em_andamento}

        def _tentar_liberar() -> None:
            if not any(pendente.values()):
                self._ocupado = False
                if ao_concluir is not None:
                    ao_concluir()

        def _ao_animacao_terminar(_estado: str) -> None:
            self._controller.estado_alterado.disconnect(_ao_animacao_terminar)
            pendente["animacao"] = False
            _tentar_liberar()

        def _ao_movimento_terminar() -> None:
            self._movimento_wander.finalizado.disconnect(_ao_movimento_terminar)
            pendente["movimento"] = False
            _tentar_liberar()

        self._controller.estado_alterado.connect(_ao_animacao_terminar)
        if pendente["movimento"]:
            self._movimento_wander.finalizado.connect(_ao_movimento_terminar)
        else:
            _tentar_liberar()

    def _familia_disponivel(self, animation_id: str, agora: float) -> bool:
        """Cooldown por FAMÍLIA (tag), não só por Behavior inteiro - sem
        isso, `sentada_rindo` -> `sentada_gargalhada_caindo` ->
        `sentada_risada-esnobe` em sequência é uma repetição óbvia pro
        usuário mesmo sendo 3 ids "diferentes" pro scheduler."""
        for tag in state_catalog.CATALOGO[animation_id].tags:
            if tag == "action":
                continue
            ultimo = self._ultimo_disparo_por_familia.get(tag)
            if ultimo is not None and agora - ultimo < COOLDOWN_FAMILIA_SEGUNDOS:
                return False
        return True

    def _conectar_liberar_ocupado(self) -> None:
        self._conectar_callback_estado(self._liberar_ocupado)

    def _conectar_callback_estado(self, callback: Callable[[str], None]) -> None:
        self._controller.estado_alterado.connect(callback)
        self._callback_estado_pendente = callback

    def _liberar_ocupado(self, _estado: str) -> None:
        self._controller.estado_alterado.disconnect(self._liberar_ocupado)
        self._callback_estado_pendente = None
        self._ocupado = False
