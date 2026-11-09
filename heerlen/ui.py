"""Native Qt 6 midnight-neon user interface for TeamSpeak 3 ClientQuery."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSplitter,
    QStackedWidget, QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from heerlen.query import sort_channel_tree
from heerlen.storage import load_settings, save_settings
from heerlen.native import NativeWorker, list_microphones
from heerlen.connect import SERVER, make_uri
from heerlen.hotkeys import PTT_CHOICES, is_pressed
from heerlen.background import BACKGROUNDS, BackgroundWidget, store_wallpaper

CYAN = "#16d6ff"
GREEN = "#37ef7f"
TEXT = "#f2f9ff"

STYLES = """
* { font-family: "Segoe UI"; font-size: 13px; color: #f2f9ff; }
QMainWindow, QDialog { background: #030c1b; }
QWidget#AppRoot { background: transparent; }
QFrame#Panel { background: #0a2038; border: 1px solid #21547b;
                border-radius: 15px; }
QFrame#Top { background: #06182d; border-bottom: 1px solid #19527b; }
QLabel#Title { font-size: 23px; font-weight: 800; color: #f2f9ff; }
QLabel#SubTitle { font-size: 13px; color: #16d6ff; }
QLabel#Counter { font-size: 27px; color: #37ef7f; font-weight: 800; }
QLabel#Hint { font-size: 12px; color: #b5cde2; }
QLabel#Section { font-size: 17px; font-weight: 700; color: #16d6ff; }
QPushButton { background: #0a2e51; border: 1px solid #2975aa;
              border-radius: 10px; padding: 10px 15px; color: white; font-weight: 600; }
QPushButton:hover { background: #114675; border-color: #16d6ff; }
QPushButton:pressed { background: #0878bb; }
QPushButton:checked { background: #07549d; border: 2px solid #16d6ff; }
QPushButton:disabled { color: #65798d; border-color: #25384e; background: #101b2c; }
QPushButton#PTT { border: 4px solid #37ef7f; background: #0c4c38;
                  color: #dfffe9; border-radius: 35px; padding: 8px 45px;
                  font-size: 21px; font-weight: 900; }
QPushButton#PTT:pressed { background: #1ab45d; border-color: #c8ffdf; color: #031c11; }
QPushButton#PTT:disabled { background: #162d2c; color: #607b71;
                           border-color: #2f6250; }
QTreeWidget, QListWidget, QTextEdit { background: #071729; alternate-background-color: #0a2038;
                          border: 1px solid #20496f; border-radius: 9px;
                          padding: 7px; outline: none; }
QTreeWidget::item, QListWidget::item { padding: 6px; border-radius: 6px; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #07549d; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #123656; }
QLineEdit { background: #081a30; color: white; border: 1px solid #2b668e;
            border-radius: 9px; padding: 10px; }
QLineEdit:focus { border: 1px solid #16d6ff; }
QScrollBar:vertical { width: 10px; background: #071729; }
QScrollBar::handle:vertical { background: #236089; border-radius: 4px; min-height: 18px; }
QSplitter::handle { background: #123656; width: 8px; }
QLabel#Status { background: #0a2038; border: 1px solid #245782;
                border-radius: 9px; padding: 10px; }
"""


def box(parent: QWidget | None = None, *, vertical: bool = True,
        spacing: int = 10, margins: tuple[int, int, int, int] = (0, 0, 0, 0)):
    layout = QVBoxLayout(parent) if vertical else QHBoxLayout(parent)
    layout.setSpacing(spacing)
    layout.setContentsMargins(*margins)
    return layout


def panel() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Panel")
    return frame, box(frame, margins=(16, 16, 16, 16))


class Bridge(QObject):
    snapshot = Signal(dict)
    notice = Signal(str)


class SettingsDialog(QDialog):
    """User preferences only; never asks ordinary users for a ClientQuery key."""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Instellingen — Teamspeak Heerlen PC")
        self.setMinimumWidth(520)
        self.setStyleSheet(STYLES)
        self.selected_wallpaper = ""
        layout = box(self, spacing=15, margins=(22, 22, 22, 22))

        title = QLabel("PERSOONLIJKE INSTELLINGEN")
        title.setObjectName("Section")
        layout.addWidget(title)
        info = QLabel(
            "Server: heerlen.mijnts3.nl • direct verbonden zonder TeamSpeak 3.\n"
            "Je hoeft alleen je gebruikersnaam te kiezen op het hoofdscherm."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addWidget(QLabel("Mijn PTT-toets of muisknop"))
        self.ptt_choice = QComboBox()
        for choice in PTT_CHOICES:
            self.ptt_choice.addItem(choice)
        selected = config.get("ptt_key", "F9")
        self.ptt_choice.setCurrentText(selected if selected in PTT_CHOICES else "F9")
        layout.addWidget(self.ptt_choice)
        layout.addWidget(QLabel("Windows microfoon"))
        self.microphone_choice = QComboBox()
        self.microphone_choice.addItems(list_microphones())
        saved_mic = str(config.get("microphone", "Standaard (Windows)"))
        if self.microphone_choice.findText(saved_mic) < 0:
            self.microphone_choice.addItem(saved_mic)
        self.microphone_choice.setCurrentText(saved_mic)
        layout.addWidget(self.microphone_choice)
        mic_hint = QLabel(
            "Kies Standaard (Windows) of selecteer jouw headset/microfoon. "
            "Als Windows geen microfoon ziet, blijft TeamSpeak wel verbonden. "
            "Een gewijzigde microfoon wordt na opnieuw verbinden actief."
        )
        mic_hint.setObjectName("Hint")
        mic_hint.setWordWrap(True)
        layout.addWidget(mic_hint)
        hint = QLabel("Deze toets werkt ook buiten het Heerlen-venster. "
                      "Kies een toets die niet met andere programma's botst.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.roger_checkbox = QCheckBox("3-tonige rogerpiep na loslaten PTT")
        self.roger_checkbox.setChecked(bool(config.get("roger", True)))
        layout.addWidget(self.roger_checkbox)
        explanation = QLabel(
            "De 3 tonen worden aan het einde van je uitzending via TeamSpeak "
            "naar het kanaal verstuurd (niet alleen lokaal afgespeeld)."
        )
        explanation.setObjectName("Hint")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        layout.addWidget(QLabel("Achtergrond"))
        self.wallpaper_combo = QComboBox()
        self.wallpaper_combo.addItems(list(BACKGROUNDS))
        self.wallpaper_combo.setCurrentText(config.get("background", "Nachtblauw"))
        layout.addWidget(self.wallpaper_combo)
        choose_button = QPushButton("Eigen afbeelding kiezen (PNG, JPG, WEBP)")
        choose_button.clicked.connect(self.choose_wallpaper)
        layout.addWidget(choose_button)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_wallpaper(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Selecteer je achtergrond", "",
            "Afbeeldingen (*.png *.jpg *.jpeg *.webp)"
        )
        if filename:
            self.selected_wallpaper = filename
            self.wallpaper_combo.setCurrentText("Eigen afbeelding")

    def accept(self):
        if self.selected_wallpaper:
            try:
                store_wallpaper(self.selected_wallpaper)
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, "Ongeldige achtergrond", str(exc))
                return
        super().accept()

    def values(self) -> dict:
        return {
            "ptt_key": self.ptt_choice.currentText(),
            "microphone": self.microphone_choice.currentText(),
            "roger": self.roger_checkbox.isChecked(),
            "background": self.wallpaper_combo.currentText(),
        }


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Teamspeak Heerlen PC")
        self.resize(1120, 780)
        self.setMinimumSize(830, 620)
        self.setStyleSheet(STYLES)
        self.setWindowIcon(QIcon(str(self._asset("logo.svg"))))
        self.cfg = load_settings()
        self.current_view = self.cfg.get("view", "kanalen")
        self.latest: dict = {}
        self.talking: set[int] = set()
        self.worker: NativeWorker | None = None
        self.bridge = Bridge()
        self.bridge.snapshot.connect(self.show_snapshot)
        self.bridge.notice.connect(self.show_notice)
        self._tree_signature = None
        self._ptt_pressed = False
        self._button_ptt_held = False
        self._hotkey_held = False
        self._requested_connection = False
        self._create_ui()
        self.switch_view(self.current_view)
        self.ptt_timer = QTimer(self)
        self.ptt_timer.setInterval(30)
        self.ptt_timer.timeout.connect(self._poll_hotkey)
        self.ptt_timer.start()

    @staticmethod
    def _asset(filename: str) -> Path:
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        return root / "assets" / filename

    def _create_ui(self):
        root = BackgroundWidget()
        root.setObjectName("AppRoot")
        root.set_preset(self.cfg.get("background", "Nachtblauw"))
        self.background_view = root
        self.setCentralWidget(root)
        layout = box(root, spacing=0)

        top = QFrame()
        top.setObjectName("Top")
        top_layout = box(top, margins=(20, 16, 20, 15), spacing=12)
        branding = box(vertical=False, spacing=10)
        title_col = box(spacing=3)
        title = QLabel("TEAMSPEAK  HEERLEN")
        title.setObjectName("Title")
        title_col.addWidget(title)
        subtitle = QLabel("PC EDITION  •  WINDOWS  •  LIVE VERBINDING")
        subtitle.setObjectName("SubTitle")
        title_col.addWidget(subtitle)
        branding.addLayout(title_col, 1)
        self.setup_btn = QPushButton("⚙  Instellingen")
        self.setup_btn.clicked.connect(self.open_settings)
        branding.addWidget(self.setup_btn)
        top_layout.addLayout(branding)

        join_row = box(vertical=False, spacing=9)
        self.nickname_field = QLineEdit(str(self.cfg.get("nickname", "")))
        self.nickname_field.setPlaceholderText("Vul hier jouw TeamSpeak-naam in...")
        self.nickname_field.setMaxLength(30)
        self.nickname_field.returnPressed.connect(self.toggle_connection)
        join_row.addWidget(self.nickname_field, 1)
        self.join_server_btn = QPushButton("●  Verbinden met Heerlen")
        self.join_server_btn.clicked.connect(self.toggle_connection)
        join_row.addWidget(self.join_server_btn)
        top_layout.addLayout(join_row)
        server_label = QLabel(f"VASTE SERVER: {SERVER}  •  GEEN ANDERE TEAM SPEAK APP NODIG")
        server_label.setObjectName("Hint")
        top_layout.addWidget(server_label)

        head_controls = box(vertical=False)
        self.status_label = QLabel("●  Vul je naam in en verbind met Heerlen...")
        self.status_label.setObjectName("Status")
        head_controls.addWidget(self.status_label, 1)
        self.channels_btn = QPushButton("◫  Kanalen")
        self.monitor_btn = QPushButton("◉  Live monitor")
        for button in (self.channels_btn, self.monitor_btn):
            button.setCheckable(True)
            head_controls.addWidget(button)
        self.channels_btn.clicked.connect(lambda: self.switch_view("kanalen"))
        self.monitor_btn.clicked.connect(lambda: self.switch_view("monitor"))
        top_layout.addLayout(head_controls)
        self.mic_indicator = QLabel("MICROFOON: wordt gecontroleerd bij verbinden")
        self.mic_indicator.setObjectName("Hint")
        top_layout.addWidget(self.mic_indicator)
        layout.addWidget(top)

        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)

        channel_page = QWidget()
        channel_layout = box(channel_page, margins=(18, 17, 18, 8))
        splitter = QSplitter(Qt.Orientation.Horizontal)
        channels_panel, channel_panel_layout = panel()
        label = QLabel("SERVERKANALEN")
        label.setObjectName("Section")
        channel_panel_layout.addWidget(label)
        hint = QLabel("Dubbelklik op een kanaal om over te schakelen. Spacerregels zijn aanklikbaar.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        channel_panel_layout.addWidget(hint)
        self.channel_tree = QTreeWidget()
        self.channel_tree.setHeaderHidden(True)
        self.channel_tree.setAlternatingRowColors(True)
        self.channel_tree.itemDoubleClicked.connect(self.on_channel_doubleclick)
        channel_panel_layout.addWidget(self.channel_tree, 1)
        splitter.addWidget(channels_panel)

        right_panel, right_layout = panel()
        right_title = QLabel("ONLINE GEBRUIKERS")
        right_title.setObjectName("Section")
        right_layout.addWidget(right_title)
        self.quick_count = QLabel("0 online")
        self.quick_count.setObjectName("Counter")
        right_layout.addWidget(self.quick_count)
        self.quick_users = QListWidget()
        right_layout.addWidget(self.quick_users, 1)
        splitter.addWidget(right_panel)
        splitter.setSizes([630, 360])
        channel_layout.addWidget(splitter, 1)
        self.pages.addWidget(channel_page)

        monitor_page = QWidget()
        monitor_layout = box(monitor_page, margins=(18, 17, 18, 8), spacing=12)
        head, head_layout = panel()
        monitor_title = QLabel("LIVE GEBRUIKERSMONITOR")
        monitor_title.setObjectName("Section")
        head_layout.addWidget(monitor_title)
        stats = box(vertical=False, spacing=30)
        self.online_count = QLabel("0 ONLINE")
        self.online_count.setObjectName("Counter")
        self.speaking_count = QLabel("0 SPREKERS")
        self.speaking_count.setObjectName("Counter")
        stats.addWidget(self.online_count)
        stats.addWidget(self.speaking_count)
        stats.addStretch(1)
        head_layout.addLayout(stats)
        monitor_layout.addWidget(head)
        filters = box(vertical=False)
        self.filters: dict[str, QPushButton] = {}
        for key, text in [("all", "Iedereen"), ("talking", "Sprekers"), ("mine", "Mijn kanaal")]:
            button = QPushButton(text)
            button.setCheckable(True)
            button.clicked.connect(lambda _, name=key: self.set_filter(name))
            self.filters[key] = button
            filters.addWidget(button)
        filters.addStretch(1)
        monitor_layout.addLayout(filters)
        self.monitor_list = QListWidget()
        self.monitor_list.setAlternatingRowColors(True)
        monitor_layout.addWidget(self.monitor_list, 1)
        self.pages.addWidget(monitor_page)

        lower = QFrame()
        lower.setObjectName("Top")
        lower_layout = box(lower, spacing=9, margins=(18, 10, 18, 16))
        self.rx_tx = QLabel("RX  ○  RUST       TX  ○  RUST")
        self.rx_tx.setObjectName("SubTitle")
        lower_layout.addWidget(self.rx_tx)
        row = box(vertical=False, spacing=16)
        chat_col = box(spacing=6)
        chat_title = QLabel("KANAALCHAT")
        chat_title.setObjectName("Section")
        chat_col.addWidget(chat_title)
        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setMaximumHeight(85)
        self.chat_log.setPlaceholderText("Kanaalberichten en meldingen verschijnen hier.")
        chat_col.addWidget(self.chat_log)
        chat_row = box(vertical=False, spacing=8)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Typ een bericht voor je huidige kanaal...")
        self.chat_input.returnPressed.connect(self.send_chat)
        self.send_chat_btn = QPushButton("Verstuur")
        self.send_chat_btn.clicked.connect(self.send_chat)
        chat_row.addWidget(self.chat_input, 1)
        chat_row.addWidget(self.send_chat_btn)
        chat_col.addLayout(chat_row)
        row.addLayout(chat_col, 1)
        ptt_col = box(spacing=6)
        hint = QLabel("HOUD PTT INGEDRUKT • OF KIES JE EIGEN TOETS")
        hint.setObjectName("Hint")
        ptt_col.addWidget(hint, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.ptt_button = QPushButton("PTT")
        self.ptt_button.setObjectName("PTT")
        self.ptt_button.setMinimumSize(200, 92)
        self.ptt_button.pressed.connect(self.on_ptt_button_pressed)
        self.ptt_button.released.connect(self.on_ptt_button_released)
        ptt_col.addWidget(self.ptt_button)
        row.addLayout(ptt_col)
        lower_layout.addLayout(row)
        layout.addWidget(lower)
        self.statusBar().showMessage(f"Vaste server: {SERVER} • vul je naam in en druk op Verbinden.")
        self._set_connected(False)

    def switch_view(self, view: str):
        self.current_view = view if view in ("kanalen", "monitor") else "kanalen"
        self.pages.setCurrentIndex(0 if self.current_view == "kanalen" else 1)
        self.channels_btn.setChecked(self.current_view == "kanalen")
        self.monitor_btn.setChecked(self.current_view == "monitor")
        self.cfg["view"] = self.current_view
        save_settings(self.cfg)

    def set_filter(self, name: str):
        self.filter_name = name
        for key, button in self.filters.items():
            button.setChecked(key == name)
        self.refresh_monitor()

    def toggle_connection(self):
        if self._requested_connection:
            self.disconnect_server()
        else:
            self.start_worker()

    def start_worker(self):
        nickname = self.nickname_field.text().strip()
        try:
            make_uri(nickname)
        except ValueError as exc:
            QMessageBox.warning(self, "Vul je naam in", str(exc))
            return
        self.cfg["nickname"] = nickname
        save_settings(self.cfg)
        if self.worker is not None:
            self.worker.stop()
            self.worker.join(timeout=5.0)
        self.worker = NativeWorker(
            nickname, self.bridge.snapshot.emit, self.bridge.notice.emit,
            roger_enabled=bool(self.cfg.get("roger", True)),
            microphone=str(self.cfg.get("microphone", "Standaard (Windows)")),
        )
        self._requested_connection = True
        self.join_server_btn.setText("■  Verbinding verbreken")
        self.nickname_field.setEnabled(False)
        self.statusBar().showMessage(f"Verbinden met {SERVER}...")
        self.worker.start()

    def disconnect_server(self):
        self.release_ptt()
        if self.worker is not None:
            self.worker.stop()
            self.worker.join(timeout=5.0)
            self.worker = None
        self._requested_connection = False
        self.nickname_field.setEnabled(True)
        self.join_server_btn.setText("●  Verbinden met Heerlen")
        self.show_snapshot({"connected": False, "problem": "Verbinding verbroken."})

    def open_settings(self):
        dialog = SettingsDialog(self.cfg, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            old_microphone = self.cfg.get("microphone", "Standaard (Windows)")
            self.cfg.update(dialog.values())
            save_settings(self.cfg)
            self.background_view.set_preset(self.cfg.get("background", "Nachtblauw"))
            if self.worker is not None:
                self.send_command("roger", "1" if self.cfg.get("roger") else "0")
            if old_microphone != self.cfg.get("microphone") and self._requested_connection:
                self.disconnect_server()
                self.start_worker()
                self.statusBar().showMessage("Nieuwe microfoon geselecteerd. Opnieuw verbinden met Heerlen...", 8000)
            else:
                self.statusBar().showMessage("Persoonlijke instellingen opgeslagen.", 6000)

    def send_command(self, kind: str, payload: str = ""):
        if self.worker is not None:
            self.worker.send(kind, payload)

    def on_channel_doubleclick(self, item: QTreeWidgetItem, column: int):
        if not self.latest.get("connected"):
            return
        cid = item.data(0, Qt.ItemDataRole.UserRole)
        if cid is not None:
            self.send_command("join", str(cid))

    def on_ptt_button_pressed(self):
        self._button_ptt_held = True
        self.press_ptt()

    def on_ptt_button_released(self):
        self._button_ptt_held = False
        if not self._hotkey_held:
            self.release_ptt()

    def _poll_hotkey(self):
        # Lightweight Windows key-state check, only for the user's selected key.
        key = str(self.cfg.get("ptt_key", "F9"))
        held = is_pressed(key)
        if held != self._hotkey_held:
            self._hotkey_held = held
            if held:
                self.press_ptt()
            elif not self._button_ptt_held:
                self.release_ptt()
        if self.worker is not None and self._requested_connection and not self.worker.is_alive():
            self._requested_connection = False
            self.join_server_btn.setText("●  Verbinden met Heerlen")
            self.nickname_field.setEnabled(True)

    def press_ptt(self):
        if not self.latest.get("connected") or not self.latest.get("mic_ready") or self._ptt_pressed:
            return
        self._ptt_pressed = True
        self.send_command("ptt_on")
        self.ptt_button.setText("TX ●")
        self.statusBar().showMessage("PTT actief: de native audio-engine zendt naar Heerlen.")

    def release_ptt(self):
        if not self._ptt_pressed:
            return
        self._ptt_pressed = False
        self.send_command("ptt_off")
        self.ptt_button.setText("PTT")

    def send_chat(self):
        value = self.chat_input.text().strip()
        if value and self.latest.get("connected"):
            self.send_command("chat", value)
            self.chat_log.append(f"Jij: {value}")
            self.chat_input.clear()

    def show_notice(self, message: str):
        self.statusBar().showMessage(message, 8000)
        self.chat_log.append(message)

    def _set_connected(self, connected: bool):
        self.ptt_button.setEnabled(connected and bool(self.latest.get("mic_ready", False)))
        self.send_chat_btn.setEnabled(connected)
        self.chat_input.setEnabled(connected)
        if not connected and self._ptt_pressed:
            self.release_ptt()

    def show_snapshot(self, snapshot: dict):
        self.latest = snapshot
        connected = bool(snapshot.get("connected"))
        self._set_connected(connected)
        name = snapshot.get("server_name") or "Heerlen"
        if connected:
            mic_name = snapshot.get("mic_name", "Microfoon onbekend")
            mic_ok = bool(snapshot.get("mic_ready", False))
            speaker_ok = bool(snapshot.get("output_ready", False))
            mic_text = (f"MICROFOON: {mic_name}" if mic_ok
                        else "MICROFOON NIET GEVONDEN • Instellingen > Windows microfoon")
            self.mic_indicator.setText(mic_text + (" • LUIDSPREKER OK" if speaker_ok
                                                   else " • Controleer je luidspreker"))
            self.mic_indicator.setStyleSheet(f"color: {GREEN if mic_ok else '#ffb74d'};")
        else:
            self.mic_indicator.setText("MICROFOON: wordt gecontroleerd bij verbinden")
        self.status_label.setText(
            f"●  Verbonden: {name}" if connected
            else "●  Niet verbonden — " + snapshot.get("problem", "Vul je naam in en klik Verbinden.")
        )
        self.status_label.setStyleSheet(
            f"color:{GREEN if connected else '#ffb74d'};"
        )
        users = snapshot.get("users", [])
        speaking = set(snapshot.get("talking", []))
        my_id = snapshot.get("my_id", 0)
        self.talking = speaking
        self.online_count.setText(f"{len(users)} ONLINE")
        self.speaking_count.setText(f"{len(speaking)} SPREKERS")
        self.quick_count.setText(f"{len(users)} online")
        is_tx = my_id in speaking
        my_channel_id = int(snapshot.get("channel_id", 0))
        audible_users = {
            int(user.get("clid", 0))
            for user in users
            if int(user.get("cid", 0)) == my_channel_id
        }
        is_rx = any(uid != my_id and uid in audible_users for uid in speaking)
        self.rx_tx.setText(
            f"RX  {'● ACTIEF' if is_rx else '○ RUST'}"
            f"       TX  {'● ACTIEF' if is_tx else '○ RUST'}"
            "       • LIVE TEAMSPEAK"
        )
        new_sig = (
            repr(snapshot.get("channels")), repr(users), tuple(sorted(speaking)), my_id
        )
        if new_sig != self._tree_signature:
            self._tree_signature = new_sig
            self.refresh_channels()
            self.refresh_monitor()

    def refresh_channels(self):
        channels = self.latest.get("channels", [])
        users = self.latest.get("users", [])
        users_by_channel = defaultdict(list)
        for user in users:
            try:
                cid = int(user.get("cid", 0))
            except (ValueError, TypeError):
                continue
            users_by_channel[cid].append(user)
        self.channel_tree.clear()
        items: dict[int, QTreeWidgetItem] = {}
        for channel, depth in sort_channel_tree(channels):
            cid = int(channel.get("cid", 0))
            pid = int(channel.get("pid", 0))
            parent = items.get(pid)
            name = channel.get("channel_name", f"Kanaal {cid}")
            entry = QTreeWidgetItem([f"▣  {name}"])
            entry.setData(0, Qt.ItemDataRole.UserRole, cid)
            entry.setForeground(0, QBrush(QColor(CYAN)))
            if parent is None:
                self.channel_tree.addTopLevelItem(entry)
            else:
                parent.addChild(entry)
            items[cid] = entry
            for user in sorted(users_by_channel.get(cid, []),
                               key=lambda u: u.get("client_nickname", "").lower()):
                username = user.get("client_nickname", "Onbekend")
                uid = int(user.get("clid", 0))
                active = uid in self.talking
                child = QTreeWidgetItem([f"{'●' if active else '○'}  {username}"])
                child.setForeground(0, QBrush(QColor(GREEN if active else TEXT)))
                entry.addChild(child)
            entry.setExpanded(True)
        self.quick_users.clear()
        for user in sorted(users, key=lambda u: u.get("client_nickname", "").lower()):
            uid = int(user.get("clid", 0))
            self.quick_users.addItem(
                f"{'●' if uid in self.talking else '○'}  "
                f"{user.get('client_nickname', 'Onbekend')}"
            )

    def refresh_monitor(self):
        users = self.latest.get("users", [])
        channel_names = {
            int(c.get("cid", 0)): c.get("channel_name", "")
            for c in self.latest.get("channels", [])
        }
        my_channel = int(self.latest.get("channel_id", 0))
        speaking = self.talking
        filtered = sorted(users, key=lambda u: (
            0 if int(u.get("clid", 0)) in speaking else 1,
            u.get("client_nickname", "").lower()
        ))
        self.monitor_list.clear()
        for u in filtered:
            clid = int(u.get("clid", 0))
            cid = int(u.get("cid", 0))
            active = clid in speaking
            if self.filter_name == "talking" and not active:
                continue
            if self.filter_name == "mine" and cid != my_channel:
                continue
            name = u.get("client_nickname", "Onbekend")
            label = "SPREEKT" if active else "ONLINE"
            if u.get("client_input_muted") == "1":
                label = "MIC UIT"
            channel = channel_names.get(cid, "Onbekend kanaal")
            item = QListWidgetItem(
                f"{'●' if active else '○'}   {name}     • {label}\n      {channel}"
            )
            item.setForeground(QBrush(QColor(GREEN if active else TEXT)))
            self.monitor_list.addItem(item)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            # Never leave the microphone open after switching away from this app.
            # Global PTT remains available when another application is active.
            # Cancel any mouse-button hold when the window loses focus.
            if not self._hotkey_held:
                self._button_ptt_held = False
                self.release_ptt()
        super().changeEvent(event)

    def closeEvent(self, event):
        self.release_ptt()
        if self.worker is not None:
            self.worker.stop()
            self.worker.join(timeout=5.0)
        super().closeEvent(event)
