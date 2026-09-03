"""Importa frames, vídeo ou spritesheet para o runtime leve da Galateia.

O script é determinístico e inteiramente local: remove um fundo de cor conectado às
bordas, preserva o movimento dentro de um recorte comum, monta um atlas WebP e grava
o animation.json consumido pelo avatar.

Exemplos (a partir da pasta assistant/):
    python scripts/importar_animacao.py "E:\\frames" --name flutuando_idle
    python scripts/importar_animacao.py "E:\\idle.mp4" --name flutuando_idle --fps 12
    python scripts/importar_animacao.py "E:\\sheet.png" --name idle --columns 6 --frame-count 34
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANIMATIONS_ROOT = PROJECT_ROOT / "assets" / "galateia" / "animations"
IMAGE_EXTENSIONS = {".png", ".webp", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]


def safe_id(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9_-]+", "-", ascii_value)
    normalized = re.sub(r"-+", "-", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_-")
    if not normalized:
        raise ValueError("Não foi possível criar um nome válido para a animação.")
    return normalized


def open_rgba(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA")


def resample_indices(count: int, source_fps: float, target_fps: float) -> list[int]:
    if target_fps >= source_fps:
        return list(range(count))
    duration = count / source_fps
    sample_times = np.arange(0.0, duration, 1.0 / target_fps)
    indices = np.minimum((sample_times * source_fps + 1e-9).astype(int), count - 1)
    return list(dict.fromkeys(int(index) for index in indices))


def load_frame_folder(
    source: Path,
    source_fps: float | None = None,
    target_fps: float | None = None,
) -> list[Image.Image]:
    paths = sorted(
        (path for path in source.iterdir() if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS),
        key=natural_key,
    )
    if not paths:
        raise ValueError(f"Nenhuma imagem compatível foi encontrada em: {source}")
    if source_fps is not None and target_fps is not None:
        paths = [paths[index] for index in resample_indices(len(paths), source_fps, target_fps)]
    return [open_rgba(path) for path in paths]


def load_video(source: Path, target_fps: float) -> list[Image.Image]:
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError(f"Não foi possível abrir o vídeo: {source}")

    source_fps = float(capture.get(cv2.CAP_PROP_FPS))
    if not math.isfinite(source_fps) or source_fps <= 0:
        source_fps = 30.0

    frames: list[Image.Image] = []
    index = 0
    next_time = 0.0
    interval = 1.0 / target_fps
    while True:
        ok, bgr = capture.read()
        if not ok:
            break
        timestamp = index / source_fps
        if timestamp + 1e-9 >= next_time:
            rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA)
            frames.append(Image.fromarray(rgba, "RGBA"))
            next_time += interval
        index += 1
    capture.release()

    if not frames:
        raise ValueError(f"O vídeo não produziu nenhum frame: {source}")
    return frames


def load_sheet(source: Path, columns: int | None, rows: int | None, frame_count: int | None) -> list[Image.Image]:
    if not columns or columns < 1:
        raise ValueError("Para uma folha única, informe --columns.")
    sheet = open_rgba(source)
    if rows is None:
        if frame_count is None:
            raise ValueError("Para uma folha única, informe --rows ou --frame-count.")
        rows = math.ceil(frame_count / columns)
    if rows < 1 or sheet.width % columns or sheet.height % rows:
        raise ValueError(
            f"A folha {sheet.width}x{sheet.height} não pode ser dividida exatamente em {columns}x{rows}."
        )

    total_cells = columns * rows
    count = frame_count if frame_count is not None else total_cells
    if not 1 <= count <= total_cells:
        raise ValueError(f"--frame-count deve estar entre 1 e {total_cells}.")

    cell_width = sheet.width // columns
    cell_height = sheet.height // rows
    return [
        sheet.crop(
            (
                (index % columns) * cell_width,
                (index // columns) * cell_height,
                (index % columns + 1) * cell_width,
                (index // columns + 1) * cell_height,
            )
        )
        for index in range(count)
    ]


def detect_source_type(source: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    if source.is_dir():
        return "frames"
    suffix = source.suffix.casefold()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in IMAGE_EXTENSIONS:
        return "sheet"
    raise ValueError(f"Formato de entrada não reconhecido: {source}")


def load_source(args: argparse.Namespace) -> tuple[list[Image.Image], str]:
    source_type = detect_source_type(args.source, args.source_type)
    if source_type == "frames":
        if not args.source.is_dir():
            raise ValueError("A entrada do tipo frames precisa ser uma pasta.")
        frames = load_frame_folder(args.source, args.source_fps, args.fps)
    elif source_type == "video":
        frames = load_video(args.source, args.fps)
    else:
        frames = load_sheet(args.source, args.columns, args.rows, args.frame_count)
    return frames, source_type


def resample_frames(frames: list[Image.Image], source_fps: float, target_fps: float) -> list[Image.Image]:
    return [frames[index] for index in resample_indices(len(frames), source_fps, target_fps)]


def validate_equal_canvas(frames: Iterable[Image.Image]) -> tuple[int, int]:
    sizes = {frame.size for frame in frames}
    if len(sizes) != 1:
        readable = ", ".join(f"{width}x{height}" for width, height in sorted(sizes))
        raise ValueError(f"Todos os frames precisam ter o mesmo tamanho. Encontrados: {readable}")
    return next(iter(sizes))


def parse_hex_color(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", value)
    if not match:
        raise ValueError("A cor deve usar o formato #RRGGBB, por exemplo #d83a9f.")
    number = int(match.group(1), 16)
    return number >> 16, (number >> 8) & 255, number & 255


def parse_crop(value: str) -> tuple[int, int, int, int]:
    try:
        left, top, right, bottom = (int(part.strip()) for part in value.split(","))
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(
            "O recorte deve usar left,top,right,bottom, por exemplo 200,60,1000,700."
        ) from None
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise argparse.ArgumentTypeError("Coordenadas inválidas em --fixed-crop.")
    return left, top, right, bottom


def border_pixels(array: np.ndarray) -> np.ndarray:
    return np.concatenate((array[0], array[-1], array[1:-1, 0], array[1:-1, -1]), axis=0)


def infer_key_color(frames: list[Image.Image]) -> tuple[int, int, int]:
    samples: list[np.ndarray] = []
    for frame in frames[: min(8, len(frames))]:
        rgb = np.asarray(frame, dtype=np.uint8)[..., :3]
        samples.append(border_pixels(rgb))
    pixels = np.concatenate(samples, axis=0)
    quantized = pixels // 12
    packed = (
        quantized[:, 0].astype(np.int32) * 22 * 22
        + quantized[:, 1].astype(np.int32) * 22
        + quantized[:, 2].astype(np.int32)
    )
    winner = int(np.bincount(packed).argmax())
    selected = pixels[packed == winner]
    color = np.median(selected, axis=0).astype(np.uint8)
    return int(color[0]), int(color[1]), int(color[2])


def has_useful_transparency(frame: Image.Image) -> bool:
    alpha = np.asarray(frame.getchannel("A"), dtype=np.uint8)
    return float(np.count_nonzero(alpha < 250)) / alpha.size >= 0.002


def connected_border_mask(candidate: np.ndarray) -> np.ndarray:
    count, labels = cv2.connectedComponents(candidate.astype(np.uint8), connectivity=8)
    if count <= 1:
        return np.zeros_like(candidate, dtype=bool)
    edge_labels = np.unique(border_pixels(labels))
    edge_labels = edge_labels[edge_labels != 0]
    return np.isin(labels, edge_labels)


def replace_partial_rgb_with_nearest_interior(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    partial = (alpha > 0) & (alpha < 245)
    known = alpha >= 245
    if not np.any(partial) or not np.any(known):
        return rgb

    distance_input = np.where(known, 0, 255).astype(np.uint8)
    _, labels = cv2.distanceTransformWithLabels(
        distance_input,
        cv2.DIST_L2,
        5,
        labelType=cv2.DIST_LABEL_PIXEL,
    )
    maximum = int(labels.max())
    lookup = np.zeros((maximum + 1, 3), dtype=np.uint8)
    lookup[labels[known]] = rgb[known]
    repaired = rgb.copy()
    repaired[partial] = lookup[labels[partial]]
    return repaired


def replace_chroma_spill(
    rgb: np.ndarray,
    alpha: np.ndarray,
    spill: np.ndarray,
) -> np.ndarray:
    affected = spill & (alpha > 0)
    known = (alpha >= 245) & ~spill
    if not np.any(affected) or not np.any(known):
        return rgb

    distance_input = np.where(known, 0, 255).astype(np.uint8)
    _, labels = cv2.distanceTransformWithLabels(
        distance_input,
        cv2.DIST_L2,
        5,
        labelType=cv2.DIST_LABEL_PIXEL,
    )
    maximum = int(labels.max())
    lookup = np.zeros((maximum + 1, 3), dtype=np.uint8)
    lookup[labels[known]] = rgb[known]
    repaired = rgb.copy()
    repaired[affected] = lookup[labels[affected]]
    return repaired


def remove_chroma_background(
    frame: Image.Image,
    key_color: tuple[int, int, int],
    tolerance: float,
    feather: float,
) -> Image.Image:
    rgba = np.asarray(frame, dtype=np.uint8).copy()
    rgb = rgba[..., :3]
    original_alpha = rgba[..., 3].astype(np.float32)
    key = np.asarray(key_color, dtype=np.float32)
    distance = np.linalg.norm(rgb.astype(np.float32) - key, axis=2)

    key_hsv = cv2.cvtColor(np.uint8([[key_color]]), cv2.COLOR_RGB2HSV)[0, 0].astype(np.float32)
    effective_tolerance = tolerance if key_hsv[1] >= 100.0 else min(tolerance, 32.0)
    effective_feather = feather if key_hsv[1] >= 100.0 else min(feather, 12.0)

    # A distância RGB remove o miolo do fundo. A segunda matte usa matiz e
    # saturação para alcançar variações causadas por gradiente/compressão e também
    # os espaços fechados entre cabelo e roupa. Pele e cabelo branco têm saturação
    # baixa e, portanto, não entram nessa segunda matte.
    rgb_strength = np.clip(
        (effective_tolerance + effective_feather - distance) / max(effective_feather, 1.0),
        0.0,
        1.0,
    )
    rgb_strength *= connected_border_mask(distance <= effective_tolerance + effective_feather)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    hue_distance = np.abs(hsv[..., 0] - key_hsv[0])
    hue_distance = np.minimum(hue_distance, 180.0 - hue_distance)
    # H.264 pode deslocar alguns graus o matiz do mesmo fundo entre cenas ou
    # conforme a iluminação muda. Trate uma faixa curta ao redor da chave como
    # remoção integral; sem esse platô, um desvio pequeno deixava o canvas inteiro
    # com alfa baixo (e aparecia como grandes fragmentos translúcidos no atlas).
    hue_core = 8.0
    hue_strength = np.clip(1.0 - np.maximum(hue_distance - hue_core, 0.0) / 22.0, 0.0, 1.0)
    saturation_floor = 18.0
    # Chroma global só é seguro para fundos realmente saturados (magenta/verde).
    # Rosa claro pode ter matiz e RGB próximos da pele; nesse caso usamos apenas a
    # região conectada às bordas e um núcleo de pixels quase idênticos à chave.
    if key_hsv[1] >= 100.0:
        # A intensidade não deve depender da saturação máxima da chave: halos
        # comprimidos pelo H.264 ficam pouco saturados, mas ainda são claramente
        # verdes/magenta. Uma rampa curta remove esse spill sem tocar branco/cinza.
        saturation_strength = np.clip((hsv[..., 1] - saturation_floor) / 42.0, 0.0, 1.0)
        chroma_strength = hue_strength * saturation_strength
    else:
        chroma_strength = np.zeros_like(distance, dtype=np.float32)

    # O núcleo global alcança fundos presos em espaços fechados, mas só é seguro
    # quando a chave é realmente cromática. Em fundos pastéis (especialmente rosa
    # claro), pixels de pele podem ser quase idênticos à chave; removê-los abre
    # buracos em pernas, rosto e mãos. Nesses casos, limite a remoção à região que
    # comprovadamente se conecta às bordas do quadro.
    if key_hsv[1] >= 100.0:
        exact_feather = 6.0
        exact_strength = np.clip((18.0 + exact_feather - distance) / exact_feather, 0.0, 1.0)
    else:
        exact_strength = np.zeros_like(distance, dtype=np.float32)
    removal_strength = np.maximum.reduce((rgb_strength, chroma_strength, exact_strength))
    factor = 1.0 - removal_strength
    alpha = np.rint(original_alpha * factor).astype(np.uint8)
    rgb = replace_chroma_spill(rgb, alpha, chroma_strength >= 0.16)
    rgb = replace_partial_rgb_with_nearest_interior(rgb, alpha)
    rgb[alpha == 0] = 0
    return Image.fromarray(np.dstack((rgb, alpha)), "RGBA")


def alpha_bbox(frame: Image.Image) -> tuple[int, int, int, int] | None:
    alpha = np.asarray(frame.getchannel("A"), dtype=np.uint8)
    ys, xs = np.nonzero(alpha > 4)
    if not len(xs):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def normalize_frames(
    frames: list[Image.Image],
    preserve_canvas: bool,
    padding: int,
    max_cell: int,
    fixed_crop: tuple[int, int, int, int] | None = None,
    allow_empty_frames: bool = False,
) -> tuple[list[Image.Image], tuple[int, int, int, int]]:
    width, height = validate_equal_canvas(frames)
    boxes = [alpha_bbox(frame) for frame in frames]
    if not allow_empty_frames and any(box is None for box in boxes):
        empty = [str(index) for index, box in enumerate(boxes) if box is None]
        raise ValueError(f"Frames totalmente transparentes: {', '.join(empty)}")
    if not any(box is not None for box in boxes):
        raise ValueError("Todos os frames estão totalmente transparentes.")

    if fixed_crop is not None:
        left, top, right, bottom = fixed_crop
        if right > width or bottom > height:
            raise ValueError(
                f"--fixed-crop {fixed_crop} excede o canvas de origem {width}x{height}."
            )
        crop = fixed_crop
        outside = [
            index
            for index, box in enumerate(boxes)
            if box is not None
            and (box[0] < left or box[1] < top or box[2] > right or box[3] > bottom)
        ]
        if outside:
            shown = ", ".join(map(str, outside[:12]))
            suffix = "..." if len(outside) > 12 else ""
            raise ValueError(
                f"A geometria fixa cortaria os frames {shown}{suffix}. "
                "Recalcule o recorte compartilhado."
            )
    elif preserve_canvas:
        crop = (0, 0, width, height)
    else:
        present = [box for box in boxes if box is not None]
        crop = (
            max(0, min(box[0] for box in present) - padding),
            max(0, min(box[1] for box in present) - padding),
            min(width, max(box[2] for box in present) + padding),
            min(height, max(box[3] for box in present) + padding),
        )

    for index, frame in enumerate(frames):
        frames[index] = frame.crop(crop)
    cell_width, cell_height = frames[0].size
    if max_cell > 0 and max(cell_width, cell_height) > max_cell:
        scale = max_cell / max(cell_width, cell_height)
        resized = (max(1, round(cell_width * scale)), max(1, round(cell_height * scale)))
        for index, frame in enumerate(frames):
            frames[index] = frame.resize(resized, Image.Resampling.LANCZOS)
    return frames, crop


def compose_atlas(frames: list[Image.Image], columns: int) -> tuple[Image.Image, int, list[int]]:
    if columns < 1:
        raise ValueError("O atlas precisa ter pelo menos uma coluna.")
    cell_width, cell_height = frames[0].size
    rows = math.ceil(len(frames) / columns)
    atlas = Image.new("RGBA", (columns * cell_width, rows * cell_height), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        atlas.alpha_composite(frame, ((index % columns) * cell_width, (index // columns) * cell_height))
    return atlas, rows, list(range(len(frames), columns * rows))


def edge_touching_frames(frames: list[Image.Image]) -> list[int]:
    touching: list[int] = []
    for index, frame in enumerate(frames):
        alpha = np.asarray(frame.getchannel("A"), dtype=np.uint8)
        if np.any(alpha[0] > 4) or np.any(alpha[-1] > 4) or np.any(alpha[:, 0] > 4) or np.any(alpha[:, -1] > 4):
            touching.append(index)
    return touching


def save_outputs(
    args: argparse.Namespace,
    frames: list[Image.Image],
    atlas: Image.Image,
    rows: int,
    unused_cells: list[int],
    source_type: str,
    key_color: tuple[int, int, int] | None,
    crop: tuple[int, int, int, int],
    source_canvas: tuple[int, int],
) -> dict[str, object]:
    output = args.output or DEFAULT_ANIMATIONS_ROOT / args.name
    output = output.resolve()
    atlas_path = output / "spritesheet.webp"
    manifest_path = output / "animation.json"
    preview_path = output / "preview.webp"
    targets = [atlas_path, manifest_path] + ([preview_path] if args.preview else [])
    existing = [path for path in targets if path.exists()]
    if existing and not args.force:
        listed = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"A saída já existe ({listed}). Use --force para substituir esses arquivos.")
    output.mkdir(parents=True, exist_ok=True)

    # method 4 mantém ótima compressão, mas evita o custo desproporcional do
    # method 6 em atlases grandes (53 animações, algumas com 120 quadros).
    save_options: dict[str, object] = {"format": "WEBP", "method": 4}
    if args.lossless:
        save_options["lossless"] = True
    else:
        save_options["quality"] = args.quality
    atlas.save(atlas_path, **save_options)

    cell_width, cell_height = frames[0].size
    duration_ms = max(1, round(1000 / args.fps))
    pivot = getattr(args, "pivot_override", None) or (cell_width // 2, cell_height)
    manifest = {
        "schemaVersion": 1,
        "id": args.name,
        "character": "galateia",
        "assetType": getattr(args, "asset_type", "character"),
        "texture": "spritesheet.webp",
        "frameCount": len(frames),
        "frameDurationMs": duration_ms,
        "effectiveFps": round(1000 / duration_ms, 3),
        "loop": args.loop,
        "frameOrder": "row-major",
        "sourceCanvas": {"width": source_canvas[0], "height": source_canvas[1]},
        "sourceCrop": {
            "left": crop[0],
            "top": crop[1],
            "right": crop[2],
            "bottom": crop[3],
        },
        "grid": {
            "columns": args.atlas_columns,
            "rows": rows,
            "cellWidth": cell_width,
            "cellHeight": cell_height,
        },
        "pivot": {"x": int(pivot[0]), "y": int(pivot[1])},
        "unusedCells": unused_cells,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.preview:
        frames[0].save(
            preview_path,
            format="WEBP",
            save_all=True,
            append_images=frames[1:],
            duration=duration_ms,
            loop=0 if args.loop else 1,
            lossless=False,
            quality=min(args.quality, 88),
            method=4,
        )

    touching = edge_touching_frames(frames)
    return {
        "ok": not touching,
        "animation": args.name,
        "sourceType": source_type,
        "source": str(args.source),
        "output": str(output),
        "frameCount": len(frames),
        "fps": manifest["effectiveFps"],
        "cell": [cell_width, cell_height],
        "atlas": [atlas.width, atlas.height],
        "cropFromSource": list(crop),
        "backgroundKey": None if key_color is None else "#%02x%02x%02x" % key_color,
        "edgeTouchingFrames": touching,
        "files": [path.name for path in targets],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Converte frames, vídeo ou folha única no formato leve de animação da Galateia."
    )
    parser.add_argument("source", type=Path, help="Pasta de frames, vídeo ou spritesheet.")
    parser.add_argument("--name", help="Identificador da animação. Por padrão, usa o nome da entrada.")
    parser.add_argument("--output", type=Path, help="Pasta de saída. Por padrão, usa assets/galateia/animations/<name>.")
    parser.add_argument("--source-type", choices=("auto", "frames", "video", "sheet"), default="auto")
    parser.add_argument("--fps", type=float, default=12.0, help="FPS final e taxa de amostragem de vídeos (padrão: 12).")
    parser.add_argument(
        "--source-fps",
        type=float,
        help="FPS original dos PNGs/folha; permite reduzir quadros sem mudar a duração.",
    )
    parser.add_argument("--loop", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--columns", type=int, help="Colunas da folha de entrada.")
    parser.add_argument("--rows", type=int, help="Linhas da folha de entrada.")
    parser.add_argument("--frame-count", type=int, help="Quantidade de células usadas na folha.")
    parser.add_argument(
        "--skip-start",
        type=int,
        default=0,
        help="Descarta esta quantidade de quadros do início antes de montar o atlas.",
    )
    parser.add_argument(
        "--skip-end",
        type=int,
        default=0,
        help="Descarta esta quantidade de quadros do final antes de montar o atlas.",
    )
    parser.add_argument("--atlas-columns", type=int, help="Colunas do atlas final; padrão: grade aproximadamente quadrada.")
    parser.add_argument(
        "--background",
        default="auto",
        help="auto, transparent ou uma cor #RRGGBB (padrão: auto).",
    )
    parser.add_argument("--tolerance", type=float, default=70.0, help="Tolerância da remoção de fundo (padrão: 70).")
    parser.add_argument("--feather", type=float, default=24.0, help="Suavização da borda removida (padrão: 24).")
    parser.add_argument("--padding", type=int, default=8, help="Espaço transparente ao redor do movimento (padrão: 8).")
    parser.add_argument("--max-cell", type=int, default=512, help="Maior lado da célula final; 0 mantém resolução (padrão: 512).")
    parser.add_argument("--preserve-canvas", action="store_true", help="Não recorta o espaço vazio comum dos frames.")
    parser.add_argument(
        "--fixed-crop",
        type=parse_crop,
        help="Recorte fixo compartilhado: left,top,right,bottom. Mantém escala e posição entre animações.",
    )
    parser.add_argument("--quality", type=int, default=90, help="Qualidade WebP de 1 a 100 (padrão: 90).")
    parser.add_argument("--lossless", action="store_true", help="Gera WebP sem perdas, com arquivo maior.")
    parser.add_argument("--preview", action="store_true", help="Também gera preview.webp animado para conferência.")
    parser.add_argument("--force", action="store_true", help="Substitui os arquivos gerados anteriormente.")
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    args.source = args.source.expanduser().resolve()
    if not args.source.exists():
        raise FileNotFoundError(f"Entrada não encontrada: {args.source}")
    if not math.isfinite(args.fps) or args.fps <= 0 or args.fps > 120:
        raise ValueError("--fps deve estar entre 0 e 120.")
    if args.source_fps is not None and (
        not math.isfinite(args.source_fps) or args.source_fps <= 0 or args.source_fps > 240
    ):
        raise ValueError("--source-fps deve estar entre 0 e 240.")
    if args.padding < 0 or args.max_cell < 0 or args.skip_start < 0 or args.skip_end < 0:
        raise ValueError("--padding, --max-cell, --skip-start e --skip-end não podem ser negativos.")
    if not 1 <= args.quality <= 100:
        raise ValueError("--quality deve estar entre 1 e 100.")

    args.name = safe_id(args.name or args.source.stem)
    frames, source_type = load_source(args)
    if source_type == "sheet" and args.source_fps is not None:
        frames = resample_frames(frames, args.source_fps, args.fps)
    if args.skip_start + args.skip_end >= len(frames):
        raise ValueError("O recorte descartaria todos os quadros da animação.")
    end = len(frames) - args.skip_end if args.skip_end else len(frames)
    frames = frames[args.skip_start:end]
    source_canvas = validate_equal_canvas(frames)

    key_color: tuple[int, int, int] | None = None
    background = args.background.casefold()
    if background == "transparent":
        pass
    elif background == "auto" and any(has_useful_transparency(frame) for frame in frames):
        pass
    else:
        key_color = infer_key_color(frames) if background == "auto" else parse_hex_color(args.background)
        for index, frame in enumerate(frames):
            frames[index] = remove_chroma_background(frame, key_color, args.tolerance, args.feather)

    frames, crop = normalize_frames(
        frames,
        args.preserve_canvas,
        args.padding,
        args.max_cell,
        args.fixed_crop,
        allow_empty_frames=getattr(args, "asset_type", "character") == "scene",
    )
    args.atlas_columns = args.atlas_columns or math.ceil(math.sqrt(len(frames)))
    atlas, rows, unused_cells = compose_atlas(frames, args.atlas_columns)
    return save_outputs(
        args,
        frames,
        atlas,
        rows,
        unused_cells,
        source_type,
        key_color,
        crop,
        source_canvas,
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = run(args)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["edgeTouchingFrames"]:
        print("Aviso: há frames encostando na borda; aumente --padding ou --max-cell.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
