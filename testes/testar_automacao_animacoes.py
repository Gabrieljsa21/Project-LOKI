"""Testes puros do orquestrador de animações, sem abrir vídeos ou Qt."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import automatizar_animacoes as automation
from mascot import state_catalog


failures: list[str] = []


def check(name: str, condition: bool, detail: object = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name} {detail}")
        failures.append(name)


check(
    "safe_id remove acentos, espaços e timestamp",
    automation.safe_id("Leque Esnóbe_202608301234.mp4") == "leque_esnobe",
    automation.safe_id("Leque Esnóbe_202608301234.mp4"),
)
check("id com loop é reconhecido", automation.infer_loop("leque_esnobe_loop"))
check("ação sem loop não é marcada como loop", not automation.infer_loop("leque_para_flutuando"))

transition = automation.infer_state("flutuando_para_leque", False)
check("transição infere origem", transition["origin"] == "flutuando", transition)
check("transição infere destino", transition["destination"] == "leque", transition)
check("transição é não interrompível", transition["interruptible"] is False, transition)

loop_state = automation.infer_state("leque_esnobe_loop", True)
check("loop infere estado lógico pela categoria", loop_state["origin"] == "leque", loop_state)
check("loop permanece no mesmo estado", loop_state["destination"] == "leque", loop_state)
legacy_loop = automation.infer_state("leque-ironica_loop", True)
check("hífen legado não vira um estado separado", legacy_loop["origin"] == "leque", legacy_loop)

with tempfile.TemporaryDirectory() as temporary:
    temp = Path(temporary)
    source_root = temp / "sources"
    source_root.mkdir()
    video = source_root / "leque_esnobe_loop.mp4"
    video.write_bytes(b"fake-video")
    frames = source_root / "leque_misteriosa_loop"
    frames.mkdir()
    for index in range(3):
        (frames / f"frame_{index:03d}.png").write_bytes(b"fake-image")

    config_path = temp / "animations.json"
    config_path.write_text(
        json.dumps({"schemaVersion": 1, "animations": []}), encoding="utf-8"
    )
    config = automation.read_config(config_path)
    candidates = automation.discover(source_root, config)
    check("scan encontra vídeo e pasta de frames", len(candidates) == 2, candidates)

    args = argparse.Namespace(
        config=config_path,
        id=None,
        loop=None,
        scene=False,
        background="#00FF00",
        tolerance=70.0,
        feather=24.0,
        skip_start=0,
        skip_end=0,
        origin=None,
        destination=None,
        fallback=None,
        tags=None,
        interruptible=None,
        dry_run=False,
        reverse=False,
    )
    registered = automation.register([video], args)
    saved = automation.read_config(config_path)
    check("registro grava uma entrada", len(saved["animations"]) == 1, saved)
    check("registro infere loop pelo nome", registered[0]["loop"] is True, registered)
    check("registro grava state declarativo", isinstance(registered[0].get("state"), dict), registered)
    check("scan deixa de repetir fonte registrada", len(automation.discover(source_root, saved)) == 1)

    declarative = state_catalog._carregar_estados_declarativos(config_path)
    generated = declarative.get("leque_esnobe_loop")
    check("catálogo carrega state declarativo", generated is not None, declarative)
    check("state declarativo conserva loop", bool(generated and generated.loop), generated)
    check("state declarativo conserva origem", bool(generated and generated.estado_origem == "leque"), generated)

    moved_root = temp / "moved"
    moved_root.mkdir()
    moved_video = moved_root / "fonte-movida.mp4"
    moved_video.write_bytes(b"moved-video")
    repair_config = {
        "schemaVersion": 1,
        "animations": [{
            "id": "fonte-movida",
            "source": str(temp / "old" / "fonte-movida.mp4"),
            "loop": False,
        }],
    }
    changes, ambiguous = automation.repair_source_paths(repair_config, temp)
    check("reparo encontra fonte movida com nome único", len(changes) == 1, changes)
    check("reparo atualiza caminho em memória", repair_config["animations"][0]["source"] == str(moved_video), repair_config)
    check("reparo único não gera ambiguidade", not ambiguous, ambiguous)

metrics = automation.bbox_metrics((100, 50, 300, 450), (90, 40, 290, 440))
check("métrica conserva escala equivalente", metrics["widthRatio"] == 1.0, metrics)
check("métrica mede deslocamento", metrics["centerDeltaX"] == 10.0, metrics)

try:
    import importar_lote_animacoes as batch
except ModuleNotFoundError as exc:
    if exc.name != "PIL":
        raise
    print("SKIP: teste de geometria do importador exige Pillow")
else:
    prepared = batch.PreparedAnimation(
        id="fora-da-geometria",
        sources=(),
        staged_frames=Path("."),
        frame_count=1,
        loop=False,
        canvas=(1280, 720),
        bbox=(10, 10, 1200, 700),
        asset_type="character",
    )
    geometry = {
        "sourceCanvas": {"width": 1280, "height": 720},
        "sourceCrop": {"left": 200, "top": 0, "right": 1000, "bottom": 720},
    }
    try:
        batch.ensure_fits(prepared, geometry)
        rejected = False
    except ValueError:
        rejected = True
    check("importador rejeita bbox fora da geometria bloqueada", rejected)
    from PIL import Image

    empty = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    visible = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    visible.putpixel((8, 8), (255, 255, 255, 255))
    try:
        batch.union_bbox([visible, empty])
        normal_rejected_empty = False
    except ValueError:
        normal_rejected_empty = True
    check("animação character continua rejeitando frame vazio", normal_rejected_empty)
    check(
        "cena aceita frame vazio durante teleportes",
        batch.union_bbox([visible, empty], allow_empty_frames=True) == (8, 8, 9, 9),
    )
    normalized, normalized_crop = batch.single.normalize_frames(
        [visible.copy(), empty.copy()],
        preserve_canvas=False,
        padding=0,
        max_cell=0,
        fixed_crop=(0, 0, 16, 16),
        allow_empty_frames=True,
    )
    check(
        "empacotador de cena conserva frame vazio de teleporte",
        normalized_crop == (0, 0, 16, 16)
        and batch.single.alpha_bbox(normalized[1]) is None,
    )

if failures:
    print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
    raise SystemExit(1)
print("\nTodos os testes da automação de animações passaram.")
