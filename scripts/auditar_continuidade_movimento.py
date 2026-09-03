"""Audita visualmente as emendas iniciar -> loop -> parar do Mascot.

Gera uma folha de contato com os quadros de fronteira, outra com os oito
últimos quadros de cada parada e um JSON com diferenças calculadas apenas
sobre a personagem (o fundo verde é ignorado).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "data" / "animacoes_galateia.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "assets" / "galateia" / "animations" / "qa_continuidade"
DIRECOES = (
    "direita",
    "esquerda",
    "subida",
    "descida",
    "superior-direita",
    "superior-esquerda",
    "inferior-direita",
    "inferior-esquerda",
)


def carregar_fontes(config_path: Path) -> dict[str, Path]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return {
        str(item["id"]): Path(str(item["source"]))
        for item in data["animations"]
        if item.get("source")
    }


def ler_quadros(path: Path) -> list[np.ndarray]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"Não foi possível abrir {path}")
    frames: list[np.ndarray] = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        capture.release()
    if not frames:
        raise ValueError(f"Vídeo sem quadros: {path}")
    return frames


def mascara_personagem(frame: np.ndarray) -> np.ndarray:
    red = frame[..., 0].astype(np.int16)
    green = frame[..., 1].astype(np.int16)
    blue = frame[..., 2].astype(np.int16)
    fundo_verde = (green > 70) & (green > red + 22) & (green > blue + 18)
    return ~fundo_verde


def diferenca(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    mask = mascara_personagem(a) | mascara_personagem(b)
    if not np.any(mask):
        return {"mae": 0.0, "pixelsAlteradosPct": 0.0}
    delta = np.abs(a.astype(np.int16) - b.astype(np.int16)).mean(axis=2)
    values = delta[mask]
    return {
        "mae": round(float(values.mean()), 3),
        "pixelsAlteradosPct": round(float((values > 24).mean() * 100), 3),
    }


def melhor_emenda(
    anteriores: list[np.ndarray], posteriores: list[np.ndarray], janela: int = 24
) -> dict[str, object]:
    inicio_anterior = max(0, len(anteriores) - janela)
    fim_posterior = min(len(posteriores), janela)
    anteriores_reduzidos = [
        cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
        for frame in anteriores[inicio_anterior:]
    ]
    posteriores_reduzidos = [
        cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
        for frame in posteriores[:fim_posterior]
    ]
    candidatos: list[tuple[float, int, int, dict[str, float]]] = []
    for offset_a, frame_a in enumerate(anteriores_reduzidos):
        index_a = inicio_anterior + offset_a
        for index_b, frame_b in enumerate(posteriores_reduzidos):
            score = diferenca(frame_a, frame_b)
            candidatos.append((score["mae"], index_a, index_b, score))
    _, index_a, index_b, score = min(candidatos, key=lambda item: item[0])
    return {"quadroAnterior": index_a, "quadroPosterior": index_b, **score}


def miniatura(frame: np.ndarray, width: int = 256, height: int = 144) -> Image.Image:
    return Image.fromarray(frame).resize((width, height), Image.Resampling.LANCZOS)


def folha_fronteiras(rows: list[tuple[str, list[np.ndarray]]], output: Path) -> None:
    labels = ("idle fim", "início iniciar", "fim iniciar", "início loop", "fim loop", "início parar", "fim parar")
    cell_w, cell_h, left, top = 256, 144, 190, 34
    sheet = Image.new("RGB", (left + cell_w * len(labels), top + cell_h * len(rows)), "#151518")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for column, label in enumerate(labels):
        draw.text((left + column * cell_w + 6, 10), label, fill="white", font=font)
    for row, (direction, frames) in enumerate(rows):
        y = top + row * cell_h
        draw.text((8, y + cell_h // 2 - 5), direction, fill="white", font=font)
        for column, frame in enumerate(frames):
            sheet.paste(miniatura(frame, cell_w, cell_h), (left + column * cell_w, y))
    sheet.save(output)


def folha_finais(rows: list[tuple[str, list[np.ndarray]]], output: Path) -> None:
    cell_w, cell_h, left, top = 192, 108, 190, 34
    count = max(len(frames) for _, frames in rows)
    sheet = Image.new("RGB", (left + cell_w * count, top + cell_h * len(rows)), "#151518")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for column in range(count):
        draw.text((left + column * cell_w + 6, 10), f"-{count - column}", fill="white", font=font)
    for row, (direction, frames) in enumerate(rows):
        y = top + row * cell_h
        draw.text((8, y + cell_h // 2 - 5), direction, fill="white", font=font)
        for column, frame in enumerate(frames):
            sheet.paste(miniatura(frame, cell_w, cell_h), (left + column * cell_w, y))
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audita emendas dos vídeos direcionais da Galateia.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    sources = carregar_fontes(args.config.resolve())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    idle = ler_quadros(sources["sentada_para_flutuando"])[-1]
    boundary_rows: list[tuple[str, list[np.ndarray]]] = []
    ending_rows: list[tuple[str, list[np.ndarray]]] = []
    report: dict[str, object] = {"schemaVersion": 1, "directions": {}}

    for direction in DIRECOES:
        prefix = f"flutuando_{direction}"
        iniciar = ler_quadros(sources[f"{prefix}_iniciar"])
        loop = ler_quadros(sources[f"{prefix}_loop"])
        parar = ler_quadros(sources[f"{prefix}_parar"])
        boundary_rows.append(
            (direction, [idle, iniciar[0], iniciar[-1], loop[0], loop[-1], parar[0], parar[-1]])
        )
        ending_rows.append((direction, parar[-8:]))
        report["directions"][direction] = {
            "idleParaIniciar": diferenca(idle, iniciar[0]),
            "iniciarParaLoop": diferenca(iniciar[-1], loop[0]),
            "fechamentoLoop": diferenca(loop[-1], loop[0]),
            "loopParaParar": diferenca(loop[-1], parar[0]),
            "pararParaIdle": diferenca(parar[-1], idle),
            "melhoresEmendas": {
                "iniciarParaLoop": melhor_emenda(iniciar, loop),
                "loopParaParar": melhor_emenda(loop, parar),
            },
            "frames": {"iniciar": len(iniciar), "loop": len(loop), "parar": len(parar)},
        }

    folha_fronteiras(boundary_rows, output / "fronteiras_movimento.png")
    folha_finais(ending_rows, output / "ultimos_quadros_parar.png")
    (output / "continuidade.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"ok": True, "output": str(output), **report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
