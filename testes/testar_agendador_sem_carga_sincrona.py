# -*- coding: utf-8 -*-
"""O agendador de comportamentos nunca carrega clipe na thread da interface.

Regressão de 2026-11-14 ("ela ta dando umas travadas vez ou outra, parece q
para de responder"): `Behavior.elegivel` chamava `AssetRepository.obter()`
para cada candidato, e com ela sentada os 16 clipes de variação eram
decodificados a cada tick, travando a Gala por 5 a 13 s. Aqui `obter()`
explode se for chamado: o tick e a variação sentada só podem olhar a
existência dos clipes. Roda offscreen, sem tela."""
import os
import sys
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mascot import behavior_scheduler
from mascot.behavior_scheduler import ANIMACOES_VARIACOES_SENTADAS, Behavior, BehaviorScheduler

_falhas = []


def checar(nome, condicao, detalhe=""):
    if condicao:
        print(f"PASS: {nome}")
    else:
        print(f"FAIL: {nome} {detalhe}")
        _falhas.append(nome)


class RepositorioQueNaoCarrega:
    """Só lista o que existe; qualquer carga síncrona é falha do teste."""

    def __init__(self, ids):
        self._ids = list(ids)
        self.chamadas_obter = []

    def ids_disponiveis(self):
        return list(self._ids)

    def obter(self, animation_id):
        self.chamadas_obter.append(animation_id)
        raise AssertionError(f"obter({animation_id}) síncrono chamado pelo agendador")


# --- Behavior.elegivel olha só a existência --------------------------------
existentes = frozenset(ANIMACOES_VARIACOES_SENTADAS[:1])
variacao = Behavior(id="sitting_variations", peso=1, cooldown_segundos=0, orcamento_por_hora=99,
                    assets_necessarios=ANIMACOES_VARIACOES_SENTADAS, executar=lambda: None)
checar("elegível quando ao menos um clipe existe", variacao.elegivel(time.monotonic(), existentes) is True)
checar("inelegível quando nenhum clipe existe", variacao.elegivel(time.monotonic(), frozenset()) is False)

# --- tick inteiro e escolha da variação, sem carga -------------------------
repositorio = RepositorioQueNaoCarrega(ANIMACOES_VARIACOES_SENTADAS)
pedidas = []
controlador = SimpleNamespace(
    animacao_atual="sentada_balancando-pernas",
    estado_logico="sentada",
    solicitar_transicao=lambda id_: pedidas.append(id_) or True,
)
agendador = SimpleNamespace(
    _repositorio=repositorio,
    _controller=controlador,
    _ultimo_disparo_por_familia={},
    _ids_existentes=frozenset(repositorio.ids_disponiveis()),
    _ocupado=False,
    _conectar_liberar_ocupado=lambda: None,
)
agendador._familia_disponivel = lambda id_, agora: BehaviorScheduler._familia_disponivel(agendador, id_, agora)
try:
    BehaviorScheduler._executar_variacao_sentada(agendador)
    checar("variação sentada escolhe sem carregar nada", repositorio.chamadas_obter == [], repositorio.chamadas_obter)
    checar("a variação escolhida é pedida à transição (que carrega em segundo plano)",
           len(pedidas) == 1 and pedidas[0] in ANIMACOES_VARIACOES_SENTADAS, pedidas)
except AssertionError as erro:
    checar("variação sentada escolhe sem carregar nada", False, erro)

checar("o módulo do agendador não chama obter() em lugar nenhum",
       ".obter(" not in "\n".join(
           linha for linha in open(behavior_scheduler.__file__, encoding="utf-8")
           if not linha.lstrip().startswith(("#", "`")) and "AssetRepository.obter()" not in linha))

print()
if _falhas:
    print(f"{len(_falhas)} FALHA(S): {_falhas}")
    sys.exit(1)
print("Todos os casos passaram.")
