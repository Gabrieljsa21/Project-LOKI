# -*- coding: utf-8 -*-
"""Física de corpo inteiro do Mascot/LOKI (plano, seção 7.3) - só posição,
velocidade e damping globais, sem constraints entre membros nem rig (o
MVP usa sprites inteiros, nunca camadas independentes).

Duas ferramentas, dois casos DIFERENTES de propósito:
- `MovimentoAmortecido` (mola, convergência assintótica) - "queda curta e
  acomodação" ao soltar um arraste (`window.py`) e Taskbar Sit
  (`behavior_scheduler.py`), onde só importa CHEGAR - o instante exato de
  chegada não precisa casar com nenhuma animação.
- `MovimentoComDuracaoFixa` (interpolação com duração conhecida) - Wander
  (`behavior_scheduler.py`), onde o deslocamento físico precisa começar
  JUNTO com a animação `iniciar` e acabar JUNTO com `parar` - uma mola
  não serve aqui porque não dá pra prever de antemão QUANDO ela "chega"
  (bug real reportado pelo usuário, 2026-08-29: ela ficava parada
  esperando a animação de iniciar terminar pra só então começar a se
  mover de verdade, e a animação de parar tocava depois dela já estar
  parada - as duas coisas rodavam em relógios desincronizados).

`obter_posicao`/`mover_para` são callables injetados (não uma referência
direta a `QWidget`) pra dar pra testar a convergência sem precisar de
janela/Qt de verdade.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

PASSO_MS = 16
LIMIAR_REPOUSO_PX = 0.5
LIMIAR_REPOUSO_VELOCIDADE = 2.0


class MovimentoAmortecido(QObject):
    finalizado = Signal()

    def __init__(self, rigidez: float = 40.0, amortecimento: float = 12.0, parent: QObject | None = None):
        super().__init__(parent)
        self._rigidez = rigidez
        self._amortecimento = amortecimento
        self._vx = 0.0
        self._vy = 0.0
        self._x = 0.0
        self._y = 0.0
        self._alvo = (0.0, 0.0)
        self._mover_para = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._passo)

    @property
    def em_andamento(self) -> bool:
        return self._timer.isActive()

    def iniciar(self, obter_posicao, mover_para, alvo: tuple[float, float]) -> None:
        """`obter_posicao()` devolve a posição `(x, y)` inicial (chamada só
        aqui, uma vez); `mover_para(x, y)` aplica a posição calculada a
        cada passo. Depois de iniciar, a simulação usa SÓ o próprio estado
        interno em ponto flutuante como fonte de verdade - nunca relê a
        posição de volta do alvo real. Sem isso, um alvo que trunca pra
        inteiro (ex.: `QWidget.move(int(x), int(y))`) descarta a fração de
        pixel calculada a cada passo, e a simulação pode ficar PRESA sem
        nunca convergir: o incremento de posição (`vy * dt`, geralmente
        bem menor que 1px por passo) nunca se acumula, porque cada passo
        reparte do zero a partir do inteiro truncado do passo anterior."""
        self.parar()
        self._x, self._y = obter_posicao()
        self._mover_para = mover_para
        self._alvo = alvo
        self._vx = 0.0
        self._vy = 0.0
        self._timer.start(PASSO_MS)

    def parar(self) -> None:
        self._timer.stop()

    def _passo(self) -> None:
        dt = PASSO_MS / 1000
        x, y = self._x, self._y
        ax, ay = self._alvo

        self._vx += ((ax - x) * self._rigidez - self._vx * self._amortecimento) * dt
        self._vy += ((ay - y) * self._rigidez - self._vy * self._amortecimento) * dt
        nx, ny = x + self._vx * dt, y + self._vy * dt

        chegou = (
            abs(ax - nx) < LIMIAR_REPOUSO_PX
            and abs(ay - ny) < LIMIAR_REPOUSO_PX
            and abs(self._vx) < LIMIAR_REPOUSO_VELOCIDADE
            and abs(self._vy) < LIMIAR_REPOUSO_VELOCIDADE
        )
        if chegou:
            self._x, self._y = ax, ay
            self._mover_para(ax, ay)
            self._timer.stop()
            self.finalizado.emit()
        else:
            self._x, self._y = nx, ny
            self._mover_para(nx, ny)


def _integral_suave(s: float) -> float:
    """Integral de 0 a `s` (limitado a [0,1]) do smoothstep `u²(3-2u)` -
    fecha em `s³ - s⁴/2`. Usada pra achar o DESLOCAMENTO (não só a
    velocidade instantânea) percorrido durante uma rampa de
    aceleração/desaceleração - ver `MovimentoComDuracaoFixa._fracao_percorrida`."""
    s = max(0.0, min(1.0, s))
    return s**3 - (s**4) / 2


class MovimentoComDuracaoFixa(QObject):
    """Interpolação com início/fim previsíveis (durações conhecidas de
    antemão), mas o tempo total NUNCA varia com a distância nem com
    nenhum limiar de convergência, ao contrário de `MovimentoAmortecido`.
    É isso que permite agendar a animação de parar pra terminar junto com
    o deslocamento, em vez de só depois que ele já parou.

    Perfil de velocidade TRAPEZOIDAL (acelera/cruza/desacelera), não uma
    única curva smoothstep cobrindo a viagem inteira - essa era suave
    demais bem no começo e no fim (a curva satura perto das pontas), e
    como o clipe `iniciar` inteiro cabe dentro dessa região quase parada,
    ela parecia começar a voar bem antes de realmente saber do lugar
    (bug real reportado pelo usuário, 2026-08-29: "travamento no início
    de cada fluxo de ação"). Agora a rampa de aceleração dura EXATAMENTE
    `duracao_iniciar_ms` (a duração real do clipe), o cruzeiro anda em
    velocidade CONSTANTE (`duracao_cruzeiro_ms`, o loop), e a rampa de
    frenagem dura `duracao_parar_ms` - cada fase da física combina com a
    fase real da animação, em vez de uma curva só que ignora onde cada
    clipe começa/termina."""

    finalizado = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._duracao_iniciar_ms = 1.0
        self._duracao_cruzeiro_ms = 0.0
        self._duracao_parar_ms = 1.0
        self._duracao_total_ms = 1.0
        self._decorrido_ms = 0.0
        self._origem = (0.0, 0.0)
        self._alvo = (0.0, 0.0)
        self._mover_para = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._passo)

    @property
    def em_andamento(self) -> bool:
        return self._timer.isActive()

    def iniciar(
        self,
        obter_posicao,
        mover_para,
        alvo: tuple[float, float],
        duracao_iniciar_ms: float,
        duracao_cruzeiro_ms: float,
        duracao_parar_ms: float,
    ) -> None:
        """As 3 durações por chamada (não no construtor) - a mesma
        instância é reaproveitada pra deslocamentos diferentes (cada
        direção/distância do Wander e da perseguição de destino tem sua
        própria combinação real de iniciar/cruzeiro/parar)."""
        self.parar()
        self._duracao_iniciar_ms = max(1.0, duracao_iniciar_ms)
        self._duracao_cruzeiro_ms = max(0.0, duracao_cruzeiro_ms)
        self._duracao_parar_ms = max(1.0, duracao_parar_ms)
        self._duracao_total_ms = self._duracao_iniciar_ms + self._duracao_cruzeiro_ms + self._duracao_parar_ms
        self._origem = obter_posicao()
        self._alvo = alvo
        self._mover_para = mover_para
        self._decorrido_ms = 0.0
        self._timer.start(PASSO_MS)

    def parar(self) -> None:
        self._timer.stop()

    def _fracao_percorrida(self, t_ms: float) -> float:
        """Fração [0,1] da distância total já percorrida em `t_ms`,
        seguindo o perfil trapezoidal (ease-in / cruzeiro / ease-out).
        `peso_total` é a área sob a curva de velocidade NORMALIZADA
        (velocidade de cruzeiro = 1) - dividir por ela é o que garante
        chegar exatamente no alvo ao fim de `duracao_total_ms`, seja
        qual for a proporção entre as 3 fases."""
        a, b, c = self._duracao_iniciar_ms, self._duracao_cruzeiro_ms, self._duracao_parar_ms
        peso_total = a / 2 + b + c / 2
        if t_ms <= a:
            percorrido = a * _integral_suave(t_ms / a)
        elif t_ms <= a + b:
            percorrido = a / 2 + (t_ms - a)
        else:
            s = (t_ms - a - b) / c
            percorrido = a / 2 + b + c * (0.5 - _integral_suave(1 - s))
        return percorrido / peso_total

    def _passo(self) -> None:
        self._decorrido_ms += PASSO_MS
        t = min(self._decorrido_ms, self._duracao_total_ms)
        fracao = self._fracao_percorrida(t)
        x = self._origem[0] + (self._alvo[0] - self._origem[0]) * fracao
        y = self._origem[1] + (self._alvo[1] - self._origem[1]) * fracao
        if self._decorrido_ms >= self._duracao_total_ms:
            self._mover_para(*self._alvo)
            self._timer.stop()
            self.finalizado.emit()
        else:
            self._mover_para(x, y)


class MovimentoQuedaGravidade(QObject):
    """Queda de arrasto (`MascotWindow`) - pausa parada no lugar, depois
    acelera CONTINUAMENTE até o fim, nunca desacelerando (pedido do
    usuário, 2026-08-29: "ela pode ficar no local por 1s, e só então
    começar a cair, mas numa velocidade menor do que no loop. É assim
    que funciona gravidade"). Diferente de `MovimentoComDuracaoFixa`
    (que acelera, cruza em velocidade CONSTANTE e desacelera no fim) -
    aqui a velocidade cresce o tempo INTEIRO da queda (`fração = t²`,
    igual queda livre real: distância ∝ tempo²), porque a arte do clipe
    de queda continua em movimento franco até o último quadro (sem
    nenhum quadro de pouso/desaceleração pra combinar)."""

    finalizado = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._pausa_ms = 0.0
        self._duracao_queda_ms = 1.0
        self._decorrido_ms = 0.0
        self._origem = (0.0, 0.0)
        self._alvo = (0.0, 0.0)
        self._mover_para = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._passo)

    @property
    def em_andamento(self) -> bool:
        return self._timer.isActive()

    def iniciar(
        self, obter_posicao, mover_para, alvo: tuple[float, float], pausa_ms: float, duracao_queda_ms: float
    ) -> None:
        self.parar()
        self._pausa_ms = max(0.0, pausa_ms)
        self._duracao_queda_ms = max(1.0, duracao_queda_ms)
        self._origem = obter_posicao()
        self._alvo = alvo
        self._mover_para = mover_para
        self._decorrido_ms = 0.0
        self._timer.start(PASSO_MS)

    def parar(self) -> None:
        self._timer.stop()

    def _passo(self) -> None:
        self._decorrido_ms += PASSO_MS
        duracao_total_ms = self._pausa_ms + self._duracao_queda_ms
        t_queda = max(0.0, min(self._decorrido_ms, duracao_total_ms) - self._pausa_ms)
        fracao = (t_queda / self._duracao_queda_ms) ** 2
        x = self._origem[0] + (self._alvo[0] - self._origem[0]) * fracao
        y = self._origem[1] + (self._alvo[1] - self._origem[1]) * fracao
        if self._decorrido_ms >= duracao_total_ms:
            self._mover_para(*self._alvo)
            self._timer.stop()
            self.finalizado.emit()
        else:
            self._mover_para(x, y)
