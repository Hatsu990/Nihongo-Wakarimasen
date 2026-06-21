from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig
from .papago_credentials import load_papago_credentials, save_papago_credentials


class HotwordManagerWindow(QWidget):
    def __init__(
        self,
        path: Path,
        user_translation_dictionary_path: Path,
        papago_credentials_path: Path,
    ) -> None:
        super().__init__()
        self.path = path
        self.user_translation_dictionary_path = user_translation_dictionary_path
        self.papago_credentials_path = papago_credentials_path
        self.entries = self._load_entries()
        self.setWindowTitle("Nihongo Wakarimasen - 이름 사전")
        self.resize(640, 480)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("이름 / 원문")
        self.hiragana_input = QLineEdit()
        self.hiragana_input.setPlaceholderText("히라가나")
        self.katakana_input = QLineEdit()
        self.katakana_input.setPlaceholderText("가타카나")
        self.korean_input = QLineEdit()
        self.korean_input.setPlaceholderText("한글 표시")

        add_button = QPushButton("등록")
        add_button.clicked.connect(self.add_entry)

        register_layout = QVBoxLayout()
        register_layout.addWidget(QLabel("이름"))
        register_layout.addWidget(self.name_input)
        register_layout.addWidget(QLabel("히라가나"))
        register_layout.addWidget(self.hiragana_input)
        register_layout.addWidget(QLabel("가타카나"))
        register_layout.addWidget(self.katakana_input)
        register_layout.addWidget(QLabel("한글 표시"))
        register_layout.addWidget(self.korean_input)
        register_layout.addWidget(add_button)
        register_layout.addStretch()
        register_page = QWidget()
        register_page.setLayout(register_layout)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["이름", "히라가나", "가타카나", "한글 표시"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)

        delete_button = QPushButton("선택 삭제")
        delete_button.clicked.connect(self.delete_selected_entry)
        delete_layout = QVBoxLayout()
        delete_layout.addWidget(self.table)
        delete_layout.addWidget(delete_button)
        delete_page = QWidget()
        delete_page.setLayout(delete_layout)

        tabs = QTabWidget()
        tabs.addTab(register_page, "등록")
        tabs.addTab(delete_page, "삭제")
        tabs.addTab(self._create_papago_page(), "Papago API")

        self.status_label = QLabel()
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout = QVBoxLayout()
        layout.addWidget(tabs)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        self.refresh_table()
        self.update_status("준비됨")

    def add_entry(self) -> None:
        entry = {
            "name": self.name_input.text().strip(),
            "hiragana": self.hiragana_input.text().strip(),
            "katakana": self.katakana_input.text().strip(),
            "korean": self.korean_input.text().strip(),
            "enabled": True,
        }
        if not any((entry["name"], entry["hiragana"], entry["katakana"], entry["korean"])):
            QMessageBox.warning(self, "등록 실패", "최소 한 칸은 입력해야 합니다.")
            return
        if entry in self.entries:
            QMessageBox.information(self, "등록 생략", "이미 같은 항목이 있습니다.")
            return
        self.entries.append(entry)
        self.save_entries()
        self.name_input.clear()
        self.hiragana_input.clear()
        self.katakana_input.clear()
        self.korean_input.clear()
        self.refresh_table()
        self.update_status("등록 완료")

    def delete_selected_entry(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.entries):
            QMessageBox.information(self, "삭제 실패", "삭제할 항목을 선택하세요.")
            return
        removed = self.entries.pop(row)
        self.save_entries()
        self.refresh_table()
        label = removed.get("name") or removed.get("hiragana") or removed.get("katakana") or "항목"
        self.update_status(f"삭제 완료: {label}")

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.entries))
        for row, entry in enumerate(self.entries):
            for column, key in enumerate(("name", "hiragana", "katakana", "korean")):
                item = QTableWidgetItem(str(entry.get(key, "")))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)

    def save_entries(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "description": "User-managed Japanese STT hotwords. Add recurring names and terms here to gently bias local faster-whisper recognition.",
            "entries": self.entries,
        }
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.sync_translation_dictionary()

    def sync_translation_dictionary(self) -> None:
        if self.user_translation_dictionary_path.exists():
            data = json.loads(self.user_translation_dictionary_path.read_text(encoding="utf-8"))
        else:
            data = {
                "description": "User-managed Papago term corrections generated by Nihongo Wakarimasen.",
                "exact": {},
                "terms": [],
            }

        terms = [
            term
            for term in data.get("terms", [])
            if not (isinstance(term, dict) and term.get("managed_by") == "hotword_manager")
        ]
        for entry in self.entries:
            target = str(entry.get("korean", "")).strip()
            if not target:
                continue
            sources = self._unique_values(
                str(entry.get("name", "")),
                str(entry.get("hiragana", "")),
                str(entry.get("katakana", "")),
            )
            bad_outputs = self._unique_values(
                *sources,
                target,
                *[str(value) for value in entry.get("bad_outputs", []) if str(value).strip()],
            )
            for source in sources:
                terms.append(
                    {
                        "source": source,
                        "target": target,
                        "bad_outputs": bad_outputs,
                        "managed_by": "hotword_manager",
                    }
                )
        data["terms"] = terms
        self.user_translation_dictionary_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_translation_dictionary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _unique_values(self, *values: str) -> list[str]:
        unique = []
        seen = set()
        for value in values:
            text = value.strip()
            if text and text not in seen:
                seen.add(text)
                unique.append(text)
        return unique

    def update_status(self, message: str) -> None:
        self.status_label.setText(f"{message} | 저장 위치: {self.path}")

    def _create_papago_page(self) -> QWidget:
        credentials = load_papago_credentials(self.papago_credentials_path)
        self.papago_client_id_input = QLineEdit()
        self.papago_client_id_input.setPlaceholderText("Papago Client ID")
        self.papago_client_id_input.setText(credentials.client_id)
        self.papago_client_secret_input = QLineEdit()
        self.papago_client_secret_input.setPlaceholderText("Papago Client Secret")
        self.papago_client_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.papago_client_secret_input.setText(credentials.client_secret)

        save_button = QPushButton("API 저장")
        save_button.clicked.connect(self.save_papago_api)
        delete_button = QPushButton("저장된 API 삭제")
        delete_button.clicked.connect(self.delete_papago_api)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Client ID"))
        layout.addWidget(self.papago_client_id_input)
        layout.addWidget(QLabel("Client Secret"))
        layout.addWidget(self.papago_client_secret_input)
        layout.addWidget(save_button)
        layout.addWidget(delete_button)
        layout.addStretch()
        page = QWidget()
        page.setLayout(layout)
        return page

    def save_papago_api(self) -> None:
        client_id = self.papago_client_id_input.text().strip()
        client_secret = self.papago_client_secret_input.text().strip()
        if not client_id or not client_secret:
            QMessageBox.warning(self, "저장 실패", "Client ID와 Client Secret을 모두 입력하세요.")
            return
        save_papago_credentials(self.papago_credentials_path, client_id, client_secret)
        self.update_status("Papago API 저장 완료")

    def delete_papago_api(self) -> None:
        if self.papago_credentials_path.exists():
            self.papago_credentials_path.unlink()
        self.papago_client_id_input.clear()
        self.papago_client_secret_input.clear()
        self.update_status("Papago API 삭제 완료")

    def _load_entries(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        entries = []
        for item in data.get("entries", []):
            if not isinstance(item, dict):
                continue
            entry = {
                "name": str(item.get("name", "")).strip(),
                "hiragana": str(item.get("hiragana", "")).strip(),
                "katakana": str(item.get("katakana", "")).strip(),
                "korean": str(item.get("korean", "")).strip(),
                "bad_outputs": [
                    str(value).strip()
                    for value in item.get("bad_outputs", [])
                    if str(value).strip()
                ],
                "enabled": bool(item.get("enabled", True)),
            }
            if any((entry["name"], entry["hiragana"], entry["katakana"], entry["korean"])):
                entries.append(entry)
        return entries


def run_hotword_manager(config: AppConfig) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = HotwordManagerWindow(
        config.stt_hotwords_path,
        config.user_translation_dictionary_path,
        config.papago_credentials_path,
    )
    window.show()
    return app.exec()
