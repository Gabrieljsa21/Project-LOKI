# -*- coding: utf-8 -*-
"""Extrai miniaturas somente das ações selecionadas na Gesture Wheel."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops


RAIZ = Path(__file__).resolve().parents[1]
PASTA_ANIMACOES = RAIZ / "assets" / "galateia" / "animations"
PASTA_SAIDA = RAIZ / "assets" / "gesture_wheel" / "icons" / "auto"
CONFIG_RODA = RAIZ / "data" / "gesture_wheel.json"
PREFIXO_AUTO = "assets/gesture_wheel/icons/auto/"

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from mascot import state_catalog  # noqa: E402


def ler_json(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def salvar_json_atomico(caminho: Path, dados: object) -> None:
    handle, nome_temporario = tempfile.mkstemp(prefix=f".{caminho.name}.", suffix=".tmp", dir=caminho.parent)
    os.close(handle)
    temporario = Path(nome_temporario)
    try:
        temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporario, caminho)
    finally:
        temporario.unlink(missing_ok=True)


def eh_movimento(animation_id: str) -> bool:
    entrada = state_catalog.CATALOGO.get(animation_id)
    tags = set(entrada.tags if entrada else ())
    return "movement" in tags


def carregar_frames(animation_id: str) -> tuple[list[Image.Image], dict]:
    pasta = PASTA_ANIMACOES / animation_id
    manifesto = ler_json(pasta / "animation.json")
    grade = manifesto["grid"]
    colunas = int(grade["columns"])
    largura = int(grade["cellWidth"])
    altura = int(grade["cellHeight"])
    quantidade = int(manifesto["frameCount"])
    with Image.open(pasta / str(manifesto.get("texture", "spritesheet.webp"))) as origem:
        atlas = origem.convert("RGBA")
        frames = [
            atlas.crop((
                (indice % colunas) * largura,
                (indice // colunas) * altura,
                (indice % colunas + 1) * largura,
                (indice // colunas + 1) * altura,
            ))
            for indice in range(quantidade)
        ]
    return frames, manifesto


def quadro_comparacao(frame: Image.Image) -> Image.Image:
    reduzido = frame.resize((48, 48), Image.Resampling.BILINEAR)
    fundo = Image.new("RGBA", reduzido.size, (17, 24, 30, 255))
    return Image.alpha_composite(fundo, reduzido).convert("RGB")


def distancia_visual(a: Image.Image, b: Image.Image) -> float:
    histograma = ImageChops.difference(a, b).histogram()
    return sum((valor % 256) * total for valor, total in enumerate(histograma))


def indice_semantico(animation_id: str, quantidade: int) -> int | None:
    proporcao = None
    if animation_id.startswith("flutuando_para_"):
        proporcao = 0.84
    elif animation_id.endswith("_para_flutuando"):
        proporcao = 0.16
    elif animation_id.endswith("_iniciar"):
        proporcao = 0.78
    elif animation_id.endswith("_parar"):
        proporcao = 0.22
    elif "_para_" in animation_id:
        proporcao = 0.50
    if proporcao is None:
        return None
    return min(quantidade - 1, max(0, round((quantidade - 1) * proporcao)))


def escolher_indice(animation_id: str, frames: list[Image.Image], loop: bool) -> int:
    semantico = indice_semantico(animation_id, len(frames))
    if semantico is not None:
        return semantico
    if len(frames) < 3:
        return len(frames) // 2
    comparados = [quadro_comparacao(frame) for frame in frames]
    primeiro, ultimo = comparados[0], comparados[-1]
    inicio = max(1, round((len(frames) - 1) * 0.10))
    fim = min(len(frames) - 2, round((len(frames) - 1) * 0.90))
    centro = (len(frames) - 1) / 2

    def pontuacao(indice: int) -> tuple[float, float]:
        primeira = distancia_visual(comparados[indice], primeiro)
        ultima = distancia_visual(comparados[indice], ultimo)
        destaque = primeira if loop else primeira + ultima
        return destaque, -abs(indice - centro)

    return max(range(inicio, fim + 1), key=pontuacao)


def criar_icone(frame: Image.Image, tamanho: int = 128) -> Image.Image:
    caixa = frame.getchannel("A").getbbox()
    if caixa:
        frame = frame.crop(caixa)
    frame.thumbnail((tamanho - 10, tamanho - 10), Image.Resampling.LANCZOS)
    icone = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    icone.alpha_composite(frame, ((tamanho - frame.width) // 2, (tamanho - frame.height) // 2))
    return icone


def sincronizar(apenas: set[str] | None = None, *, forcar: bool = False) -> dict[str, int]:
    config = ler_json(CONFIG_RODA)
    selecionadas = [
        str(item.get("id")) for item in config.get("acoes", [])
        if isinstance(item, dict) and item.get("id") in state_catalog.CATALOGO
    ]
    candidatas = [aid for aid in selecionadas if not eh_movimento(aid) and (apenas is None or aid in apenas)]
    imagens = dict(config.get("imagens") or {})
    geradas = personalizadas = ausentes = 0
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)

    if apenas is None:
        permitidas = set(candidatas)
        imagens = {
            aid: caminho for aid, caminho in imagens.items()
            if not (isinstance(caminho, str) and caminho.replace("\\", "/").startswith(PREFIXO_AUTO) and aid not in permitidas)
        }

    for animation_id in candidatas:
        atual = imagens.get(animation_id)
        automatico = isinstance(atual, str) and atual.replace("\\", "/").startswith(PREFIXO_AUTO)
        if atual and not automatico and not forcar:
            personalizadas += 1
            continue
        try:
            frames, manifesto = carregar_frames(animation_id)
        except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
            ausentes += 1
            continue
        indice = escolher_indice(animation_id, frames, bool(manifesto.get("loop", False)))
        destino = PASTA_SAIDA / f"{animation_id}.png"
        criar_icone(frames[indice]).save(destino, "PNG", optimize=True)
        imagens[animation_id] = destino.relative_to(RAIZ).as_posix()
        geradas += 1

    config["imagens"] = imagens
    salvar_json_atomico(CONFIG_RODA, config)
    return {
        "selecionadas": len(selecionadas), "movimentosComSeta": sum(eh_movimento(aid) for aid in selecionadas),
        "geradas": geradas, "personalizadasPreservadas": personalizadas, "assetsAusentes": ausentes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria miniaturas das ações atualmente selecionadas na roda.")
    parser.add_argument("--only", action="append", help="Atualiza apenas este id; pode ser repetido.")
    parser.add_argument("--force", action="store_true", help="Permite substituir uma imagem manual.")
    args = parser.parse_args()
    resultado = sincronizar(set(args.only) if args.only else None, forcar=args.force)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0 if not resultado["assetsAusentes"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
