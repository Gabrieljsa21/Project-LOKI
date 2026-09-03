"""Importa muitas animações da Galateia com geometria compartilhada e bloqueada.

O primeiro processamento calcula um único recorte a partir de todas as animações da
configuração. Esse recorte fica salvo em ``geometry.json`` e passa a ser reutilizado
nas próximas importações, mantendo escala, posição e pivô estáveis entre estados.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import importar_animacao as single


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "data" / "animacoes_galateia.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "assets" / "galateia" / "animations"
DEFAULT_GEOMETRY = DEFAULT_OUTPUT / "geometry.json"
DEFAULT_CACHE = PROJECT_ROOT / "cache" / "galateia_animation_frames"
TEMP_ROOT = PROJECT_ROOT.parent / ".tmp"
CACHE_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class PreparedAnimation:
    id: str
    sources: tuple[Path, ...]
    staged_frames: Path
    frame_count: int
    loop: bool
    canvas: tuple[int, int]
    bbox: tuple[int, int, int, int]
    asset_type: str


def read_config(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1:
        raise ValueError("A configuração precisa usar schemaVersion 1.")
    animations = data.get("animations")
    if not isinstance(animations, list) or not animations:
        raise ValueError("A configuração não contém animações.")
    ids = [single.safe_id(str(item.get("id", ""))) for item in animations]
    if len(ids) != len(set(ids)):
        raise ValueError("Há identificadores de animação repetidos na configuração.")
    return data


def restore_canvas(frames: list[Image.Image], settings: dict[str, object] | None) -> list[Image.Image]:
    if not settings:
        return frames
    width = int(settings["width"])
    height = int(settings["height"])
    left = int(settings.get("left", 0))
    top = int(settings.get("top", 0))
    restored: list[Image.Image] = []
    for index, frame in enumerate(frames):
        if left < 0 or top < 0 or left + frame.width > width or top + frame.height > height:
            raise ValueError(f"O frame {index} não cabe no restoreCanvas {width}x{height}.")
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.alpha_composite(frame, (left, top))
        restored.append(canvas)
    return restored


def trim_frames(frames: list[Image.Image], item: dict[str, object]) -> list[Image.Image]:
    start = int(item.get("skipStart", 0))
    end_count = int(item.get("skipEnd", 0))
    if start < 0 or end_count < 0 or start + end_count >= len(frames):
        raise ValueError(f"Recorte de pontas inválido para {item['id']}.")
    end = len(frames) - end_count if end_count else len(frames)
    return frames[start:end]


def source_specs(item: dict[str, object]) -> list[dict[str, object]]:
    """Normaliza uma fonte simples ou vários segmentos ordenados."""
    raw_sources = item.get("sources")
    if raw_sources is None:
        if not item.get("source"):
            raise ValueError(f"{item['id']}: informe source ou sources.")
        return [{"path": item["source"]}]
    if item.get("source"):
        raise ValueError(f"{item['id']}: use source ou sources, nunca os dois.")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError(f"{item['id']}: sources precisa conter pelo menos um segmento.")

    normalized: list[dict[str, object]] = []
    for index, raw in enumerate(raw_sources, start=1):
        if isinstance(raw, str):
            normalized.append({"path": raw})
        elif isinstance(raw, dict) and raw.get("path"):
            normalized.append(dict(raw))
        else:
            raise ValueError(f"{item['id']}: segmento {index} de sources é inválido.")
    return normalized


def trim_segment(frames: list[Image.Image], segment: dict[str, object], animation_id: object) -> list[Image.Image]:
    start = int(segment.get("skipStart", 0))
    end_count = int(segment.get("skipEnd", 0))
    if start < 0 or end_count < 0 or start + end_count >= len(frames):
        raise ValueError(f"Recorte de segmento inválido para {animation_id}.")
    end = len(frames) - end_count if end_count else len(frames)
    return frames[start:end]


def load_segment(
    item: dict[str, object], segment: dict[str, object], fps: float
) -> tuple[Path, list[Image.Image]]:
    source = Path(str(segment["path"])).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Entrada não encontrada: {source}")
    source_type = single.detect_source_type(
        source, str(segment.get("sourceType", item.get("sourceType", "auto")))
    )
    if source_type == "video":
        frames = single.load_video(source, fps)
    elif source_type == "frames":
        source_fps = float(segment.get("sourceFps", item.get("sourceFps", fps)))
        frames = single.load_frame_folder(source, source_fps, fps)
    else:
        raise ValueError(
            f"{item['id']}: o lote aceita vídeo ou pasta de PNGs; folhas devem ser separadas primeiro."
        )
    return source, trim_segment(frames, segment, item["id"])


def load_and_clean(
    item: dict[str, object], fps: float
) -> tuple[tuple[Path, ...], list[Image.Image], tuple[int, int, int] | None]:
    loaded = [load_segment(item, segment, fps) for segment in source_specs(item)]
    sources = tuple(source for source, _ in loaded)
    frames = [frame for _, segment_frames in loaded for frame in segment_frames]
    frames = trim_frames(frames, item)
    frames = restore_canvas(frames, item.get("restoreCanvas"))
    single.validate_equal_canvas(frames)

    background = str(item.get("background", "auto"))
    key_color: tuple[int, int, int] | None = None
    if background.casefold() == "transparent":
        pass
    elif background.casefold() == "auto" and any(single.has_useful_transparency(frame) for frame in frames):
        pass
    else:
        key_color = single.infer_key_color(frames) if background.casefold() == "auto" else single.parse_hex_color(background)
        tolerance = float(item.get("tolerance", 70.0))
        feather = float(item.get("feather", 24.0))
        frames = [single.remove_chroma_background(frame, key_color, tolerance, feather) for frame in frames]
    return sources, frames, key_color


def union_bbox(
    frames: list[Image.Image], *, allow_empty_frames: bool = False,
) -> tuple[int, int, int, int]:
    boxes = [single.alpha_bbox(frame) for frame in frames]
    if not allow_empty_frames and any(box is None for box in boxes):
        raise ValueError("A sequência contém um frame totalmente transparente.")
    present = [box for box in boxes if box is not None]
    if not present:
        raise ValueError("A sequência inteira ficou transparente.")
    return (
        min(box[0] for box in present),
        min(box[1] for box in present),
        max(box[2] for box in present),
        max(box[3] for box in present),
    )


def source_paths(item: dict[str, object]) -> tuple[Path, ...]:
    paths = tuple(Path(str(segment["path"])).expanduser().resolve() for segment in source_specs(item))
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Entrada não encontrada: {', '.join(missing)}")
    return paths


def source_signature(path: Path) -> dict[str, object]:
    """Assinatura barata e independente da pasta da fonte.

    Organizar os vídeos em outra pasta não altera os quadros extraídos. Nome,
    tamanho e mtime continuam detectando substituições sem invalidar o cache só
    porque o caminho absoluto mudou.
    """
    if path.is_file():
        stat = path.stat()
        return {
            "kind": "file", "name": path.name,
            "size": stat.st_size, "mtimeNs": stat.st_mtime_ns,
        }
    files = sorted(
        (item for item in path.iterdir() if item.is_file() and item.suffix.casefold() in single.IMAGE_EXTENSIONS),
        key=single.natural_key,
    )
    return {
        "kind": "frames", "name": path.name,
        "files": [
            {"name": item.name, "size": item.stat().st_size, "mtimeNs": item.stat().st_mtime_ns}
            for item in files
        ],
    }


def preprocessing_signature(item: dict[str, object]) -> dict[str, object]:
    """Opções que afetam os quadros, sem os caminhos físicos das fontes."""
    # ``state`` descreve o grafo do runtime. Alterá-lo não muda nenhum pixel e
    # portanto não deve invalidar o cache caro de extração/chroma.
    preprocessing = {
        key: value for key, value in item.items()
        if key not in {"loop", "source", "sources", "state"}
    }
    if item.get("sources") is not None:
        preprocessing["sources"] = [
            {key: value for key, value in segment.items() if key != "path"}
            if isinstance(segment, dict) else {}
            for segment in item["sources"]
        ]
    return preprocessing


def cache_fingerprint(item: dict[str, object], fps: float, sources: tuple[Path, ...]) -> str:
    payload = {
        "schemaVersion": CACHE_SCHEMA_VERSION,
        "fps": fps,
        "preprocessing": preprocessing_signature(item),
        "sources": [source_signature(path) for path in sources],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def legacy_cache_fingerprint(item: dict[str, object], fps: float, sources: tuple[Path, ...]) -> str:
    """Fingerprint usado antes de o cache sobreviver à mudança de pasta."""
    preprocessing = {key: value for key, value in item.items() if key != "loop"}
    signatures: list[dict[str, object]] = []
    for path in sources:
        if path.is_file():
            stat = path.stat()
            signatures.append({"path": str(path), "size": stat.st_size, "mtimeNs": stat.st_mtime_ns})
            continue
        files = sorted(
            (entry for entry in path.iterdir() if entry.is_file() and entry.suffix.casefold() in single.IMAGE_EXTENSIONS),
            key=single.natural_key,
        )
        signatures.append({
            "path": str(path),
            "files": [
                {"name": entry.name, "size": entry.stat().st_size, "mtimeNs": entry.stat().st_mtime_ns}
                for entry in files
            ],
        })
    payload = {
        "schemaVersion": CACHE_SCHEMA_VERSION,
        "fps": fps,
        "preprocessing": preprocessing,
        "sources": signatures,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def relocated_cache_is_safe(metadata: dict[str, object], sources: tuple[Path, ...], metadata_path: Path) -> bool:
    """Aceita uma migração única quando só o diretório pai mudou.

    O nome precisa ser o mesmo, o caminho anterior não pode mais existir e a
    fonte encontrada não pode ser mais nova que o cache. Uma fonte realmente
    substituída continua invalidando o cache normalmente.
    """
    previous = metadata.get("sources")
    if not isinstance(previous, list) or len(previous) != len(sources):
        return False
    cache_mtime = metadata_path.stat().st_mtime_ns
    for old_value, current in zip(previous, sources):
        old = Path(str(old_value))
        if old.exists() or old.name.casefold() != current.name.casefold():
            return False
        if current.stat().st_mtime_ns > cache_mtime:
            return False
    return True


def cached_prepared(
    item: dict[str, object], fps: float, cache_root: Path
) -> PreparedAnimation | None:
    animation_id = single.safe_id(str(item["id"]))
    sources = source_paths(item)
    cache_dir = cache_root / animation_id
    metadata_path = cache_dir / "cache.json"
    frames_dir = cache_dir / "frames"
    if not metadata_path.is_file() or not frames_dir.is_dir():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        expected_fingerprint = cache_fingerprint(item, fps, sources)
        frame_count = int(metadata["frameCount"])
        cached_frames = list(frames_dir.glob("frame_*.png"))
        fingerprint_matches = metadata.get("fingerprint") == expected_fingerprint
        if not fingerprint_matches:
            fingerprint_matches = (
                metadata.get("fingerprint") == legacy_cache_fingerprint(item, fps, sources)
                or relocated_cache_is_safe(metadata, sources, metadata_path)
            )
        if (
            metadata.get("schemaVersion") != CACHE_SCHEMA_VERSION
            or not fingerprint_matches
            or len(cached_frames) != frame_count
        ):
            return None
        if metadata.get("fingerprint") != expected_fingerprint or metadata.get("sources") != [str(path) for path in sources]:
            metadata["fingerprint"] = expected_fingerprint
            metadata["sources"] = [str(path) for path in sources]
            temporary_metadata = metadata_path.with_suffix(".json.tmp")
            temporary_metadata.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            os.replace(temporary_metadata, metadata_path)
        return PreparedAnimation(
            id=animation_id,
            sources=sources,
            staged_frames=frames_dir,
            frame_count=frame_count,
            loop=bool(item.get("loop", True)),
            canvas=tuple(int(value) for value in metadata["canvas"]),
            bbox=tuple(int(value) for value in metadata["bbox"]),
            asset_type=str(item.get("assetType", "character")),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def persist_cache(
    item: dict[str, object], fps: float, sources: tuple[Path, ...], frames: list[Image.Image],
    canvas: tuple[int, int], bbox: tuple[int, int, int, int], cache_root: Path,
) -> Path:
    animation_id = single.safe_id(str(item["id"]))
    cache_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{animation_id}-", dir=cache_root))
    frames_dir = temporary / "frames"
    frames_dir.mkdir()
    for index, frame in enumerate(frames):
        frame.save(frames_dir / f"frame_{index:05d}.png", format="PNG", optimize=False, compress_level=1)
    metadata = {
        "schemaVersion": CACHE_SCHEMA_VERSION,
        "animation": animation_id,
        "fingerprint": cache_fingerprint(item, fps, sources),
        "frameCount": len(frames),
        "canvas": list(canvas),
        "bbox": list(bbox),
        "sources": [str(path) for path in sources],
    }
    (temporary / "cache.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Não move a pasta temporária: no Windows ela pode carregar uma ACL
    # restritiva. As pastas finais nascem sob `cache/` e herdam as permissões
    # normais do projeto; `cache.json` é promovido por último e funciona como
    # marcador atômico de que todos os quadros chegaram completos.
    destination = cache_root / animation_id
    destination_frames = destination / "frames"
    destination_frames.mkdir(parents=True, exist_ok=True)
    generated_names = {path.name for path in frames_dir.glob("frame_*.png")}
    for generated in frames_dir.glob("frame_*.png"):
        replace_from_copy(generated, destination_frames / generated.name)
    for stale in destination_frames.glob("frame_*.png"):
        if stale.name not in generated_names:
            stale.unlink()
    replace_from_copy(temporary / "cache.json", destination / "cache.json")
    shutil.rmtree(temporary)
    return destination / "frames"


def prepare(
    item: dict[str, object], fps: float, staging_root: Path, cache_root: Path,
    *, use_cache: bool = True, rebuild_cache: bool = False,
) -> tuple[PreparedAnimation, bool]:
    animation_id = single.safe_id(str(item["id"]))
    if use_cache and not rebuild_cache:
        cached = cached_prepared(item, fps, cache_root)
        if cached is not None:
            return cached, True

    sources, frames, _ = load_and_clean(item, fps)
    canvas = single.validate_equal_canvas(frames)
    asset_type = str(item.get("assetType", "character"))
    bbox = union_bbox(frames, allow_empty_frames=asset_type == "scene")
    if use_cache:
        staged = persist_cache(item, fps, sources, frames, canvas, bbox, cache_root)
    else:
        staged = staging_root / animation_id
        staged.mkdir(parents=True)
        for index, frame in enumerate(frames):
            frame.save(staged / f"frame_{index:05d}.png", format="PNG", optimize=False, compress_level=1)
    return PreparedAnimation(
        id=animation_id,
        sources=sources,
        staged_frames=staged,
        frame_count=len(frames),
        loop=bool(item.get("loop", True)),
        canvas=canvas,
        bbox=bbox,
        asset_type=asset_type,
    ), False


def calculate_geometry(
    prepared: list[PreparedAnimation], padding: int, max_cell: int
) -> dict[str, object]:
    canvases = {animation.canvas for animation in prepared}
    if len(canvases) != 1:
        readable = ", ".join(f"{w}x{h}" for w, h in sorted(canvases))
        raise ValueError(f"Todas as entradas precisam compartilhar o mesmo canvas: {readable}")
    width, height = next(iter(canvases))
    left = max(0, min(item.bbox[0] for item in prepared) - padding)
    top = max(0, min(item.bbox[1] for item in prepared) - padding)
    right = min(width, max(item.bbox[2] for item in prepared) + padding)
    bottom = min(height, max(item.bbox[3] for item in prepared) + padding)
    crop_width = right - left
    crop_height = bottom - top
    scale = min(1.0, max_cell / max(crop_width, crop_height)) if max_cell else 1.0
    cell_width = max(1, round(crop_width * scale))
    cell_height = max(1, round(crop_height * scale))
    return {
        "schemaVersion": 1,
        "sourceCanvas": {"width": width, "height": height},
        "sourceCrop": {"left": left, "top": top, "right": right, "bottom": bottom},
        "cell": {"width": cell_width, "height": cell_height},
        "pivot": {"x": cell_width // 2, "y": cell_height},
        "maxCell": max_cell,
        "padding": padding,
    }


def load_geometry(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1:
        raise ValueError("geometry.json usa uma versão desconhecida.")
    return data


def crop_tuple(geometry: dict[str, object]) -> tuple[int, int, int, int]:
    crop = geometry["sourceCrop"]
    return int(crop["left"]), int(crop["top"]), int(crop["right"]), int(crop["bottom"])


def ensure_fits(prepared: PreparedAnimation, geometry: dict[str, object]) -> None:
    canvas = geometry["sourceCanvas"]
    expected = int(canvas["width"]), int(canvas["height"])
    if prepared.canvas != expected:
        raise ValueError(
            f"{prepared.id}: canvas {prepared.canvas[0]}x{prepared.canvas[1]}, esperado {expected[0]}x{expected[1]}."
        )
    left, top, right, bottom = crop_tuple(geometry)
    box = prepared.bbox
    if box[0] < left or box[1] < top or box[2] > right or box[3] > bottom:
        raise ValueError(
            f"{prepared.id} ultrapassa a geometria bloqueada. Execute novamente com "
            "--recalculate-geometry para ampliar o recorte e reconstruir todas as animações."
        )


def scene_crop(prepared: PreparedAnimation) -> tuple[int, int, int, int]:
    return 0, 0, prepared.canvas[0], prepared.canvas[1]


def scene_max_cell(geometry: dict[str, object], prepared: PreparedAnimation) -> int:
    normal_crop = crop_tuple(geometry)
    normal_width = normal_crop[2] - normal_crop[0]
    scale = int(geometry["cell"]["width"]) / normal_width
    return max(1, round(max(prepared.canvas) * scale))


def scene_pivot(geometry: dict[str, object], prepared: PreparedAnimation) -> tuple[int, int]:
    normal_crop = crop_tuple(geometry)
    normal_width = normal_crop[2] - normal_crop[0]
    scale = int(geometry["cell"]["width"]) / normal_width
    pivot = geometry["pivot"]
    source_anchor_x = normal_crop[0] + int(pivot["x"]) / scale
    source_anchor_y = normal_crop[1] + int(pivot["y"]) / scale
    return round(source_anchor_x * scale), round(source_anchor_y * scale)


def importer_args(
    prepared: PreparedAnimation,
    destination: Path,
    geometry: dict[str, object],
    fps: float,
    quality: int,
) -> SimpleNamespace:
    is_scene = prepared.asset_type == "scene"
    return SimpleNamespace(
        source=prepared.staged_frames,
        name=prepared.id,
        output=destination,
        source_type="frames",
        fps=fps,
        source_fps=fps,
        loop=prepared.loop,
        columns=None,
        rows=None,
        frame_count=None,
        skip_start=0,
        skip_end=0,
        atlas_columns=math.ceil(math.sqrt(prepared.frame_count)),
        background="transparent",
        tolerance=70.0,
        feather=24.0,
        padding=0,
        max_cell=scene_max_cell(geometry, prepared) if is_scene else int(geometry["maxCell"]),
        preserve_canvas=False,
        fixed_crop=scene_crop(prepared) if is_scene else crop_tuple(geometry),
        quality=quality,
        lossless=False,
        preview=True,
        force=True,
        asset_type=prepared.asset_type,
        pivot_override=scene_pivot(geometry, prepared) if is_scene else None,
    )


def replace_from_copy(source: Path, destination: Path) -> None:
    """Substitui atomicamente sem carregar a ACL da pasta temporária."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def promote(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("spritesheet.webp", "animation.json", "preview.webp"):
        generated = source / name
        if generated.exists():
            replace_from_copy(generated, destination / name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Importa em massa animações da Galateia mantendo escala, posição e pivô idênticos."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--geometry", type=Path, default=DEFAULT_GEOMETRY)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--only", action="append", help="Importa somente este id; pode ser repetido.")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Também gera preview.webp. O visualizador não precisa dele.",
    )
    parser.add_argument(
        "--recalculate-geometry",
        action="store_true",
        help="Recalcula o recorte e reconstrói todas as animações configuradas.",
    )
    cache_group = parser.add_mutually_exclusive_group()
    cache_group.add_argument(
        "--rebuild-cache", action="store_true",
        help="Refaz os quadros intermediários mesmo quando o cache ainda é válido.",
    )
    cache_group.add_argument(
        "--no-cache", action="store_true",
        help="Não lê nem grava o cache persistente de quadros tratados.",
    )
    parser.add_argument(
        "--prepare-only", action="store_true",
        help="Prepara/atualiza o cache, mas não monta spritesheets.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = args.config.expanduser().resolve()
    config = read_config(config_path)
    fps = float(config.get("fps", 12))
    max_cell = int(config.get("maxCell", 384))
    padding = int(config.get("geometryPadding", 24))
    quality = int(config.get("atlasQuality", 90))
    all_items = list(config["animations"])
    selected_ids = {single.safe_id(value) for value in args.only or []}
    known_ids = {single.safe_id(str(item["id"])) for item in all_items}
    unknown = selected_ids - known_ids
    if unknown:
        raise ValueError(f"Animações não encontradas na configuração: {', '.join(sorted(unknown))}")

    geometry_path = args.geometry.expanduser().resolve()
    cache_root = args.cache_dir.expanduser().resolve()
    must_calculate = args.recalculate_geometry or not geometry_path.exists()
    if must_calculate and selected_ids:
        print("A geometria será calculada com todas as animações; --only será aplicado depois.")
    items_to_prepare = all_items if must_calculate else [
        item for item in all_items if not selected_ids or single.safe_id(str(item["id"])) in selected_ids
    ]
    if not items_to_prepare:
        raise ValueError("Nenhuma animação foi selecionada.")

    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gaia-animation-batch-", dir=TEMP_ROOT) as temporary:
        temp = Path(temporary)
        staging = temp / "staging"
        staging.mkdir()
        prepared: list[PreparedAnimation] = []
        cache_hits = 0
        for index, item in enumerate(items_to_prepare, start=1):
            print(f"[{index}/{len(items_to_prepare)}] Preparando {item['id']}...", flush=True)
            animation, cache_hit = prepare(
                item, fps, staging, cache_root,
                use_cache=not args.no_cache, rebuild_cache=args.rebuild_cache,
            )
            prepared.append(animation)
            if cache_hit:
                cache_hits += 1
                print(f"  cache reutilizado: {animation.id}", flush=True)

        if must_calculate:
            normal_prepared = [item for item in prepared if item.asset_type == "character"]
            if not normal_prepared:
                raise ValueError("A geometria compartilhada exige ao menos uma animação character.")
            geometry = calculate_geometry(normal_prepared, padding, max_cell)
        else:
            geometry = load_geometry(geometry_path)
        for animation in prepared:
            if animation.asset_type == "scene":
                expected_canvas = (
                    int(geometry["sourceCanvas"]["width"]), int(geometry["sourceCanvas"]["height"])
                )
                if animation.canvas != expected_canvas:
                    raise ValueError(
                        f"{animation.id}: cena usa canvas {animation.canvas}, esperado {expected_canvas}."
                    )
            else:
                ensure_fits(animation, geometry)

        if args.prepare_only:
            print(json.dumps({
                "ok": True, "prepared": len(prepared), "cacheHits": cache_hits,
                "cacheMisses": len(prepared) - cache_hits, "cache": str(cache_root),
            }, ensure_ascii=False, indent=2))
            return 0

        selected = prepared if not selected_ids else [item for item in prepared if item.id in selected_ids]
        generated_root = temp / "generated"
        results: list[dict[str, object]] = []
        for index, animation in enumerate(selected, start=1):
            print(f"[{index}/{len(selected)}] Montando {animation.id}...", flush=True)
            generated = generated_root / animation.id
            import_args = importer_args(animation, generated, geometry, fps, quality)
            import_args.preview = args.preview
            result = single.run(import_args)
            if result["edgeTouchingFrames"] and animation.asset_type != "scene":
                raise ValueError(f"{animation.id} encostou na borda após a montagem.")
            results.append(result)

        output_root = args.output.expanduser().resolve()
        for animation in selected:
            promote(generated_root / animation.id, output_root / animation.id)
        if must_calculate:
            geometry_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_geometry = temp / "geometry.json"
            temporary_geometry.write_text(
                json.dumps(geometry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            replace_from_copy(temporary_geometry, geometry_path)

    print(json.dumps({
        "ok": True, "geometry": geometry, "animations": results,
        "cacheHits": cache_hits, "cacheMisses": len(prepared) - cache_hits,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
