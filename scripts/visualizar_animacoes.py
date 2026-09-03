"""Visualizador simples dos sprites finais da Galateia.

Lê diretamente ``assets/galateia/animations/*/animation.json`` e o atlas
correspondente. Assim, a prévia usa exatamente os mesmos arquivos que a aplicação.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


ROOT = Path(__file__).resolve().parents[1]
ANIMATIONS_DIR = ROOT / "assets" / "galateia" / "animations"


@dataclass(frozen=True)
class AnimationAsset:
    id: str
    directory: Path
    atlas: QPixmap
    frames: tuple[QPixmap, ...]
    frame_duration_ms: int
    effective_fps: float
    loop: bool
    cell_width: int
    cell_height: int
    source_bytes: int

    @property
    def duration_seconds(self) -> float:
        return len(self.frames) * self.frame_duration_ms / 1000

    @classmethod
    def load(cls, manifest_path: Path) -> "AnimationAsset":
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        grid = data["grid"]
        columns = int(grid["columns"])
        rows = int(grid["rows"])
        cell_width = int(grid["cellWidth"])
        cell_height = int(grid["cellHeight"])
        frame_count = int(data["frameCount"])
        if frame_count < 1 or frame_count > columns * rows:
            raise ValueError("quantidade de quadros incompatível com a grade")

        texture_path = manifest_path.parent / data["texture"]
        atlas = QPixmap(str(texture_path))
        if atlas.isNull():
            raise ValueError(f"não foi possível abrir {texture_path.name}")
        expected = QSize(columns * cell_width, rows * cell_height)
        if atlas.size() != expected:
            raise ValueError(
                f"atlas mede {atlas.width()}x{atlas.height()}, esperado "
                f"{expected.width()}x{expected.height()}"
            )

        frames = []
        for index in range(frame_count):
            x = (index % columns) * cell_width
            y = (index // columns) * cell_height
            frames.append(atlas.copy(QRect(x, y, cell_width, cell_height)))

        return cls(
            id=str(data["id"]),
            directory=manifest_path.parent,
            atlas=atlas,
            frames=tuple(frames),
            frame_duration_ms=max(1, int(data["frameDurationMs"])),
            effective_fps=float(data.get("effectiveFps", 1000 / int(data["frameDurationMs"]))),
            loop=bool(data["loop"]),
            cell_width=cell_width,
            cell_height=cell_height,
            source_bytes=texture_path.stat().st_size,
        )


class AnimationCanvas(QWidget):
    frame_changed = Signal(int)

    def __init__(self, *, transparent: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.asset: AnimationAsset | None = None
        self.sequence: tuple[AnimationAsset, ...] = ()
        self.sequence_index = 0
        self.sequence_loop = False
        self.frame_index = 0
        self.playing = False
        self.repeat_transition = False
        self.scale_percent = 100
        self.transparent = transparent
        self._waiting_to_repeat = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)
        self.setMinimumSize(360, 430)

    def set_asset(self, asset: AnimationAsset, *, autoplay: bool = True) -> None:
        self.sequence = ()
        self.sequence_index = 0
        self._activate_asset(asset, autoplay=autoplay)

    def set_sequence(
        self,
        assets: list[AnimationAsset] | tuple[AnimationAsset, ...],
        *,
        loop: bool = False,
        autoplay: bool = True,
    ) -> None:
        if not assets:
            return
        self.sequence = tuple(assets)
        self.sequence_index = 0
        self.sequence_loop = loop
        self._activate_asset(self.sequence[0], autoplay=autoplay)

    def _activate_asset(self, asset: AnimationAsset, *, autoplay: bool) -> None:
        self.asset = asset
        self.frame_index = 0
        self._waiting_to_repeat = False
        self.timer.setInterval(asset.frame_duration_ms)
        self.resize_for_asset()
        self.frame_changed.emit(0)
        self.update()
        self.set_playing(autoplay)

    def resize_for_asset(self) -> None:
        if self.transparent and self.asset:
            factor = self.scale_percent / 100
            self.setFixedSize(
                max(1, round(self.asset.cell_width * factor)),
                max(1, round(self.asset.cell_height * factor)),
            )

    def set_scale_percent(self, value: int) -> None:
        self.scale_percent = value
        self.resize_for_asset()
        self.update()

    def set_playing(self, playing: bool) -> None:
        self.playing = bool(playing and self.asset)
        if self.playing and not self._waiting_to_repeat:
            self.timer.start()
        else:
            self.timer.stop()

    def restart(self) -> None:
        if not self.asset:
            return
        if self.sequence:
            self.sequence_index = 0
            self.asset = self.sequence[0]
            self.timer.setInterval(self.asset.frame_duration_ms)
            self.resize_for_asset()
        self._waiting_to_repeat = False
        self.frame_index = 0
        self.frame_changed.emit(0)
        self.update()
        self.set_playing(True)

    def step(self, delta: int) -> None:
        if not self.asset:
            return
        self.set_playing(False)
        next_frame = self.frame_index + delta
        if self.sequence and next_frame >= len(self.asset.frames) and self.sequence_index < len(self.sequence) - 1:
            self.sequence_index += 1
            self.asset = self.sequence[self.sequence_index]
            self.timer.setInterval(self.asset.frame_duration_ms)
            self.resize_for_asset()
            self.frame_index = 0
        elif self.sequence and next_frame < 0 and self.sequence_index > 0:
            self.sequence_index -= 1
            self.asset = self.sequence[self.sequence_index]
            self.timer.setInterval(self.asset.frame_duration_ms)
            self.resize_for_asset()
            self.frame_index = len(self.asset.frames) - 1
        else:
            self.frame_index = max(0, min(len(self.asset.frames) - 1, next_frame))
        self.frame_changed.emit(self.frame_index)
        self.update()

    def _advance(self) -> None:
        if not self.asset:
            return
        last = len(self.asset.frames) - 1
        if self.frame_index < last:
            self.frame_index += 1
        elif self.sequence:
            if self.sequence_index < len(self.sequence) - 1:
                self.sequence_index += 1
            elif self.sequence_loop:
                self.sequence_index = 0
            else:
                self.set_playing(False)
                return
            self.asset = self.sequence[self.sequence_index]
            self.frame_index = 0
            self.timer.setInterval(self.asset.frame_duration_ms)
            self.resize_for_asset()
        elif self.asset.loop:
            self.frame_index = 0
        elif self.repeat_transition:
            self.timer.stop()
            self._waiting_to_repeat = True
            QTimer.singleShot(850, self._repeat_after_pause)
            return
        else:
            self.set_playing(False)
            return
        self.frame_changed.emit(self.frame_index)
        self.update()

    def _repeat_after_pause(self) -> None:
        if not self.asset or not self.playing:
            self._waiting_to_repeat = False
            return
        self._waiting_to_repeat = False
        self.frame_index = 0
        self.frame_changed.emit(0)
        self.update()
        self.timer.start()

    def paintEvent(self, _event) -> None:  # noqa: N802 - nome exigido pelo Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if not self.transparent:
            self._paint_checkerboard(painter)
        if not self.asset:
            return

        frame = self.asset.frames[self.frame_index]
        if self.transparent:
            target = self.rect()
        else:
            margin = 18
            available = self.rect().adjusted(margin, margin, -margin, -margin)
            scaled = frame.size().scaled(available.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRect(QPoint(0, 0), scaled)
            target.moveCenter(available.center())
        painter.drawPixmap(target, frame)

    def _paint_checkerboard(self, painter: QPainter) -> None:
        size = 18
        colors = (QColor("#171b24"), QColor("#202633"))
        for y in range(0, self.height(), size):
            for x in range(0, self.width(), size):
                painter.fillRect(x, y, size, size, colors[(x // size + y // size) % 2])


class DesktopOverlay(AnimationCanvas):
    closed = Signal(object)

    def __init__(
        self,
        assets: tuple[AnimationAsset, ...],
        scale_percent: int,
        repeat: bool,
        sequence_loop: bool,
    ):
        super().__init__(transparent=True)
        self._drag_offset: QPoint | None = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.repeat_transition = repeat
        self.scale_percent = scale_percent
        if len(assets) > 1:
            self.set_sequence(assets, loop=sequence_loop)
        else:
            self.set_asset(assets[0])
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.right() - self.width() - 24, area.bottom() - self.height() - 8)
        self.setToolTip("Arraste para mover • Espaço: pausar • R: reiniciar • Esc: fechar")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.close()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Space:
            self.set_playing(not self.playing)
        elif event.key() == Qt.Key.Key_R:
            self.restart()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit(self)
        super().closeEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, assets: list[AnimationAsset], requested_id: str | None = None):
        super().__init__()
        self.assets = assets
        self.overlays: list[DesktopOverlay] = []
        self.setWindowTitle("Prévia das animações da Galateia")
        self.resize(820, 820)
        self.setMinimumSize(700, 700)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title = QLabel("Animações da Galateia")
        title.setObjectName("title")
        subtitle = QLabel("Prévia dos arquivos finais usados pelo projeto")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        top = QHBoxLayout()
        top.addWidget(QLabel("Animação"))
        self.combo = QComboBox()
        for asset in assets:
            self.combo.addItem(asset.id.replace("_", " "), asset)
        top.addWidget(self.combo, 1)
        self.add_sequence_button = QPushButton("Adicionar à sequência")
        top.addWidget(self.add_sequence_button)
        layout.addLayout(top)

        sequence_header = QHBoxLayout()
        sequence_title = QLabel("Sequência para testar")
        sequence_title.setObjectName("sectionTitle")
        sequence_header.addWidget(sequence_title)
        sequence_header.addStretch()
        self.sequence_loop_checkbox = QCheckBox("Repetir sequência")
        sequence_header.addWidget(self.sequence_loop_checkbox)
        layout.addLayout(sequence_header)

        sequence_row = QHBoxLayout()
        self.sequence_list = QListWidget()
        self.sequence_list.setObjectName("sequence")
        self.sequence_list.setMaximumHeight(112)
        sequence_row.addWidget(self.sequence_list, 1)
        sequence_buttons = QVBoxLayout()
        self.move_up_button = QPushButton("Subir")
        self.move_down_button = QPushButton("Descer")
        self.remove_sequence_button = QPushButton("Remover")
        self.clear_sequence_button = QPushButton("Limpar")
        for button in (
            self.move_up_button,
            self.move_down_button,
            self.remove_sequence_button,
            self.clear_sequence_button,
        ):
            sequence_buttons.addWidget(button)
        sequence_row.addLayout(sequence_buttons)
        layout.addLayout(sequence_row)

        self.play_sequence_button = QPushButton("Reproduzir sequência")
        self.play_sequence_button.setObjectName("sequencePrimary")
        layout.addWidget(self.play_sequence_button)

        self.canvas = AnimationCanvas()
        self.canvas.setObjectName("preview")
        layout.addWidget(self.canvas, 1)

        self.status = QLabel()
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        controls = QHBoxLayout()
        self.previous_button = QPushButton("◀ Quadro")
        self.play_button = QPushButton("Pausar")
        self.restart_button = QPushButton("Reiniciar")
        self.next_button = QPushButton("Quadro ▶")
        controls.addWidget(self.previous_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.restart_button)
        controls.addWidget(self.next_button)
        layout.addLayout(controls)

        options = QHBoxLayout()
        self.repeat_checkbox = QCheckBox("Repetir transições para conferir")
        self.repeat_checkbox.setChecked(True)
        options.addWidget(self.repeat_checkbox)
        options.addStretch()
        options.addWidget(QLabel("Tamanho na tela"))
        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(50, 150)
        self.scale_slider.setValue(100)
        self.scale_slider.setFixedWidth(120)
        self.scale_label = QLabel("100%")
        options.addWidget(self.scale_slider)
        options.addWidget(self.scale_label)
        layout.addLayout(options)

        self.overlay_button = QPushButton("Mostrar reprodução atual sobre a área de trabalho")
        self.overlay_button.setObjectName("primary")
        layout.addWidget(self.overlay_button)

        hint = QLabel(
            "Na área de trabalho: arraste para mover • Espaço pausa • R reinicia • "
            "Esc ou botão direito fecha"
        )
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.setCentralWidget(root)
        self._set_style()

        self.combo.currentIndexChanged.connect(self._select_asset)
        self.add_sequence_button.clicked.connect(self._add_to_sequence)
        self.move_up_button.clicked.connect(lambda: self._move_sequence(-1))
        self.move_down_button.clicked.connect(lambda: self._move_sequence(1))
        self.remove_sequence_button.clicked.connect(self._remove_from_sequence)
        self.clear_sequence_button.clicked.connect(lambda: self.sequence_list.clear())
        self.play_sequence_button.clicked.connect(self._play_sequence)
        self.sequence_list.itemDoubleClicked.connect(lambda _item: self._play_sequence())
        self.canvas.frame_changed.connect(self._update_status)
        self.play_button.clicked.connect(self._toggle_play)
        self.restart_button.clicked.connect(self.canvas.restart)
        self.previous_button.clicked.connect(lambda: self.canvas.step(-1))
        self.next_button.clicked.connect(lambda: self.canvas.step(1))
        self.repeat_checkbox.toggled.connect(self._set_repeat)
        self.scale_slider.valueChanged.connect(self._set_scale_label)
        self.overlay_button.clicked.connect(self._show_overlay)

        selected = 0
        if requested_id:
            for index, asset in enumerate(assets):
                if asset.id == requested_id:
                    selected = index
                    break
        else:
            selected = max(range(len(assets)), key=lambda i: assets[i].directory.stat().st_mtime)
        self.combo.setCurrentIndex(selected)
        self._select_asset(selected)

    def _set_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #10141c; color: #e8edf7; font: 10pt "Segoe UI"; }
            QLabel#title { font-size: 22pt; font-weight: 700; color: #f5f8ff; }
            QLabel#subtitle, QLabel#hint { color: #8f9aaf; }
            QLabel#sectionTitle { color: #b9c8df; font-weight: 600; }
            QComboBox, QPushButton { background: #202633; border: 1px solid #353d50;
                border-radius: 7px; padding: 8px 11px; }
            QListWidget#sequence { background: #151a24; border: 1px solid #353d50;
                border-radius: 7px; padding: 5px; }
            QListWidget#sequence::item { padding: 5px 7px; border-radius: 4px; }
            QListWidget#sequence::item:selected { background: #28566d; color: #ffffff; }
            QComboBox:hover, QPushButton:hover { border-color: #55bde8; background: #262e3d; }
            QPushButton:pressed { background: #171c27; }
            QPushButton#primary { background: #167ca7; border-color: #38b6e9; font-weight: 600; }
            QPushButton#primary:hover { background: #1c91bf; }
            QPushButton#sequencePrimary { background: #284d78; border-color: #4d83bd; font-weight: 600; }
            QPushButton#sequencePrimary:hover { background: #32618f; }
            QWidget#preview { border: 1px solid #353d50; border-radius: 10px; }
            QSlider::groove:horizontal { height: 5px; background: #31394a; border-radius: 2px; }
            QSlider::handle:horizontal { width: 15px; margin: -5px 0; background: #55c8f5;
                border-radius: 7px; }
            """
        )

    def _current_asset(self) -> AnimationAsset:
        return self.combo.currentData()

    def _select_asset(self, _index: int) -> None:
        asset = self._current_asset()
        self.canvas.repeat_transition = self.repeat_checkbox.isChecked()
        self.canvas.set_asset(asset)
        self.play_button.setText("Pausar")

    def _add_to_sequence(self) -> None:
        asset = self._current_asset()
        item = QListWidgetItem(asset.id.replace("_", " "))
        item.setData(Qt.ItemDataRole.UserRole, asset.id)
        self.sequence_list.addItem(item)
        self.sequence_list.setCurrentItem(item)

    def _sequence_assets(self) -> list[AnimationAsset]:
        by_id = {asset.id: asset for asset in self.assets}
        return [
            by_id[self.sequence_list.item(index).data(Qt.ItemDataRole.UserRole)]
            for index in range(self.sequence_list.count())
        ]

    def _move_sequence(self, delta: int) -> None:
        row = self.sequence_list.currentRow()
        target = row + delta
        if row < 0 or target < 0 or target >= self.sequence_list.count():
            return
        item = self.sequence_list.takeItem(row)
        self.sequence_list.insertItem(target, item)
        self.sequence_list.setCurrentRow(target)

    def _remove_from_sequence(self) -> None:
        row = self.sequence_list.currentRow()
        if row >= 0:
            self.sequence_list.takeItem(row)

    def _play_sequence(self) -> None:
        assets = self._sequence_assets()
        if not assets:
            QMessageBox.information(self, "Sequência vazia", "Adicione pelo menos uma animação à sequência.")
            return
        self.canvas.repeat_transition = False
        self.canvas.set_sequence(assets, loop=self.sequence_loop_checkbox.isChecked())
        self.play_button.setText("Pausar")

    def _toggle_play(self) -> None:
        if not self.canvas.playing:
            if self.canvas.asset and self.canvas.frame_index == len(self.canvas.asset.frames) - 1:
                self.canvas.restart()
            else:
                self.canvas.set_playing(True)
        else:
            self.canvas.set_playing(False)
        self.play_button.setText("Pausar" if self.canvas.playing else "Continuar")

    def _set_repeat(self, checked: bool) -> None:
        self.canvas.repeat_transition = checked

    def _set_scale_label(self, value: int) -> None:
        self.scale_label.setText(f"{value}%")

    def _update_status(self, frame_index: int) -> None:
        asset = self.canvas.asset
        if not asset:
            return
        loop_text = "loop" if asset.loop else "transição"
        sequence_text = ""
        if self.canvas.sequence:
            sequence_text = (
                f"Sequência {self.canvas.sequence_index + 1}/{len(self.canvas.sequence)}  •  "
                f"{asset.id.replace('_', ' ')}  •  "
            )
        size_mb = asset.source_bytes / (1024 * 1024)
        self.status.setText(
            f"{sequence_text}Quadro {frame_index + 1}/{len(asset.frames)}  •  "
            f"{asset.effective_fps:g} FPS  •  {asset.duration_seconds:.2f}s  •  "
            f"{loop_text}  •  {size_mb:.2f} MB"
        )

    def _show_overlay(self) -> None:
        assets = self.canvas.sequence or (self._current_asset(),)
        overlay = DesktopOverlay(
            assets,
            self.scale_slider.value(),
            self.repeat_checkbox.isChecked(),
            self.canvas.sequence_loop,
        )
        overlay.closed.connect(self._remove_overlay)
        self.overlays.append(overlay)
        overlay.show()
        overlay.activateWindow()

    def _remove_overlay(self, overlay: DesktopOverlay) -> None:
        if overlay in self.overlays:
            self.overlays.remove(overlay)


def discover_assets() -> tuple[list[AnimationAsset], list[str]]:
    assets: list[AnimationAsset] = []
    errors: list[str] = []
    for manifest in sorted(ANIMATIONS_DIR.glob("*/animation.json")):
        try:
            assets.append(AnimationAsset.load(manifest))
        except Exception as exc:  # Mostra pacote inválido sem derrubar os demais.
            errors.append(f"{manifest.parent.name}: {exc}")
    return assets, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualiza as animações finais da Galateia")
    parser.add_argument("--animation", help="ID da animação que deve ser selecionada")
    parser.add_argument("--overlay", action="store_true", help="abre também sobre a área de trabalho")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Animações da Galateia")
    assets, errors = discover_assets()
    if not assets:
        QMessageBox.critical(
            None,
            "Nenhuma animação encontrada",
            "Não há animações válidas em:\n" + str(ANIMATIONS_DIR),
        )
        return 1

    window = MainWindow(assets, args.animation)
    window.show()
    if errors:
        QMessageBox.warning(window, "Algumas animações foram ignoradas", "\n".join(errors))
    if args.overlay:
        QTimer.singleShot(250, window._show_overlay)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
