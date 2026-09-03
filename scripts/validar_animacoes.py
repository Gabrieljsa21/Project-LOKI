"""Valida que animações da Galateia compartilham geometria e arquivos obrigatórios.

Roda sem Qt/QApplication (checagem rápida de terminal/CI). A regra de
validação em si (schema, geometria, células) vive em
`features/mascot/asset_repository.py` - este script só resolve a lista de
ids esperados (`animacoes_galateia.json`) e formata o relatório; nunca
duplica a regra.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT / "assets" / "galateia" / "animations"
DEFAULT_CONFIG = PROJECT_ROOT / "data" / "animacoes_galateia.json"

sys.path.insert(0, str(PROJECT_ROOT))
from mascot import asset_repository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Confere a geometria comum das animações da Galateia.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    root = args.root.resolve()
    geometry_path = root / "geometry.json"
    expected = json.loads(geometry_path.read_text(encoding="utf-8"))
    expected = {
        "sourceCanvas": expected["sourceCanvas"],
        "sourceCrop": expected["sourceCrop"],
        "cell": expected["cell"],
        "pivot": expected["pivot"],
    }
    config = json.loads(args.config.resolve().read_text(encoding="utf-8"))
    expected_ids = [str(item["id"]) for item in config["animations"]]
    errors: list[str] = []
    rows: list[dict[str, object]] = []

    for animation_id in expected_ids:
        folder = root / animation_id
        manifest_path = folder / "animation.json"
        atlas_path = folder / "spritesheet.webp"
        missing = [path.name for path in (manifest_path, atlas_path) if not path.is_file()]
        if missing:
            errors.append(f"{animation_id}: faltando {', '.join(missing)}")
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        try:
            asset_repository.validar_manifesto(animation_id, manifest, expected)
        except asset_repository.AssetInvalido as exc:
            errors.append(str(exc))
        grid = manifest["grid"]
        rows.append(
            {
                "id": animation_id,
                "frames": int(manifest["frameCount"]),
                "loop": bool(manifest["loop"]),
                "cell": f"{grid['cellWidth']}x{grid['cellHeight']}",
                "atlasBytes": atlas_path.stat().st_size,
            }
        )

    result = {"ok": not errors, "geometry": expected, "animations": rows, "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
