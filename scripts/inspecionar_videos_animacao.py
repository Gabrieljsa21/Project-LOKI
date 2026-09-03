"""Gera metadados e folhas de contato para revisar vídeos de animação em massa."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Sequence

import cv2
from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "cache" / "animation_video_inspection"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
SAMPLES = (0.0, 0.25, 0.5, 0.75, 0.999)


def safe_name(path: Path) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", path.stem).strip("-") or "video"


def inspect_video(path: Path, output: Path) -> dict[str, object]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"Não foi possível abrir: {path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 30.0
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = frame_count / fps if fps > 0 else 0.0
    thumbs: list[Image.Image] = []
    sampled: list[dict[str, object]] = []
    thumb_width = 256
    thumb_height = max(1, round(thumb_width * height / width)) if width else 144
    for ratio in SAMPLES:
        index = min(max(0, round((frame_count - 1) * ratio)), max(0, frame_count - 1))
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, bgr = capture.read()
        if not ok:
            continue
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb).resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        thumbs.append(image)
        sampled.append({"frame": index, "time": round(index / fps, 3)})
    capture.release()
    if not thumbs:
        raise ValueError(f"O vídeo não produziu amostras: {path}")

    label_height = 24
    sheet = Image.new("RGB", (thumb_width * len(thumbs), thumb_height + label_height), "#202020")
    draw = ImageDraw.Draw(sheet)
    for column, (thumb, sample) in enumerate(zip(thumbs, sampled)):
        left = column * thumb_width
        sheet.paste(thumb, (left, label_height))
        draw.text((left + 6, 5), f"{sample['time']:.2f}s", fill="white")
    output.mkdir(parents=True, exist_ok=True)
    contact_sheet = output / f"{safe_name(path)}.jpg"
    sheet.save(contact_sheet, quality=90)
    return {
        "path": str(path),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "frameCount": frame_count,
        "duration": round(duration, 3),
        "samples": sampled,
        "contactSheet": str(contact_sheet),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspeciona vídeos de animação sem convertê-los.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    paths: list[Path] = []
    for raw in args.paths:
        path = raw.expanduser().resolve()
        if path.is_dir():
            paths.extend(
                sorted(
                    (entry for entry in path.iterdir() if entry.suffix.casefold() in VIDEO_EXTENSIONS),
                    key=lambda entry: entry.name.casefold(),
                )
            )
        else:
            paths.append(path)
    results = [inspect_video(path, args.output.expanduser().resolve()) for path in paths]
    output = args.output.expanduser().resolve()
    columns = 2
    cell_width = 640
    label_height = 22
    resized_sheets: list[tuple[str, Image.Image]] = []
    for result in results:
        with Image.open(str(result["contactSheet"])) as source:
            height = max(1, round(source.height * (cell_width - 12) / source.width))
            resized_sheets.append((Path(str(result["path"])).name, source.resize(
                (cell_width - 12, height), Image.Resampling.LANCZOS
            ).convert("RGB")))
    content_height = max((image.height for _, image in resized_sheets), default=1)
    rows = (len(resized_sheets) + columns - 1) // columns
    overview = Image.new("RGB", (cell_width * columns, rows * (content_height + label_height + 8)), "#181818")
    draw = ImageDraw.Draw(overview)
    for index, (name, image) in enumerate(resized_sheets):
        left = (index % columns) * cell_width + 6
        top = (index // columns) * (content_height + label_height + 8)
        draw.text((left, top + 3), name, fill="white")
        overview.paste(image, (left, top + label_height))
    overview_path = output / "overview.jpg"
    overview.save(overview_path, quality=90)

    report_path = output / "inspection.json"
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True, "videos": len(results), "report": str(report_path), "overview": str(overview_path)
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
