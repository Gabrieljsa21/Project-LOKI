# -*- coding: utf-8 -*-
"""Reação à música do SIREN (`music_listening`): regras de elegibilidade do
`BehaviorScheduler` e validade do estado "tocando" do `MascotApp`, sem
abrir janela nem socket."""
import os
import sys
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mascot import behavior_scheduler, process_main

_falhas = []


def checar(nome, condicao, detalhe=""):
    if condicao:
        print(f"PASS: {nome}")
    else:
        print(f"FAIL: {nome} {detalhe}")
        _falhas.append(nome)


def scheduler_falso(animacao, tocando, ligado=True):
    """Só os atributos que `_elegivel_pelo_estado` lê - o método é chamado
    sem construir o QObject de verdade."""
    return SimpleNamespace(
        _controller=SimpleNamespace(animacao_atual=animacao, estado_logico="sentada"),
        _ouvindo_musica=lambda: bool(ligado) and tocando,
    )


Scheduler = behavior_scheduler.BehaviorScheduler
elegivel = Scheduler._elegivel_pelo_estado
IDLE_SENTADA = "sentada_balancando-pernas"

checar("com música, ela não levanta", elegivel(scheduler_falso(IDLE_SENTADA, True), "stand_up") is False)
checar("com música, ela não sai vagando", elegivel(scheduler_falso("flutuando_idle", True), "wander") is False)
checar("com música, variações sentadas continuam", elegivel(scheduler_falso(IDLE_SENTADA, True), "sitting_variations") is True)
checar("sem música, levantar volta ao normal", elegivel(scheduler_falso(IDLE_SENTADA, False), "stand_up") is True)
checar("sem música, vagar volta ao normal", elegivel(scheduler_falso("flutuando_idle", False), "wander") is True)
checar("toggle desligado ignora a música", elegivel(scheduler_falso(IDLE_SENTADA, True, ligado=False), "stand_up") is True)

falso = SimpleNamespace(_behaviors_config={"music_listening": True}, _musica_tocando=lambda: True)
checar("_ouvindo_musica exige toggle E música", Scheduler._ouvindo_musica(falso) is True)
falso._behaviors_config = {}
checar("_ouvindo_musica é falso sem o toggle", Scheduler._ouvindo_musica(falso) is False)

tocando = process_main.MascotApp.musica_tocando
agora = time.monotonic()
app_falso = SimpleNamespace(playback_state={"playing": True}, _playback_ultimo_evento=agora)
checar("tocando com evento recente", tocando(app_falso) is True)
app_falso._playback_ultimo_evento = agora - process_main.VALIDADE_EVENTO_SIREN_SEGUNDOS - 1
checar("evento velho deixa de contar (SIREN fechou sem avisar)", tocando(app_falso) is False)
app_falso = SimpleNamespace(playback_state={"playing": False}, _playback_ultimo_evento=agora)
checar("pausado não conta como tocando", tocando(app_falso) is False)

if _falhas:
    print(f"\n{len(_falhas)} falha(s)")
    sys.exit(1)
print("\nTudo certo.")
