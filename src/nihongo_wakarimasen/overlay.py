from __future__ import annotations

import ctypes
import ctypes.wintypes
from dataclasses import replace
from html import escape
import re
import sys
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .audio import CaptureProcessOption, list_capture_process_options
from .config import AppConfig
from .models import Utterance
from .pipeline import ListeningPipeline


GWL_EXSTYLE = -20
HOTKEY_CLICK_THROUGH = 1
MOD_NOREPEAT = 0x4000
VK_F6 = 0x75
WM_HOTKEY = 0x0312
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020


class SubtitleWindow(QWidget):
    update_requested = Signal(list)
    status_requested = Signal(str)
    error_requested = Signal(str)
    source_picker_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Nihongo Wakarimasen")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.click_through = False
        self.capture_source = "source: not selected"

        self.status_label = QLabel("starting...")
        self.status_label.setFont(QFont("Malgun Gothic", 9))
        self.status_label.setMinimumWidth(0)
        self.status_label.setFixedHeight(24)
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.status_label.setStyleSheet(
            """
            QLabel {
                color: rgba(226, 232, 240, 190);
                background: rgba(15, 23, 42, 210);
                padding: 5px 10px 0 10px;
            }
            """
        )

        self.label = QLabel("waiting...")
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self.label.setFont(QFont("Malgun Gothic", 12))
        self.label.setMinimumWidth(0)
        self.label.setFixedHeight(218)
        self.label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.label.setStyleSheet(
            """
            QLabel {
                color: #f8fafc;
                background: rgba(15, 23, 42, 210);
                border: 1px solid rgba(148, 163, 184, 110);
                border-top: 0;
                padding: 6px 12px 12px 12px;
            }
            """
        )

        self.mode_label = QLabel("M", self)
        self.mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mode_label.setFixedSize(28, 28)
        self.mode_label.setToolTip("F6: mouse pass-through off")

        self.menu_button = QPushButton("☰", self)
        self.menu_button.setFixedSize(28, 28)
        self.menu_button.setToolTip("Select captured app audio")
        self.menu_button.clicked.connect(self.source_picker_requested.emit)
        self.menu_button.setStyleSheet(
            """
            QPushButton {
                color: #ffffff;
                background: rgba(30, 41, 59, 225);
                border: 1px solid rgba(255, 255, 255, 150);
                border-radius: 14px;
                font-weight: 800;
                font-size: 15px;
            }
            QPushButton:hover {
                background: rgba(51, 65, 85, 240);
            }
            """
        )

        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addWidget(self.label)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        self.resize(820, 260)
        self.update_requested.connect(self.render)
        self.status_requested.connect(self.render_status)
        self.error_requested.connect(self.render_error)
        self._drag_position = None
        self._update_mode_indicator()

    def render(self, utterances: list[Utterance]) -> None:
        final_items = [item for item in utterances if item.korean]
        provisional_items = [item for item in utterances if not item.korean and item.japanese]

        lines = [
            self._render_pair(
                self._format_text(item.japanese, 120),
                self._format_text(item.korean, 170),
            )
            for item in final_items[-3:]
            if self._has_display_text(item.japanese) or self._has_display_text(item.korean)
        ]

        if provisional_items:
            lines.append(self._render_provisional(provisional_items[-1].japanese))
        self.label.setText("".join(lines) if lines else "waiting...")

    def _render_pair(self, japanese: str, korean: str) -> str:
        return (
            "<div style='margin-bottom:8px;'>"
            f"<div style='font-size:11px; color:#cbd5e1; margin-bottom:1px;'>{japanese}</div>"
            f"<div style='font-size:16px; color:#ffffff; font-weight:700; margin-bottom:5px;'>{korean}</div>"
            "</div>"
        )

    def _render_provisional(self, japanese: str) -> str:
        text = self._format_text(japanese, 96)
        return (
            "<div style='margin-top:2px; padding-top:3px; border-top:1px solid rgba(148, 163, 184, 55);'>"
            f"<span style='font-size:10px; color:#93c5fd; font-weight:700;'>JP</span> "
            f"<span style='font-size:11px; color:#bfdbfe;'>{text}</span>"
            f"<span style='font-size:10px; color:#94a3b8;'> ...</span>"
            "</div>"
        )

    def render_status(self, message: str) -> None:
        self.status_label.setText(self._fit_status_text(f"{self.capture_source} | {message}"))

    def render_error(self, message: str) -> None:
        self.status_label.setText("error")
        message = self._fit_text(message, 260)
        self.label.setText(
            "<div style='font-size:15px; color:#fecaca;'>"
            f"{escape(message)}"
            "</div>"
        )

    def set_capture_source(self, source: str) -> None:
        self.capture_source = f"capturing: {source}"
        self.render_status("ready")

    def _fit_status_text(self, text: str) -> str:
        compact = " ".join(text.split())
        return compact if len(compact) <= 150 else compact[:147] + "..."

    def _format_text(self, text: str, max_chars: int) -> str:
        fitted = self._fit_text(text, max_chars)
        return escape(fitted).replace("\n", "<br>")

    def _fit_text(self, text: str, max_chars: int) -> str:
        compact = " ".join(text.split())
        if len(compact) <= max_chars:
            return compact
        return "... " + compact[-max(0, max_chars - 4) :]

    def _has_display_text(self, text: str) -> bool:
        return bool(re.sub(r"[\s.!?。！？、,]+", "", text))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.click_through:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.click_through:
            return
        if self._drag_position is not None:
            self.move(event.globalPosition().toPoint() - self._drag_position)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_position = None

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_F6:
            self.toggle_click_through()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.mode_label.move(self.width() - self.mode_label.width() - 8, 8)
        self.menu_button.move(self.mode_label.x() - self.menu_button.width() - 6, 8)

    def nativeEvent(self, event_type, message):  # noqa: N802
        if sys.platform == "win32":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_CLICK_THROUGH:
                self.toggle_click_through()
                return True, 0
        return super().nativeEvent(event_type, message)

    def register_hotkeys(self) -> None:
        if sys.platform != "win32":
            return
        ctypes.windll.user32.RegisterHotKey(
            int(self.winId()),
            HOTKEY_CLICK_THROUGH,
            MOD_NOREPEAT,
            VK_F6,
        )

    def unregister_hotkeys(self) -> None:
        if sys.platform != "win32":
            return
        ctypes.windll.user32.UnregisterHotKey(int(self.winId()), HOTKEY_CLICK_THROUGH)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.unregister_hotkeys()
        super().closeEvent(event)

    def toggle_click_through(self) -> None:
        self.click_through = not self.click_through
        self._apply_click_through()
        self._update_mode_indicator()

    def _apply_click_through(self) -> None:
        if sys.platform != "win32":
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, self.click_through)
            return
        hwnd = int(self.winId())
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if self.click_through:
            ex_style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
        else:
            ex_style &= ~WS_EX_TRANSPARENT
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

    def _update_mode_indicator(self) -> None:
        if self.click_through:
            self.mode_label.setText(">")
            self.mode_label.setToolTip("F6: mouse pass-through on")
            color = "rgba(34, 197, 94, 225)"
        else:
            self.mode_label.setText("M")
            self.mode_label.setToolTip("F6: mouse pass-through off")
            color = "rgba(248, 113, 113, 225)"
        self.mode_label.setStyleSheet(
            f"""
            QLabel {{
                color: #ffffff;
                background: {color};
                border: 1px solid rgba(255, 255, 255, 170);
                border-radius: 14px;
                font-weight: 800;
                font-size: 13px;
            }}
            """
        )
        self.mode_label.raise_()
        self.menu_button.raise_()


class CaptureProcessDialog(QDialog):
    def __init__(
        self,
        current_capture_process: str | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("어느 사운드를 가져올까요?")
        self.setModal(True)
        self.selected_option: CaptureProcessOption | None = None
        self.current_capture_process = current_capture_process

        title = QLabel("어느 사운드를 가져올까요?")
        title.setFont(QFont("Malgun Gothic", 13, QFont.Weight.Bold))
        description = QLabel("Discord는 실행 중이면 소리가 없어도 목록에 표시됩니다.")
        description.setFont(QFont("Malgun Gothic", 9))
        description.setStyleSheet("color: #64748b;")

        self.list_widget = QListWidget()
        self.list_widget.setMinimumSize(560, 260)
        self.list_widget.itemDoubleClicked.connect(self.accept)

        self.refresh_button = QPushButton("새로고침")
        self.cancel_button = QPushButton("취소")
        self.select_button = QPushButton("선택")
        self.refresh_button.clicked.connect(self.refresh)
        self.cancel_button.clicked.connect(self.reject)
        self.select_button.clicked.connect(self.accept)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.refresh_button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.select_button)

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(self.list_widget)
        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        options = list_capture_process_options(
            [self.current_capture_process] if self.current_capture_process else []
        )
        if not options:
            item = QListWidgetItem(
                "캡처 가능한 앱을 찾지 못했습니다. Discord나 Chrome에서 소리를 재생한 뒤 새로고침하세요."
            )
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(item)
            return

        selected_row = 0
        for index, option in enumerate(options):
            item = QListWidgetItem(option.label)
            item.setData(Qt.ItemDataRole.UserRole, option)
            self.list_widget.addItem(item)
            if self.current_capture_process and (
                self.current_capture_process == option.capture_value
                or self.current_capture_process.lower() == option.name.lower()
            ):
                selected_row = index
        self.list_widget.setCurrentRow(selected_row)

    def accept(self) -> None:  # noqa: D102
        item = self.list_widget.currentItem()
        option = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if option is None:
            return
        self.selected_option = option
        super().accept()


def run_overlay(config: AppConfig) -> int:
    app = QApplication(sys.argv)

    startup_dialog = CaptureProcessDialog(config.capture_process)
    if startup_dialog.exec() != QDialog.DialogCode.Accepted or startup_dialog.selected_option is None:
        return 1

    selected_option = startup_dialog.selected_option
    current_config = replace(config, capture_process=selected_option.capture_value)

    window = SubtitleWindow()
    window.set_capture_source(selected_option.label)
    window.show()
    window.register_hotkeys()

    screen = app.primaryScreen()
    if screen is not None:
        geometry = screen.availableGeometry()
        window.move(
            geometry.center().x() - window.width() // 2,
            geometry.bottom() - window.height() - 40,
        )

    state_lock = threading.Lock()
    state: dict[str, object] = {
        "generation": 0,
        "pipeline": None,
        "config": current_config,
        "source": selected_option.label,
    }

    def guarded_status(generation: int, message: str) -> None:
        with state_lock:
            if generation != state["generation"]:
                return
        window.status_requested.emit(message)

    def guarded_update(generation: int, utterances: list[Utterance]) -> None:
        with state_lock:
            if generation != state["generation"]:
                return
        window.update_requested.emit(utterances)

    def worker(generation: int, worker_config: AppConfig) -> None:
        try:
            if worker_config.realtime_translate:
                from .realtime_translate import RealtimeTranslatePipeline

                pipeline = RealtimeTranslatePipeline(
                    worker_config,
                    status=lambda message: guarded_status(generation, message),
                )
            else:
                pipeline = ListeningPipeline(
                    worker_config,
                    status=lambda message: guarded_status(generation, message),
                )
            with state_lock:
                if generation != state["generation"]:
                    return
                state["pipeline"] = pipeline
            pipeline.run_forever(lambda utterances: guarded_update(generation, utterances))
        except Exception as exc:
            with state_lock:
                if generation != state["generation"]:
                    return
            window.error_requested.emit(str(exc))

    def start_worker(worker_config: AppConfig, source: str) -> None:
        with state_lock:
            previous = state.get("pipeline")
            if previous is not None and hasattr(previous, "stop"):
                previous.stop()
            state["generation"] = int(state["generation"]) + 1
            generation = int(state["generation"])
            state["pipeline"] = None
            state["config"] = worker_config
            state["source"] = source
        window.set_capture_source(source)
        thread = threading.Thread(target=worker, args=(generation, worker_config), daemon=True)
        thread.start()

    def open_source_picker() -> None:
        with state_lock:
            active_config = state["config"]
        dialog = CaptureProcessDialog(active_config.capture_process, window)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_option is None:
            return
        option = dialog.selected_option
        next_config = replace(active_config, capture_process=option.capture_value)
        start_worker(next_config, option.label)

    window.source_picker_requested.connect(open_source_picker)
    start_worker(current_config, selected_option.label)
    return app.exec()
