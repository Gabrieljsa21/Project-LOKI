"""Orquestra a entrada de novas animações da Galateia.

O script concentra o trabalho repetitivo do pipeline:

* descobre vídeos e pastas de frames ainda não registrados;
* cria entradas em ``animacoes_galateia.json`` de forma atômica;
* infere metadados básicos de estado a partir da convenção dos ids;
* chama o importador e o validador existentes;
* audita fontes, assets, manifests, catálogo e outliers geométricos;
* grava relatórios JSON e Markdown reutilizáveis por pessoas e agentes.

Ele usa apenas a biblioteca padrão. O processamento visual continua delegado aos
importadores existentes, que rodam no ambiente Python do projeto.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "data" / "animacoes_galateia.json"
DEFAULT_SOURCE_ROOT = Path(r"E:\Downloads\Sprites")
DEFAULT_ASSET_ROOT = PROJECT_ROOT / "assets" / "galateia" / "animations"
DEFAULT_CACHE_ROOT = PROJECT_ROOT / "cache" / "galateia_animation_frames"
DEFAULT_REPORT_JSON = PROJECT_ROOT / "cache" / "animation_pipeline_report.json"
DEFAULT_REPORT_MD = PROJECT_ROOT / "cache" / "animation_pipeline_report.md"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXTENSIONS = {".png", ".webp", ".jpg", ".jpeg"}
FRAME_NAME = re.compile(r"^(?:frame[_ -]?)?\d+$", re.IGNORECASE)
TIMESTAMP_SUFFIX = re.compile(r"(?:[_ -](?:19|20)\d{10,13})$")


@dataclass(frozen=True)
class Candidate:
    path: Path
    source_type: str
    suggested_id: str
    loop: bool


@dataclass
class AuditReport:
    generated_at: str
    config: str
    source_root: str
    reference: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    information: list[str] = field(default_factory=list)
    animations: list[dict[str, object]] = field(default_factory=list)
    unregistered: list[dict[str, object]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "generatedAt": self.generated_at,
            "config": self.config,
            "sourceRoot": self.source_root,
            "reference": self.reference,
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "animations": len(self.animations),
                "unregistered": len(self.unregistered),
            },
            "errors": self.errors,
            "warnings": self.warnings,
            "information": self.information,
            "animations": self.animations,
            "unregistered": self.unregistered,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalized_path(path: Path | str) -> str:
    """Chave de caminho estável no Windows e utilizável em outros sistemas."""
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(path))))


def safe_id(value: str) -> str:
    """Converte um nome de arquivo em id previsível sem apagar sua estrutura."""
    value = Path(value).stem.strip()
    value = TIMESTAMP_SUFFIX.sub("", value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = value.casefold().replace("&", " e ")
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = re.sub(r"[-_]{2,}", lambda match: match.group(0)[0], value)
    value = value.strip("_-")
    if not value:
        raise ValueError("Não foi possível criar um id a partir do nome informado.")
    return value


def infer_loop(animation_id: str) -> bool:
    tokens = set(re.split(r"[_-]+", animation_id.casefold()))
    return "loop" in tokens or "idle" in tokens


def state_fallback(destination: str | None) -> str | None:
    return {
        "flutuando": "flutuando_idle",
        "sentada": "sentada_balancando-pernas",
    }.get(destination or "")


def infer_state(animation_id: str, loop: bool) -> dict[str, object]:
    """Infere uma especificação conservadora a partir da convenção de ids.

    ``origem_para_destino`` é tratado como transição. Loops e ações usam a
    primeira categoria antes de ``_`` como estado lógico. A inferência fica no
    JSON e pode ser corrigida sem editar Python.
    """
    animation_id = safe_id(animation_id)
    if "_para_" in animation_id:
        origin, destination = animation_id.split("_para_", 1)
        return {
            "origin": origin,
            "destination": destination,
            "fallback": state_fallback(destination),
            "interruptible": False,
            "tags": ["transition"],
            "inferred": True,
        }

    # Aceita também arquivos legados como ``leque-ironica_loop`` sem criar o
    # estado acidental ``leque-ironica``. Pela convenção oficial, a primeira
    # palavra é a família/estado e o restante descreve a ação.
    logical_state = re.split(r"[_-]", animation_id, maxsplit=1)[0]
    if animation_id == "flutuando_idle":
        origin: str | None = None
        destination = "flutuando"
    else:
        origin = logical_state
        destination = logical_state
    tags = ["idle"] if loop else ["action"]
    return {
        "origin": origin,
        "destination": destination,
        "fallback": None if loop else state_fallback(destination),
        "interruptible": bool(loop),
        "tags": tags,
        "inferred": True,
    }


def frame_folder(path: Path) -> bool:
    try:
        images = [entry for entry in path.iterdir() if entry.is_file() and entry.suffix.casefold() in IMAGE_EXTENSIONS]
    except (OSError, PermissionError):
        return False
    if len(images) < 2:
        return False
    matching = sum(bool(FRAME_NAME.fullmatch(entry.stem)) for entry in images)
    return matching >= 2 and matching / len(images) >= 0.6


def item_sources(item: dict[str, object]) -> tuple[Path, ...]:
    if item.get("source"):
        return (Path(str(item["source"])).expanduser(),)
    sources: list[Path] = []
    for segment in item.get("sources", []) if isinstance(item.get("sources"), list) else []:
        if isinstance(segment, str):
            sources.append(Path(segment).expanduser())
        elif isinstance(segment, dict) and segment.get("path"):
            sources.append(Path(str(segment["path"])).expanduser())
    return tuple(sources)


def read_config(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1 or not isinstance(data.get("animations"), list):
        raise ValueError(f"Configuração inválida: {path}")
    return data


def write_json_atomic(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def configured_source_keys(config: dict[str, object]) -> set[str]:
    return {
        normalized_path(source)
        for item in config["animations"]
        for source in item_sources(item)
    }


def relocation_candidates(missing: Path, source_root: Path) -> list[Path]:
    """Procura uma fonte movida sem adivinhar entre resultados ambíguos."""
    if not source_root.exists() or not missing.name:
        return []
    expected_file = bool(missing.suffix)
    matches: list[Path] = []
    try:
        for candidate in source_root.rglob(missing.name):
            if expected_file and not candidate.is_file():
                continue
            if not expected_file and not candidate.is_dir():
                continue
            matches.append(candidate.resolve())
    except (OSError, PermissionError):
        return []
    return sorted({path for path in matches}, key=lambda path: str(path).casefold())


def repair_source_paths(
    config: dict[str, object], source_root: Path,
) -> tuple[list[dict[str, str]], list[str]]:
    """Atualiza em memória caminhos ausentes quando há exatamente um substituto."""
    changes: list[dict[str, str]] = []
    ambiguous: list[str] = []
    for item in config["animations"]:
        containers: list[tuple[dict[str, object], str]] = []
        if item.get("source"):
            containers.append((item, "source"))
        raw_sources = item.get("sources")
        if isinstance(raw_sources, list):
            for index, segment in enumerate(raw_sources):
                if isinstance(segment, dict) and segment.get("path"):
                    containers.append((segment, "path"))
                elif isinstance(segment, str):
                    # Converte a forma curta somente quando o reparo for seguro.
                    wrapper = {"path": segment}
                    raw_sources[index] = wrapper
                    containers.append((wrapper, "path"))
        for container, key in containers:
            current = Path(str(container[key])).expanduser()
            if current.exists():
                continue
            matches = relocation_candidates(current, source_root)
            if len(matches) == 1:
                replacement = matches[0]
                container[key] = str(replacement)
                changes.append({
                    "id": str(item.get("id", "")),
                    "from": str(current),
                    "to": str(replacement),
                })
            elif len(matches) > 1:
                ambiguous.append(
                    f"{item.get('id')}: {current.name} possui {len(matches)} destinos possíveis."
                )
    return changes, ambiguous


def discover(
    source_root: Path, config: dict[str, object], *, recursive: bool = False,
) -> list[Candidate]:
    source_root = source_root.expanduser()
    if not source_root.exists():
        return []
    registered = configured_source_keys(config)
    candidates: list[Candidate] = []
    if recursive:
        walker: Iterable[tuple[str, list[str], list[str]]] = os.walk(source_root)
    else:
        root_files = [entry.name for entry in source_root.iterdir() if entry.is_file()]
        walker = [(str(source_root), [], root_files)]
        # Uma pasta de frames colocada diretamente na raiz também é uma fonte;
        # outras subpastas são coleções/arquivos históricos e não são invadidas.
        for child in source_root.iterdir():
            if child.is_dir() and frame_folder(child):
                key = normalized_path(child)
                if key not in registered:
                    suggestion = safe_id(child.name)
                    candidates.append(Candidate(child.resolve(), "frames", suggestion, infer_loop(suggestion)))
    for current, directories, files in walker:
        current_path = Path(current)
        if frame_folder(current_path):
            key = normalized_path(current_path)
            if key not in registered:
                suggestion = safe_id(current_path.name)
                candidates.append(Candidate(current_path.resolve(), "frames", suggestion, infer_loop(suggestion)))
            directories[:] = []
            continue
        for filename in files:
            path = current_path / filename
            if path.suffix.casefold() not in VIDEO_EXTENSIONS:
                continue
            key = normalized_path(path)
            if key in registered:
                continue
            suggestion = safe_id(path.name)
            candidates.append(Candidate(path.resolve(), "video", suggestion, infer_loop(suggestion)))
    unique = {normalized_path(candidate.path): candidate for candidate in candidates}
    return sorted(unique.values(), key=lambda candidate: str(candidate.path).casefold())


def unique_id(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    index = 2
    while f"{base}-{index}" in used:
        index += 1
    return f"{base}-{index}"


def tags_from_argument(value: str | None, defaults: Sequence[str]) -> list[str]:
    if not value:
        return list(defaults)
    return [part.strip() for part in value.split(",") if part.strip()]


def build_items(paths: Sequence[Path], args: argparse.Namespace, config: dict[str, object]) -> list[dict[str, object]]:
    if args.id and len(paths) != 1:
        raise ValueError("--id só pode ser usado ao adicionar uma única fonte.")
    used = {str(item.get("id", "")) for item in config["animations"]}
    existing_sources = configured_source_keys(config)
    built: list[dict[str, object]] = []
    for path in paths:
        path = path.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Fonte não encontrada: {path}")
        if normalized_path(path) in existing_sources:
            raise ValueError(f"A fonte já está registrada: {path}")
        if path.is_dir() and not frame_folder(path):
            raise ValueError(f"A pasta não parece conter uma sequência numerada de frames: {path}")
        if path.is_file() and path.suffix.casefold() not in VIDEO_EXTENSIONS:
            raise ValueError(f"Formato de vídeo não reconhecido: {path}")

        proposed = safe_id(args.id or path.name)
        animation_id = unique_id(proposed, used)
        used.add(animation_id)
        loop = infer_loop(animation_id) if args.loop is None else bool(args.loop)
        state = infer_state(animation_id, loop)
        if args.origin is not None:
            state["origin"] = None if args.origin.casefold() in {"none", "null", "-"} else args.origin
        if args.destination is not None:
            state["destination"] = args.destination
        if args.fallback is not None:
            state["fallback"] = None if args.fallback.casefold() in {"none", "null", "-"} else args.fallback
        if args.interruptible is not None:
            state["interruptible"] = bool(args.interruptible)
        state["tags"] = tags_from_argument(args.tags, state.get("tags", []))
        state["inferred"] = not any(
            value is not None
            for value in (args.origin, args.destination, args.fallback, args.tags, args.interruptible)
        )

        item: dict[str, object] = {
            "id": animation_id,
            "source": str(path),
            "loop": loop,
            "state": state,
        }
        if args.scene:
            item["assetType"] = "scene"
        if args.background:
            item["background"] = args.background
        if args.tolerance is not None:
            item["tolerance"] = args.tolerance
        if args.feather is not None:
            item["feather"] = args.feather
        if args.skip_start:
            item["skipStart"] = args.skip_start
        if args.skip_end:
            item["skipEnd"] = args.skip_end
        built.append(item)
    return built


def register(paths: Sequence[Path], args: argparse.Namespace) -> list[dict[str, object]]:
    config_path = args.config.expanduser().resolve()
    config = read_config(config_path)
    items = build_items(paths, args, config)
    if args.dry_run:
        print(json.dumps({"dryRun": True, "animations": items}, ensure_ascii=False, indent=2))
        return items
    config["animations"].extend(items)
    write_json_atomic(config_path, config)
    print(f"Registradas {len(items)} animação(ões) em {config_path}.")
    for item in items:
        print(f"  + {item['id']} <- {item['source']}")
    return items


def run_checked(command: Sequence[str], cwd: Path = PROJECT_ROOT) -> None:
    print("\n> " + " ".join(f'"{part}"' if " " in part else part for part in command), flush=True)
    completed = subprocess.run(list(command), cwd=cwd, check=False)
    if completed.returncode:
        raise RuntimeError(f"O comando terminou com código {completed.returncode}: {command[1]}")


def run_pipeline(ids: Sequence[str], args: argparse.Namespace) -> None:
    importer = Path(__file__).with_name("importar_lote_animacoes.py")
    validator = Path(__file__).with_name("validar_animacoes.py")
    command = [sys.executable, str(importer), "--config", str(args.config)]
    for animation_id in ids:
        command.extend(("--only", animation_id))
    if args.rebuild_cache:
        command.append("--rebuild-cache")
    if args.preview:
        command.append("--preview")
    run_checked(command)
    run_checked([sys.executable, str(validator), "--config", str(args.config)])


def load_cache_metadata(animation_id: str, cache_root: Path) -> dict[str, object] | None:
    path = cache_root / animation_id / "cache.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_manifest(animation_id: str, asset_root: Path) -> dict[str, object] | None:
    path = asset_root / animation_id / "animation.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def bbox_metrics(bbox: Sequence[int], reference: Sequence[int]) -> dict[str, float]:
    left, top, right, bottom = (int(value) for value in bbox)
    ref_left, ref_top, ref_right, ref_bottom = (int(value) for value in reference)
    width, height = right - left, bottom - top
    ref_width, ref_height = ref_right - ref_left, ref_bottom - ref_top
    return {
        "widthRatio": round(width / ref_width, 3) if ref_width else 0.0,
        "heightRatio": round(height / ref_height, 3) if ref_height else 0.0,
        "centerDeltaX": round((left + right - ref_left - ref_right) / 2, 1),
        "centerDeltaY": round((top + bottom - ref_top - ref_bottom) / 2, 1),
        "bottomDelta": float(bottom - ref_bottom),
    }


def load_catalog_ids() -> set[str]:
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        module = importlib.import_module("mascot.state_catalog")
        module = importlib.reload(module)
        return set(module.CATALOGO)
    finally:
        if sys.path and sys.path[0] == str(PROJECT_ROOT):
            sys.path.pop(0)


def audit(args: argparse.Namespace, *, only: set[str] | None = None) -> AuditReport:
    config_path = args.config.expanduser().resolve()
    source_root = args.source_root.expanduser().resolve()
    asset_root = args.asset_root.expanduser().resolve()
    cache_root = args.cache_root.expanduser().resolve()
    config = read_config(config_path)
    report = AuditReport(utc_now(), str(config_path), str(source_root), args.reference)
    all_items = list(config["animations"])
    items = [item for item in all_items if not only or str(item.get("id")) in only]
    ids = [str(item.get("id", "")) for item in all_items]
    duplicates = sorted({animation_id for animation_id in ids if ids.count(animation_id) > 1})
    if duplicates:
        report.errors.append("Ids repetidos: " + ", ".join(duplicates))

    try:
        catalog_ids = load_catalog_ids()
    except Exception as exc:  # relatório precisa sobreviver a um catálogo quebrado
        catalog_ids = set()
        report.errors.append(f"Falha ao carregar o catálogo: {exc}")

    reference_metadata = load_cache_metadata(args.reference, cache_root)
    reference_bbox = reference_metadata.get("bbox") if reference_metadata else None
    if not reference_bbox:
        report.warnings.append(f"Cache da referência {args.reference} ausente; alinhamento não foi comparado.")

    for item in items:
        animation_id = str(item.get("id", ""))
        row: dict[str, object] = {
            "id": animation_id,
            "sourceExists": True,
            "assetExists": False,
            "catalogued": animation_id in catalog_ids,
            "stateInferred": bool(isinstance(item.get("state"), dict) and item["state"].get("inferred")),
        }
        sources = item_sources(item)
        missing = [str(source) for source in sources if not source.exists()]
        if missing:
            row["sourceExists"] = False
            report.errors.append(f"{animation_id}: fonte ausente: {', '.join(missing)}")

        manifest = load_manifest(animation_id, asset_root)
        texture = asset_root / animation_id / "spritesheet.webp"
        if manifest is None or not texture.is_file():
            report.warnings.append(f"{animation_id}: asset final ainda não foi montado.")
        else:
            row["assetExists"] = True
            row["frameCount"] = manifest.get("frameCount")
            if bool(manifest.get("loop")) != bool(item.get("loop", True)):
                report.errors.append(f"{animation_id}: loop do manifesto difere da configuração.")
            expected_type = str(item.get("assetType", "character"))
            if str(manifest.get("assetType", "character")) != expected_type:
                report.errors.append(f"{animation_id}: assetType do manifesto difere da configuração.")

        if animation_id not in catalog_ids:
            if isinstance(item.get("state"), dict):
                report.errors.append(f"{animation_id}: possui state declarativo, mas não entrou no catálogo.")
            else:
                report.warnings.append(f"{animation_id}: ainda não está no catálogo e não possui state declarativo.")

        metadata = load_cache_metadata(animation_id, cache_root)
        if metadata and reference_bbox and str(item.get("assetType", "character")) != "scene":
            metrics = bbox_metrics(metadata.get("bbox", (0, 0, 0, 0)), reference_bbox)
            row["alignment"] = metrics
            if (
                metrics["widthRatio"] < 0.45 or metrics["widthRatio"] > 2.20
                or metrics["heightRatio"] < 0.55 or metrics["heightRatio"] > 1.75
                or abs(metrics["centerDeltaX"]) > 320
                or abs(metrics["centerDeltaY"]) > 240
            ):
                report.warnings.append(
                    f"{animation_id}: geometria muito diferente de {args.reference}; confira escala e posição."
                )
        report.animations.append(row)

    candidates = discover(source_root, config, recursive=bool(args.recursive))
    report.unregistered = [
        {
            "path": str(candidate.path),
            "sourceType": candidate.source_type,
            "suggestedId": candidate.suggested_id,
            "suggestedLoop": candidate.loop,
        }
        for candidate in candidates
    ]
    if candidates:
        report.information.append(f"Há {len(candidates)} fonte(s) não registrada(s) em {source_root}.")

    configured_ids = set(ids)
    if asset_root.exists():
        asset_ids = {
            path.name for path in asset_root.iterdir()
            if path.is_dir() and (path / "animation.json").exists()
        }
        orphan_assets = sorted(asset_ids - configured_ids)
        if orphan_assets:
            report.warnings.append("Assets sem entrada na configuração: " + ", ".join(orphan_assets))
    return report


def report_markdown(report: AuditReport) -> str:
    data = report.as_dict()
    summary = data["summary"]
    lines = [
        "# Relatório do pipeline de animações",
        "",
        f"Gerado em `{report.generated_at}`.",
        "",
        f"- Resultado: **{'OK' if report.ok else 'COM ERROS'}**",
        f"- Animações verificadas: {summary['animations']}",
        f"- Erros: {summary['errors']}",
        f"- Avisos: {summary['warnings']}",
        f"- Fontes não registradas: {summary['unregistered']}",
        "",
    ]
    for title, values in (("Erros", report.errors), ("Avisos", report.warnings), ("Informações", report.information)):
        lines.extend((f"## {title}", ""))
        lines.extend(f"- {value}" for value in values)
        if not values:
            lines.append("- Nenhum.")
        lines.append("")
    lines.extend(("## Animações", "", "| Id | Fonte | Asset | Catálogo | Inferido |", "| --- | --- | --- | --- | --- |"))
    for row in report.animations:
        lines.append(
            f"| `{row['id']}` | {'OK' if row['sourceExists'] else 'AUSENTE'} | "
            f"{'OK' if row['assetExists'] else 'PENDENTE'} | "
            f"{'OK' if row['catalogued'] else 'PENDENTE'} | "
            f"{'sim' if row['stateInferred'] else 'não'} |"
        )
    lines.extend(("", "## Fontes ainda não registradas", ""))
    if report.unregistered:
        lines.extend(f"- `{row['suggestedId']}`: `{row['path']}`" for row in report.unregistered)
    else:
        lines.append("- Nenhuma.")
    lines.append("")
    return "\n".join(lines)


def save_report(report: AuditReport, json_path: Path, markdown_path: Path) -> None:
    write_json_atomic(json_path, report.as_dict())
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(report_markdown(report), encoding="utf-8")
    print(f"Relatório JSON: {json_path}")
    print(f"Relatório legível: {markdown_path}")


def add_common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ASSET_ROOT)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument(
        "--recursive", action="store_true",
        help="Inclui subpastas na busca por fontes não registradas.",
    )


def add_registration_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("paths", nargs="+", type=Path, help="Vídeos ou pastas de frames que serão registrados.")
    parser.add_argument("--id", help="Id explícito; disponível somente para uma fonte.")
    loop = parser.add_mutually_exclusive_group()
    loop.add_argument("--loop", dest="loop", action="store_true")
    loop.add_argument("--no-loop", dest="loop", action="store_false")
    parser.set_defaults(loop=None)
    parser.add_argument("--scene", action="store_true", help="Mantém o canvas amplo da cena.")
    parser.add_argument("--background", help="Cor chroma em hexadecimal ou auto/transparent.")
    parser.add_argument("--tolerance", type=float)
    parser.add_argument("--feather", type=float)
    parser.add_argument("--skip-start", type=int, default=0)
    parser.add_argument("--skip-end", type=int, default=0)
    parser.add_argument("--origin", help="Estado lógico de origem; use none para nulo.")
    parser.add_argument("--destination", help="Estado lógico de destino.")
    parser.add_argument("--fallback", help="Próximo clipe; use none para nulo.")
    parser.add_argument("--tags", help="Tags separadas por vírgula.")
    interruptible = parser.add_mutually_exclusive_group()
    interruptible.add_argument("--interruptible", dest="interruptible", action="store_true")
    interruptible.add_argument("--non-interruptible", dest="interruptible", action="store_false")
    parser.set_defaults(interruptible=None)
    parser.add_argument("--dry-run", action="store_true", help="Mostra o cadastro sem escrever.")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automatiza o pipeline de animações da Galateia.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Lista fontes ainda não registradas.")
    add_common_paths(scan_parser)
    scan_parser.add_argument("--json", action="store_true")

    add_parser = subparsers.add_parser("add", help="Registra fontes sem processá-las.")
    add_common_paths(add_parser)
    add_registration_options(add_parser)

    process_parser = subparsers.add_parser("process", help="Registra, importa, valida e audita.")
    add_common_paths(process_parser)
    add_registration_options(process_parser)
    process_parser.add_argument("--rebuild-cache", action="store_true")
    process_parser.add_argument("--preview", action="store_true")
    process_parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    process_parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD)

    refresh_parser = subparsers.add_parser(
        "refresh", help="Reimporta ids já registrados, valida e audita."
    )
    add_common_paths(refresh_parser)
    refresh_parser.add_argument("ids", nargs="+", help="Ids existentes que serão reprocessados.")
    refresh_parser.add_argument("--rebuild-cache", action="store_true")
    refresh_parser.add_argument("--preview", action="store_true")
    refresh_parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    refresh_parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD)

    repair_parser = subparsers.add_parser(
        "repair-paths", help="Localiza fontes movidas e corrige caminhos únicos."
    )
    add_common_paths(repair_parser)
    repair_parser.add_argument(
        "--apply", action="store_true",
        help="Grava as correções; sem esta opção apenas mostra a prévia.",
    )

    audit_parser = subparsers.add_parser("audit", help="Audita o pipeline sem reprocessar vídeos.")
    add_common_paths(audit_parser)
    audit_parser.add_argument("--reference", default="flutuando_idle")
    audit_parser.add_argument("--only", action="append")
    audit_parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    audit_parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD)
    audit_parser.add_argument("--fail-on-warning", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "scan":
        config = read_config(args.config.expanduser().resolve())
        candidates = discover(args.source_root, config, recursive=bool(args.recursive))
        payload = [candidate.__dict__ | {"path": str(candidate.path)} for candidate in candidates]
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif not candidates:
            print("Nenhuma fonte nova encontrada.")
        else:
            print(f"{len(candidates)} fonte(s) não registrada(s):")
            for candidate in candidates:
                print(
                    f"  {candidate.suggested_id} | {'loop' if candidate.loop else 'ação'} | "
                    f"{candidate.source_type} | {candidate.path}"
                )
        return 0

    if args.command == "add":
        register(args.paths, args)
        return 0

    if args.command == "process":
        items = register(args.paths, args)
        if args.dry_run:
            return 0
        ids = [str(item["id"]) for item in items]
        run_pipeline(ids, args)
        audit_args = argparse.Namespace(**vars(args))
        audit_args.reference = "flutuando_idle"
        report = audit(audit_args, only=set(ids))
        save_report(report, args.report_json, args.report_md)
        print(f"Pipeline concluído para: {', '.join(ids)}")
        return 0 if report.ok else 2

    if args.command == "refresh":
        config = read_config(args.config.expanduser().resolve())
        known = {str(item.get("id", "")) for item in config["animations"]}
        unknown = sorted(set(args.ids) - known)
        if unknown:
            raise ValueError("Ids não registrados: " + ", ".join(unknown))
        run_pipeline(args.ids, args)
        audit_args = argparse.Namespace(**vars(args))
        audit_args.reference = "flutuando_idle"
        report = audit(audit_args, only=set(args.ids))
        save_report(report, args.report_json, args.report_md)
        print(f"Reprocessamento concluído para: {', '.join(args.ids)}")
        return 0 if report.ok else 2

    if args.command == "repair-paths":
        config_path = args.config.expanduser().resolve()
        config = read_config(config_path)
        changes, ambiguous = repair_source_paths(config, args.source_root.expanduser().resolve())
        if not changes and not ambiguous:
            print("Nenhum caminho de fonte precisa de reparo.")
            return 0
        for change in changes:
            print(f"  {change['id']}: {change['from']} -> {change['to']}")
        for message in ambiguous:
            print(f"  AMBÍGUO: {message}")
        if args.apply and changes:
            write_json_atomic(config_path, config)
            print(f"{len(changes)} caminho(s) corrigido(s) em {config_path}.")
        elif changes:
            print("Prévia apenas. Execute novamente com --apply para gravar.")
        return 0 if not ambiguous else 2

    if args.command == "audit":
        report = audit(args, only=set(args.only or []) or None)
        save_report(report, args.report_json, args.report_md)
        print(
            f"Resultado: {len(report.errors)} erro(s), {len(report.warnings)} aviso(s), "
            f"{len(report.unregistered)} fonte(s) não registrada(s)."
        )
        if report.errors or (args.fail_on_warning and report.warnings):
            return 2
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
